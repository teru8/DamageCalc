"""
Python ↔ Node.js bridge for @smogon/calc damage calculation.
Manages a persistent Node.js subprocess; communicates via line-delimited JSON.
"""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from src.constants import ABILITY_JA_TO_EN, nature_ja_to_en
from src.data.item_dictionary import ITEM_FALLBACK_JA_TO_EN
from src.data.item_catalog import get_item_name_en
from src.models import PokemonInstance, MoveInfo

# ── Node.js executable path ───────────────────────────────────────────────

def _find_node() -> str:
    node = shutil.which("node")
    if node:
        return node
    for p in [
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
        r"/usr/local/bin/node",
        r"/usr/bin/node",
    ]:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("node.exe が見つかりません。Node.js をインストールしてください。")

def _resolve_bridge_js() -> Path:
    """Resolve bridge.js path for both dev and PyInstaller builds."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates: list[Path] = []
        meipass_raw = getattr(sys, "_MEIPASS", "")
        if meipass_raw:
            candidates.append(Path(meipass_raw) / "src" / "calc" / "bridge.js")
        candidates.append(exe_dir / "_internal" / "src" / "calc" / "bridge.js")
        candidates.append(exe_dir / "src" / "calc" / "bridge.js")
        for path in candidates:
            if path.exists():
                return path
        # Fallback to the most likely onedir location for clearer errors upstream.
        return exe_dir / "_internal" / "src" / "calc" / "bridge.js"
    return Path(__file__).resolve().parent / "bridge.js"

_BRIDGE_JS = _resolve_bridge_js()

def _item_name_to_en(item_name_ja: str) -> str:
    name = (item_name_ja or "").strip()
    if not name:
        return ""
    mapped = ITEM_FALLBACK_JA_TO_EN.get(name, "")
    if mapped:
        return mapped
    return get_item_name_en(name)

def _ability_name_to_en(ability_name_ja: str, pokemon_name_ja: str = "", terastal_active: bool = False) -> str:
    """Convert Japanese ability name to English, with special handling for form-dependent abilities."""
    name = (ability_name_ja or "").strip()
    if not name:
        return ""
    
    # Special handling for Calyrex forms
    if name == "じんばいったい":
        if "はくばじょうのすがた" in pokemon_name_ja:
            return "As One (Glastrier)"
        elif "こくばじょうのすがた" in pokemon_name_ja:
            return "As One (Spectrier)"
    
    # Special handling for Ogerpon forms (requires terastal active)
    if name == "おもかげやどし" and terastal_active:
        if "みどりのめん" in pokemon_name_ja:
            return "Embody Aspect (Teal)"
        elif "かまどのめん" in pokemon_name_ja:
            return "Embody Aspect (Hearthflame)"
        elif "いどのめん" in pokemon_name_ja:
            return "Embody Aspect (Wellspring)"
        elif "いしずえのめん" in pokemon_name_ja:
            return "Embody Aspect (Cornerstone)"
    
    mapped = ABILITY_JA_TO_EN.get(name, "")
    if mapped:
        return mapped
    return ""


# PokeAPI form names that differ from Smogon species names
_POKEAPI_TO_SMOGON_SPECIES: dict[str, str] = {
    # Mimikyu forms
    "mimikyu-disguised":  "Mimikyu",
    # Indeedee forms (gender-specific abilities)
    "indeedee-male":  "Indeedee",
    "indeedee-female":  "Indeedee-F",
    # Basculegion forms (Smogon male = "Basculegion" without -M suffix)
    "basculegion-male":  "Basculegion",
    "basculegion-female":  "Basculegion-F",
    # Jellicent forms (gender forms are competitively identical)
    "jellicent-male":  "Jellicent",
    "jellicent-female":  "Jellicent",
    # Meowstic forms (gender-specific abilities)
    "meowstic-male":  "Meowstic",
    "meowstic-female":  "Meowstic-F",
    # Oinkologne forms (gender-specific abilities)
    "oinkologne-male":  "Oinkologne",
    "oinkologne-female":  "Oinkologne-F",
    # Toxtricity forms
    "toxtricity-amped":  "Toxtricity",
    "toxtricity-low-key":  "Toxtricity-Low-Key",
    # Paldean Tauros breed forms (PokeAPI uses -breed suffix, Smogon does not)
    "tauros-paldea-combat-breed":  "Tauros-Paldea",
    "tauros-paldea-blaze-breed":  "Tauros-Paldea-Blaze",
    "tauros-paldea-aqua-breed":  "Tauros-Paldea-Aqua",
    # Floette Eternal Flower
    "floette-eternal-flower":  "Floette-Eternal",
    "floette-eternal":  "Floette-Eternal",
    # Zygarde forms (power-construct forms map to base forms)
    "zygarde-10":  "Zygarde-10",
    "zygarde-50":  "Zygarde",
    "zygarde-10-power-construct":  "Zygarde-10",
    "zygarde-50-power-construct":  "Zygarde",
    "zygarde-complete":  "Zygarde-Complete",
    # Minior forms (both map to Minior)
    "minior-red-meteor":  "Minior",
    "minior-red":  "Minior",
    # Darmanitan Galar forms (zen mode is different from standard)
    "darmanitan-galar-standard":  "Darmanitan-Galar",
    "darmanitan-galar-zen":  "Darmanitan-Galar-Zen",
    # Darmanitan forms (Zen Mode: Standard → Zen)
    "darmanitan-standard":  "Darmanitan",
    "darmanitan-zen":  "Darmanitan-Zen",
    # Meloetta forms (Relic Song: Aria → Pirouette)
    "meloetta-aria":  "Meloetta",
    "meloetta-pirouette":  "Meloetta-Pirouette",
    # Wishiwashi forms (Schooling: Solo → School)
    "wishiwashi-solo":  "Wishiwashi",
    "wishiwashi-school":  "Wishiwashi-School",
    # Eiscue forms (Ice Face: Ice → Noice)
    "eiscue-ice":  "Eiscue",
    "eiscue-noice":  "Eiscue-Noice",
    # Morpeko forms (Hunger Switch: Full Belly → Hangry)
    "morpeko-full-belly":  "Morpeko",
    "morpeko-hangry":  "Morpeko-Hangry",
    # Palafin forms (Zero to Hero: Zero → Hero)
    "palafin-zero":  "Palafin",
    "palafin-hero":  "Palafin-Hero",
    # Deoxys forms
    "deoxys-normal":  "Deoxys",
    "deoxys-attack":  "Deoxys-Attack",
    "deoxys-defense":  "Deoxys-Defense",
    "deoxys-speed":  "Deoxys-Speed",
    # Wormadam forms
    "wormadam-plant":  "Wormadam",
    "wormadam-sandy":  "Wormadam-Sandy",
    "wormadam-trash":  "Wormadam-Trash",
    # Shaymin forms
    "shaymin-land":  "Shaymin",
    "shaymin-sky":  "Shaymin-Sky",
    # Basculin forms
    "basculin-red-striped":  "Basculin",
    "basculin-blue-striped":  "Basculin-Blue-Striped",
    "basculin-white-striped":  "Basculin-White-Striped",
    # Therian/Incarnate forms
    "tornadus-incarnate":  "Tornadus",
    "tornadus-therian":  "Tornadus-Therian",
    "thundurus-incarnate":  "Thundurus",
    "thundurus-therian":  "Thundurus-Therian",
    "landorus-incarnate":  "Landorus",
    "landorus-therian":  "Landorus-Therian",
    "enamorus-incarnate":  "Enamorus",
    "enamorus-therian":  "Enamorus-Therian",
    # Keldeo forms
    "keldeo-ordinary":  "Keldeo",
    "keldeo-resolute":  "Keldeo-Resolute",
    # Pumpkaboo/Gourgeist size variants
    "pumpkaboo-average":  "Pumpkaboo",
    "pumpkaboo-small":  "Pumpkaboo-Small",
    "pumpkaboo-large":  "Pumpkaboo-Large",
    "pumpkaboo-super":  "Pumpkaboo-Super",
    "gourgeist-average":  "Gourgeist",
    "gourgeist-small":  "Gourgeist-Small",
    "gourgeist-large":  "Gourgeist-Large",
    "gourgeist-super":  "Gourgeist-Super",
    # Hoopa forms
    "hoopa":  "Hoopa",
    "hoopa-unbound":  "Hoopa-Unbound",
    # Oricorio styles
    "oricorio-baile":  "Oricorio",
    "oricorio-pom-pom":  "Oricorio-Pom-Pom",
    "oricorio-pau":  "Oricorio-Pa'u",
    "oricorio-sensu":  "Oricorio-Sensu",
    # Lycanroc forms
    "lycanroc-midday":  "Lycanroc",
    "lycanroc-midnight":  "Lycanroc-Midnight",
    "lycanroc-dusk":  "Lycanroc-Dusk",
    # Urshifu forms
    "urshifu-single-strike":  "Urshifu",
    "urshifu-rapid-strike":  "Urshifu-Rapid-Strike",
    # Rotom forms
    "rotom-heat":  "Rotom-Heat",
    "rotom-wash":  "Rotom-Wash",
    "rotom-frost":  "Rotom-Frost",
    "rotom-fan":  "Rotom-Fan",
    "rotom-mow":  "Rotom-Mow",
    # Giratina forms
    "giratina-altered":  "Giratina",
    "giratina-origin":  "Giratina-Origin",
    # Kyurem forms
    "kyurem-black":  "Kyurem-Black",
    "kyurem-white":  "Kyurem-White",
    # Necrozma forms
    "necrozma-dawn":  "Necrozma-Dawn-Wings",
    "necrozma-dusk":  "Necrozma-Dusk-Mane",
    "necrozma-ultra":  "Necrozma-Ultra",
    # Zacian/Zamazenta forms
    "zacian":  "Zacian",
    "zacian-crowned":  "Zacian-Crowned",
    "zamazenta":  "Zamazenta",
    "zamazenta-crowned":  "Zamazenta-Crowned",
    # Calyrex forms
    "calyrex-ice":  "Calyrex-Ice",
    "calyrex-shadow":  "Calyrex-Shadow",
    # Dialga/Palkia Origin forms
    "dialga-origin":  "Dialga-Origin",
    "palkia-origin":  "Palkia-Origin",
    # Ursaluna Bloodmoon
    "ursaluna-bloodmoon":  "Ursaluna-Bloodmoon",
    # Ogerpon masks
    "ogerpon":  "Ogerpon",
    "ogerpon-wellspring-mask":  "Ogerpon-Wellspring",
    "ogerpon-hearthflame-mask":  "Ogerpon-Hearthflame",
    "ogerpon-cornerstone-mask":  "Ogerpon-Cornerstone",
    # Castform forms
    "castform":  "Castform",
    "castform-sunny":  "Castform-Sunny",
    "castform-rainy":  "Castform-Rainy",
    "castform-snowy":  "Castform-Snowy",
    # Aegislash forms
    "aegislash-shield":  "Aegislash-Shield",
    "aegislash-blade":  "Aegislash-Blade",
    # Minior forms (Shields Down: Meteor → Core)
    "minior-red-meteor":  "Minior-Meteor",
    "minior-red":  "Minior",
    # Terapagos forms
    "terapagos":  "Terapagos",
    "terapagos-terastal":  "Terapagos-Terastal",
    "terapagos-stellar":  "Terapagos-Stellar",
}

# Mega forms where base PokeAPI name_en differs from what Smogon expects as the Mega base.
# Key: Smogon name of the base form, Value: Smogon name of the Mega form.
_MEGA_BASE_TO_SMOGON: dict[str, str] = {
    "Floette-Eternal":        "Floette-Mega",  # Floettite transforms Floette-Eternal → Floette-Mega
    "Floette-Eternal-Flower": "Floette-Mega",  # PokeAPI name variant
    "Zygarde-50":             "Mega Zygarde",  # Zygarde-50 → Mega Zygarde (custom)
}


def smogon_mega_species(name_en: str, name_ja: str) -> str:
    """Return Smogon species name, resolving Mega forms via the Japanese name prefix."""
    normalized = _normalize_smogon_species(name_en)
    if not (name_ja or "").startswith("メガ") or "Mega" in normalized:
        return normalized
    if normalized in _MEGA_BASE_TO_SMOGON:
        return _MEGA_BASE_TO_SMOGON[normalized]
    tail = (name_ja or "")[-1]
    if tail in ("Ｘ", "X"):
        return normalized + "-Mega-X"
    elif tail in ("Ｙ", "Y"):
        return normalized + "-Mega-Y"
    return normalized + "-Mega"


def _normalize_smogon_species(name: str) -> str:
    """Convert PokeAPI form names (lowercase-hyphenated) to Smogon species names."""
    if not name:
        return name
    lower = name.lower()
    if lower in _POKEAPI_TO_SMOGON_SPECIES:
        return _POKEAPI_TO_SMOGON_SPECIES[lower]
    # General: capitalize the first letter of each hyphen-separated segment.
    # "-male" / "-female" suffixes → "-M" / "-F"
    segments = lower.split("-")
    result = []
    for i, seg in enumerate(segments):
        # Region prefixes: alola, galar, hisui, paldea → capitalize
        if seg in ("alola", "galar", "hisui", "paldea"):
            result.append(seg.capitalize())
        # Size variants: small, large, super → capitalize
        elif seg in ("small", "large", "super"):
            result.append(seg.capitalize())
        # Breed suffixes: combat, blaze, aqua → capitalize
        elif seg in ("combat", "blaze", "aqua"):
            result.append(seg.capitalize())
        # Gender suffixes: male/female → M/F (except for specific cases handled by mapping)
        elif seg == "male":
            result.append("M")
        elif seg == "female":
            result.append("F")
        # Standard segments: capitalize
        else:
            result.append(seg.capitalize())
    return "-".join(result)


_FORCE_FIXED_BP_OVERRIDE_MOVES_JA: frozenset[str] = frozenset({
    "ころがる", "アイスボール", "れんぞくぎり",
    "おはかまいり", "ふんどのこぶし", "エコーボイス",
    "アシストパワー", "つけあがる", "おしおき",
    "しおふき", "ふんか", "ドラゴンエナジー",
    "じたばた", "きしかいせい",
    "しぼりとる", "にぎりつぶす",
    "からげんき", "たたりめ", "ベノムショック",
    "しおみず", "かたきうち", "ゆきなだれ",
    "はたきおとす", "マグニチュード",
    "ジャイロボール", "エレキボール",
})


# ── Type name: English lowercase → title case (for smogon) ───────────────
TYPE_TO_SMOGON: dict[str, str] = {
    t: t.capitalize() for t in [
        "normal", "fire", "water", "electric", "grass", "ice",
        "fighting", "poison", "ground", "flying", "psychic", "bug",
        "rock", "ghost", "dragon", "dark", "steel", "fairy", "stellar",
    ]
}

# ── Singleton bridge process ──────────────────────────────────────────────

class SmogonBridge:
    _instance: "SmogonBridge | None" = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "SmogonBridge":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = SmogonBridge()
        return cls._instance

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._io_lock = threading.Lock()
        self._start()

    def _start(self) -> None:
        node = _find_node()
        bridge_cwd = _BRIDGE_JS.parent
        if not bridge_cwd.is_dir():
            raise FileNotFoundError(
                "bridge.js の実行ディレクトリが見つかりません: {}".format(bridge_cwd)
            )
        creationflags = 0
        startupinfo = None
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
        self._proc = subprocess.Popen(
            [node, str(_BRIDGE_JS)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(bridge_cwd),
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        t = threading.Thread(target=self._drain_stderr, daemon=True)
        t.start()

    def _drain_stderr(self) -> None:
        if self._proc is None or self._proc.stderr is None:
            return
        for line in self._proc.stderr:
            line = line.rstrip()
            if line:
                logging.warning("smogon-bridge stderr: %s", line)

    def _send(self, req: dict) -> dict:
        if self._proc is None or self._proc.poll() is not None:
            self._start()
        payload = json.dumps(req, ensure_ascii=False) + "\n"
        with self._io_lock:
            self._proc.stdin.write(payload)
            self._proc.stdin.flush()
            line = self._proc.stdout.readline()
        if not line:
            return {"min": 0, "max": 0, "error": "bridge closed"}
        return json.loads(line)

    def calc(self, attacker_d: dict, defender_d: dict,
             move_d: dict, field_d: dict) -> tuple[int, int, bool]:
        req = {"attacker": attacker_d, "defender": defender_d,
               "move": move_d, "field": field_d}
        try:
            res = self._send(req)
        except (
            AttributeError,
            BrokenPipeError,
            ConnectionError,
            json.JSONDecodeError,
            OSError,
            TypeError,
            ValueError,
        ) as e:
            import logging
            logging.warning(
                "SmogonBridge calc error (atk=%r def=%r move=%r): %s",
                attacker_d.get("name"), defender_d.get("name"), move_d.get("name"),
                e, exc_info=True,
            )
            return (0, 0, True)
        is_error = bool(res.get("error"))
        return (max(0, res.get("min", 0)), max(0, res.get("max", 0)), is_error)

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def __del__(self) -> None:
        self.close()


# ── Public helpers ────────────────────────────────────────────────────────

def pokemon_to_attacker_dict(
    p: PokemonInstance,
    ev_override: dict[str, int] | None = None,
    atk_rank: int = 0,
    terastal_type: str = "",
    nat_mult_override: float = 1.0,
    use_sp: bool = False,
    allies_fainted: int = 0,
    gender: str = "",
    ability_on: bool = False,
    apply_both: bool = False,
) -> dict:
    """Build attacker descriptor for the bridge."""
    nature_en = nature_ja_to_en(p.nature)

    # Apply nature mult override from the panel (overrides actual nature for the chosen stat)
    if nat_mult_override != 1.0:
        if use_sp:
            if nat_mult_override > 1.0:
                nature_en = "Modest"
            elif nat_mult_override < 1.0:
                nature_en = "Mild"
        else:
            if nat_mult_override > 1.0:
                nature_en = "Adamant"
            elif nat_mult_override < 1.0:
                nature_en = "Lonely"

    evs = {
        "hp":  p.ev_hp,
        "atk": p.ev_attack,
        "def": p.ev_defense,
        "spa": p.ev_sp_attack,
        "spd": p.ev_sp_defense,
        "spe": p.ev_speed,
    }
    if ev_override:
        evs.update(ev_override)

    ivs = {"hp": 31, "atk": 31, "def": 31, "spa": 31, "spd": 31, "spe": 31}

    boosts: dict[str, int] = {}
    if atk_rank != 0:
        if apply_both:
            boosts["atk"] = atk_rank
            boosts["spa"] = atk_rank
        else:
            boosts["atk" if not use_sp else "spa"] = atk_rank

    tera_en = TYPE_TO_SMOGON.get(terastal_type, "")
    terastal_active = bool(terastal_type)

    ability_en = _ability_name_to_en(p.ability, p.name_ja, terastal_active) or "No Ability"
    result = {
        "species":  smogon_mega_species(p.name_en, p.name_ja) or p.name_ja or "Bulbasaur",
        "level":    p.level,
        "nature":   nature_en,
        "evs":      evs,
        "ivs":      ivs,
        "ability":  ability_en,
        "item":     _item_name_to_en(p.item),
        "status":   p.status or "",
        "teraType": tera_en,
        "boosts":   boosts,
    }
    if p.current_hp > 0:
        result["curHP"] = int(p.current_hp)
    if allies_fainted > 0:
        result["alliesFainted"] = int(allies_fainted)
    if gender in ("M", "F", "N"):
        result["gender"] = gender
    if ability_on:
        result["abilityOn"] = True
    if ability_en in ("Protosynthesis", "Quark Drive"):
        result["boostedStat"] = "auto"
    return result


def defender_scenario_dict(
    species_name_en: str,
    ev_hp: int,
    ev_def: int,
    ev_spd: int,
    nature_en: str = "Hardy",
    ability_en: str = "",
    item_en: str = "",
    terastal_type: str = "",
    def_rank: int = 0,
    is_physical: bool = True,
    gender: str = "",
    apply_both: bool = False,
) -> dict:
    """Build a fixed-EV defender scenario dict (HBD0 / HBD32)."""
    tera_en = TYPE_TO_SMOGON.get(terastal_type, "")
    boosts: dict[str, int] = {}
    if def_rank != 0:
        if apply_both:
            boosts["def"] = def_rank
            boosts["spd"] = def_rank
        else:
            boosts["def" if is_physical else "spd"] = def_rank

    result = {
        "species":  _normalize_smogon_species(species_name_en) or "Bulbasaur",
        "level":    50,
        "nature":   nature_en,
        "evs":      {"hp": ev_hp, "atk": 0, "def": ev_def, "spa": 0, "spd": ev_spd, "spe": 0},
        "ivs":      {"hp": 31, "atk": 31, "def": 31, "spa": 31, "spd": 31, "spe": 31},
        "ability":  ability_en or "No Ability",
        "item":     item_en,
        "status":   "",
        "teraType": tera_en,
        "boosts":   boosts,
    }
    if gender in ("M", "F", "N"):
        result["gender"] = gender
    if ability_en in ("Protosynthesis", "Quark Drive"):
        result["boostedStat"] = "auto"
    return result


def attacker_scenario_dict(
    species_name_en: str,
    ev_hp: int,
    ev_atk: int,
    ev_spa: int,
    nature_en: str = "Hardy",
    ability_en: str = "",
    item_en: str = "",
    atk_rank: int = 0,
    is_physical: bool = True,
    terastal_type: str = "",
    allies_fainted: int = 0,
    ability_on: bool = False,
    gender: str = "",
    apply_both: bool = False,
) -> dict:
    """Build a fixed-EV attacker scenario dict (AC0 / AC32)."""
    boosts: dict[str, int] = {}
    if atk_rank != 0:
        if apply_both:
            boosts["atk"] = atk_rank
            boosts["spa"] = atk_rank
        else:
            boosts["atk" if is_physical else "spa"] = atk_rank

    tera_en = TYPE_TO_SMOGON.get(terastal_type, "")
    result = {
        "species":  _normalize_smogon_species(species_name_en) or "Bulbasaur",
        "level":    50,
        "nature":   nature_en,
        "evs":      {"hp": ev_hp, "atk": ev_atk, "def": 0, "spa": ev_spa, "spd": 0, "spe": 0},
        "ivs":      {"hp": 31, "atk": 31, "def": 31, "spa": 31, "spd": 31, "spe": 31},
        "ability":  ability_en or "No Ability",
        "item":     item_en,
        "status":   "",
        "teraType": tera_en,
        "boosts":   boosts,
    }
    if allies_fainted > 0:
        result["alliesFainted"] = int(allies_fainted)
    if ability_on:
        result["abilityOn"] = True
    if gender in ("M", "F", "N"):
        result["gender"] = gender
    if ability_en in ("Protosynthesis", "Quark Drive"):
        result["boostedStat"] = "auto"
    return result


def pokemon_to_defender_dict(p: PokemonInstance, def_rank: int = 0,
                              is_physical: bool = True, gender: str = "",
                              apply_both: bool = False) -> dict:
    """Build custom defender dict from actual PokemonInstance."""
    tera_en = TYPE_TO_SMOGON.get(p.terastal_type or "", "")
    boosts: dict[str, int] = {}
    if def_rank != 0:
        if apply_both:
            boosts["def"] = def_rank
            boosts["spd"] = def_rank
        else:
            boosts["def" if is_physical else "spd"] = def_rank

    ability_en = _ability_name_to_en(
        p.ability or "",
        p.name_ja or "",
        bool(p.terastal_type),
    ) or "No Ability"
    result = {
        "species":  smogon_mega_species(p.name_en, p.name_ja) or p.name_ja or "Bulbasaur",
        "level":    p.level,
        "nature":   nature_ja_to_en(p.nature),
        "evs": {
            "hp":  p.ev_hp,
            "atk": p.ev_attack,
            "def": p.ev_defense,
            "spa": p.ev_sp_attack,
            "spd": p.ev_sp_defense,
            "spe": p.ev_speed,
        },
        "ivs": {"hp": 31, "atk": 31, "def": 31, "spa": 31, "spd": 31, "spe": 31},
        "ability":  ability_en,
        "item":     _item_name_to_en(p.item or ""),
        "status":   "",
        "teraType": tera_en,
        "boosts":   boosts,
    }
    if gender in ("M", "F", "N"):
        result["gender"] = gender
    if ability_en in ("Protosynthesis", "Quark Drive"):
        result["boostedStat"] = "auto"
    return result


def move_to_dict(
    move: MoveInfo,
    is_crit: bool = False,
    hits: int = 0,
    bp_override: int = 0,
    atk_type_override: str = "",
    charged: bool = False,
    forced_type: str = "",
    bp_multiplier: float = 1.0,
) -> dict:
    """Build move descriptor for the bridge."""
    overrides: dict = {}

    # Power override (variable-power moves / user spinbox)
    final_bp = bp_override if bp_override > 0 else 0
    if final_bp > 0:
        overrides["basePower"] = final_bp
        if move.name_ja in _FORCE_FIXED_BP_OVERRIDE_MOVES_JA:
            # Special BP moves are recomputed internally by move name.
            # Override the display name to bypass name-based dynamic BP logic.
            overrides["name"] = "{} (Fixed BP)".format(move.name_en or move.name_ja)

    effective_type_for_charge = forced_type or atk_type_override or move.type_name

    # (Charge): doubles electric move power
    if charged and effective_type_for_charge == "electric":
        base = final_bp if final_bp > 0 else move.power
        overrides["basePower"] = base * 2

    # Attack type override (manual / derived)
    final_type_override = forced_type or atk_type_override
    if final_type_override:
        smogon_type = TYPE_TO_SMOGON.get(final_type_override, "")
        if smogon_type:
            overrides["type"] = smogon_type

    if bp_multiplier != 1.0:
        base = int(overrides.get("basePower", move.power))
        overrides["basePower"] = max(1, math.floor(base * float(bp_multiplier)))

    d: dict = {
        "name":   move.name_en or move.name_ja,
        "isCrit": is_crit,
    }
    if hits > 1:
        d["hits"] = hits
    if overrides:
        d["overrides"] = overrides
    return d


def field_to_dict(
    weather: str = "none",
    terrain: str = "none",
    reflect: bool = False,
    lightscreen: bool = False,
    helping_hand: bool = False,
    fairy_aura: bool = False,
    dark_aura: bool = False,
    friend_guard: bool = False,
    tailwind: bool = False,
    gravity: bool = False,
) -> dict:
    return {
        "weather":     weather if weather != "none" else "",
        "terrain":     terrain if terrain != "none" else "",
        "reflect":     reflect,
        "lightScreen": lightscreen,
        "helpingHand": helping_hand,
        "friendGuard": friend_guard,
        "tailwind":    tailwind,
        "isGravity":   gravity,
        "isFairyAura": fairy_aura,
        "isDarkAura":  dark_aura,
    }
