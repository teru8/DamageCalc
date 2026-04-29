"""
Scrapes pokechamdb.com for Pokemon Champions usage data.

Stored data:
- Pokemon usage ranking
- Move usage per Pokemon
- Ability usage per Pokemon
- Item usage per Pokemon
- Nature usage per Pokemon
- Effort-point spread usage per Pokemon
"""
from __future__ import annotations

import html
import json
import random
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from src.constants import ABILITIES_JA, ITEMS_JA, NATURES_JA
from src.data import database as db
from src.data.item_catalog import get_item_names

POKECHAMDB_BASE = "https://pokechamdb.com"
POKECHAMDB_DEFAULT_SEASON = db.DEFAULT_USAGE_SEASON
POKECHAMDB_FORMAT = "single"

POKEDB_TOKYO_BASE = "https://champs.pokedb.tokyo"

# 使用可能なデータ源
USAGE_SOURCES = {
    "pokechamdb": "pokechamdb.com",
    "pokedb_tokyo": "pokedb.tokyo（シングル）",
}
USAGE_SOURCE_DEFAULT = "pokechamdb"

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

_SESSION = requests.Session()

if getattr(sys, "frozen", False):
    # ビルド版: 実行ファイルと同じ場所
    _LOG_FILE = Path(sys.executable).parent / "usage_scraper.log"
else:
    # 開発環境: プロジェクトルート
    _LOG_FILE = Path(__file__).parent.parent.parent / "usage_scraper.log"

_SLUG_LINK_RE = re.compile(
    r"/pokemon/([a-z0-9][a-z0-9-]*)\?season=([^\"&<]+)"
)
_H1_NAME_RE = re.compile(r"<h1\b[^>]*>([^<]+)</h1>", re.IGNORECASE)
_RSC_ID_RE = re.compile(r"_rsc=([a-z0-9]+)")
_UL_RE = re.compile(r"<ul\b[^>]*>(.*?)</ul>", re.IGNORECASE | re.DOTALL)
_LI_RE = re.compile(r"<li\b[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_USAGE_RE = re.compile(r"(\d+(?:\.\d+)?)%")
_RSC_ENTRY_RE = re.compile(
    r'"name":"((?:\\.|[^"])*)".*?"usage":(\d+(?:\.\d+)?)',
    re.DOTALL,
)
_NEXT_PUSH_RE = re.compile(r"self\.__next_f\.push\((.*?)\)</script>", re.DOTALL)

_SECTION_SPECS = {
    "move": {
        "anchors": (">MOVES<", ">わざ<"),
        "rsc_keys": ("moves",),
        "allow_raw": False,
    },
    "ability": {
        "anchors": (">ABILITY<", ">ABILITIES<", ">とくせい<"),
        "rsc_keys": ("abilities",),
        "allow_raw": True,
    },
    "item": {
        "anchors": (">ITEMS<", ">もちもの<"),
        "rsc_keys": ("items",),
        "allow_raw": True,
    },
    "nature": {
        "anchors": (">NATURE<", ">せいかく<"),
        "rsc_keys": ("natures", "nature"),
        "allow_raw": False,
    },
}
_SECTION_ICON_LABEL = {
    "move": "MOVES",
    "ability": "ABILITY",
    "item": "ITEMS",
    "nature": "NATURE",
}

_SLUG_FORM_SUFFIX_TOKENS = {
    "male",
    "female",
    "hisui",
    "alola",
    "galar",
    "paldea",
    "blaze",
    "aqua",
    "combat",
    "shield",
    "blade",
    "breed",
    "disguised",
    "busted",
    "full",
    "belly",
    "hangry",
    "average",
    "small",
    "large",
    "super",
    "midday",
    "midnight",
    "dusk",
    "family",
    "of",
    "three",
    "four",
    "zero",
    "hero",
    "eternal",
    "rainy",
    "snowy",
    "sunny",
    "heat",
    "wash",
    "frost",
    "fan",
    "mow",
    "incarnate",
    "therian",
    "ordinary",
    "resolute",
    "aria",
    "pirouette",
    "attack",
    "defense",
    "speed",
    "school",
    "solo",
    "amped",
    "key",
    "low",
    "origin",
    "land",
    "sky",
    "crowned",
    "x",
    "y",
}


def _expand_slug_aliases(slug: str) -> set[str]:
    base = (slug or "").strip().lower()
    if not base:
        return set()

    variants: set[str] = {base, base.replace("-", "")}
    parts = [p for p in base.split("-") if p]
    while len(parts) > 1 and parts[-1] in _SLUG_FORM_SUFFIX_TOKENS:
        parts = parts[:-1]
        trunk = "-".join(parts)
        if not trunk:
            break
        variants.add(trunk)
        variants.add(trunk.replace("-", ""))

    for suffix in ("alola", "galar", "hisui", "paldea", "eternal"):
        variants.add("{}-{}".format(base, suffix))

    if base.startswith("rotom"):
        for form in ("heat", "wash", "frost", "fan", "mow"):
            variants.add("rotom-{}".format(form))
    if base.startswith("lycanroc"):
        variants.update({"lycanroc", "lycanroc-midday", "lycanroc-midnight", "lycanroc-dusk"})
    if base.startswith("maushold"):
        variants.update({"maushold", "maushold-family-of-three", "maushold-family-of-four"})
    if base.startswith("morpeko"):
        variants.update({"morpeko", "morpeko-full-belly", "morpeko-hangry"})
    if base.startswith("basculegion"):
        variants.update({"basculegion", "basculegion-male", "basculegion-female"})
    if base.startswith("palafin"):
        variants.update({"palafin", "palafin-zero", "palafin-hero"})
    if base.startswith("meowstic"):
        variants.update({"meowstic", "meowstic-male", "meowstic-female"})
    if base == "tauros":
        variants.update({"tauros-paldea-aqua", "tauros-paldea-blaze", "tauros-paldea-combat"})

    expanded: set[str] = set()
    for token in variants:
        token = token.strip("-")
        if not token:
            continue
        expanded.add(token)
        expanded.add(token.replace("-", ""))
        if token.endswith("-male"):
            expanded.add("{}-female".format(token[:-5]))
        if token.endswith("-female"):
            expanded.add("{}-male".format(token[:-7]))
        if token.endswith("-m"):
            expanded.add("{}-f".format(token[:-2]))
            expanded.add("{}female".format(token[:-2]))
        if token.endswith("-f"):
            expanded.add("{}-m".format(token[:-2]))
            expanded.add("{}male".format(token[:-2]))
    return expanded


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        item = item.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _extract_balanced_fragment(text: str, start: int, open_char: str, close_char: str) -> str:
    if start < 0 or start >= len(text) or text[start] != open_char:
        return ""
    depth = 0
    in_str = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == open_char:
            depth += 1
            continue
        if ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return ""


def _extract_next_payload_text(detail_text: str) -> str:
    parts: list[str] = []
    for match in _NEXT_PUSH_RE.finditer(detail_text):
        raw = match.group(1).strip()
        if raw.endswith(");"):
            raw = raw[:-2]
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], str):
            parts.append(payload[1])
    return "\n".join(parts)


def _slugify_name_en(name_en: str) -> str:
    text = (name_en or "").strip().lower()
    if not text:
        return ""
    text = text.replace("♀", "-f").replace("♂", "-m")
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _get_slug_to_ja() -> dict[str, str]:
    entries = db.get_all_species_name_entries()
    slug_map: dict[str, str] = {}
    for _, name_ja, name_en in entries:
        base_slug = _slugify_name_en(name_en)
        if not base_slug:
            continue
        for variant in _expand_slug_aliases(base_slug):
            if variant in slug_map and slug_map[variant] != name_ja:
                continue
            slug_map[variant] = name_ja
    return slug_map


def _fetch_text(url: str, retries: int = 3, retry_delay: float = 2.0) -> str | None:
    for attempt in range(retries + 1):
        try:
            headers = {"User-Agent": random.choice(_USER_AGENTS)}
            response = _SESSION.get(url, timeout=15, headers=headers)
            if response.status_code == 429:
                if attempt < retries:
                    delay = (retry_delay * (2 ** attempt)) + random.uniform(0, 1)
                    time.sleep(delay)
                    continue
                return None
            response.raise_for_status()
            return response.text
        except Exception as e:
            if attempt < retries:
                delay = (retry_delay * (2 ** attempt)) + random.uniform(0, 1)
                time.sleep(delay)
            else:
                return None
    return None


def _extract_latest_rsc_id(home_text: str) -> str | None:
    match = _RSC_ID_RE.search(home_text)
    return match.group(1) if match else None


def _extract_ranked_slugs(home_text: str) -> list[tuple[str, str]]:
    """Return list of (slug, season) tuples in ranking order."""
    results: list[tuple[str, str]] = []
    
    # Try to extract from JSON data embedded in HTML
    # Pattern matches: pokemonSlug\":\"slug\" (with any trailing characters)
    json_pattern = r'pokemonSlug\\":\\"([a-z0-9][a-z0-9-]*)'
    json_matches = re.findall(json_pattern, home_text, re.IGNORECASE)
    
    if json_matches:
        for slug in json_matches:
            results.append((slug, POKECHAMDB_DEFAULT_SEASON))
        _log(f"[UsageScraper] Extracted {len(results)} slugs from JSON data")
        return results
    
    _log("[UsageScraper] JSON pattern not matched, falling back to link extraction")
    
    # Fallback to link extraction
    seen: set[str] = set()
    candidates = _SLUG_LINK_RE.findall(home_text)
    if candidates:
        for slug, season in candidates:
            season = season.strip()
            if slug in seen:
                continue
            seen.add(slug)
            results.append((slug, season))
    else:
        for slug in re.findall(r"/pokemon/([a-z0-9][a-z0-9-]*)", home_text):
            if slug in seen:
                continue
            seen.add(slug)
            results.append((slug, POKECHAMDB_DEFAULT_SEASON))
    return results


def _build_detail_url(slug: str, season: str = POKECHAMDB_DEFAULT_SEASON, rsc_id: str | None = None) -> str:
    url = "{}/pokemon/{}?season={}&format={}".format(
        POKECHAMDB_BASE, slug, season, POKECHAMDB_FORMAT,
    )
    if rsc_id:
        return "{}&_rsc={}".format(url, rsc_id)
    return url


def _extract_page_pokemon_name_ja(page_text: str) -> str:
    """Extract Pokemon Japanese name from a pokechamdb detail page's H1 tag."""
    match = _H1_NAME_RE.search(page_text)
    if match:
        name = html.unescape(match.group(1)).strip()
        if name:
            return name
    return ""


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:1024].lower()
    return head.startswith("<!doctype html") or "<html" in head or "<head" in head


def _strip_tags(fragment: str) -> str:
    text = html.unescape(_TAG_RE.sub(" ", fragment))
    return _WS_RE.sub(" ", text).strip()


def _parse_usage_percent(text: str) -> float | None:
    match = _USAGE_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _decode_json_string(value: str) -> str:
    try:
        return json.loads('"{}"'.format(value))
    except Exception:
        return value.replace('\\"', '"')


def _match_known_name(text: str, ordered_names: list[str]) -> str | None:
    for name in ordered_names:
        if name and name in text:
            return name
    return None


def _guess_raw_name(text: str) -> str:
    cleaned = _USAGE_RE.sub("", text)
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    return cleaned


def _extract_rows_from_ul_html(
    ul_html: str,
    ordered_names: list[str],
    allow_raw: bool,
) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    seen: set[str] = set()

    for li_html in _LI_RE.findall(ul_html):
        li_text = _strip_tags(li_html)
        usage = _parse_usage_percent(li_text)
        if usage is None:
            continue

        name = _match_known_name(li_text, ordered_names)
        if not name and allow_raw:
            name = _guess_raw_name(li_text)
        if not name or name in seen:
            continue

        seen.add(name)
        rows.append((name, usage))

    rows.sort(key=lambda item: item[1], reverse=True)
    return rows


def _extract_rows_from_html_section(
    detail_text: str,
    anchors: tuple[str, ...],
    ordered_names: list[str],
    allow_raw: bool,
) -> list[tuple[str, float]]:
    for anchor in anchors:
        index = detail_text.find(anchor)
        if index < 0:
            continue
        fragment = detail_text[index:index + 20000]
        match = _UL_RE.search(fragment)
        if not match:
            continue
        rows = _extract_rows_from_ul_html(match.group(1), ordered_names, allow_raw)
        if rows:
            return rows
    return []


def _extract_rows_from_rsc_section(
    detail_text: str,
    expected_name_ja: str,
    rsc_keys: tuple[str, ...],
    ordered_names: list[str],
    allow_raw: bool,
) -> list[tuple[str, float]]:
    expected_marker = json.dumps(expected_name_ja, ensure_ascii=False)[1:-1]
    best_rows: list[tuple[str, float]] = []
    best_score = (-1, -1)

    for key in rsc_keys:
        section_re = re.compile(r'"{}":\[(.*?)\]'.format(re.escape(key)), re.DOTALL)
        for match in section_re.finditer(detail_text):
            fragment = match.group(1)
            rows: list[tuple[str, float]] = []
            seen: set[str] = set()
            for raw_name, raw_usage in _RSC_ENTRY_RE.findall(fragment):
                name_text = _decode_json_string(raw_name)
                name = _match_known_name(name_text, ordered_names)
                if not name and allow_raw:
                    name = _guess_raw_name(name_text)
                if not name or name in seen:
                    continue
                seen.add(name)
                try:
                    usage = float(raw_usage)
                except ValueError:
                    continue
                rows.append((name, usage))

            if not rows:
                continue

            rows.sort(key=lambda item: item[1], reverse=True)
            context = detail_text[max(0, match.start() - 600):match.start()]
            score = (1 if expected_marker and expected_marker in context else 0, len(rows))
            if score > best_score:
                best_score = score
                best_rows = rows

    return best_rows


def _extract_rows_from_next_section(
    detail_text: str,
    section: str,
    ordered_names: list[str],
    allow_raw: bool,
) -> list[tuple[str, float]]:
    payload = _extract_next_payload_text(detail_text)
    if not payload:
        return []
    icon_label = _SECTION_ICON_LABEL.get(section, "")
    if not icon_label:
        return []

    marker = '"iconLabel":"{}"'.format(icon_label)
    marker_idx = payload.find(marker)
    if marker_idx < 0:
        return []
    start = payload.rfind("{", 0, marker_idx)
    if start < 0:
        return []

    obj_txt = _extract_balanced_fragment(payload, start, "{", "}")
    if not obj_txt:
        return []
    try:
        section_obj = json.loads(obj_txt)
    except Exception:
        return []

    display_names = section_obj.get("displayNames", {}) if isinstance(section_obj, dict) else {}
    entries = section_obj.get("entries", []) if isinstance(section_obj, dict) else []
    rows: list[tuple[str, float]] = []
    seen: set[str] = set()

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_name = str(entry.get("name") or "").strip()
        if not raw_name:
            continue
        normalized_name = display_names.get(raw_name, raw_name) if isinstance(display_names, dict) else raw_name
        name = _match_known_name(normalized_name, ordered_names)
        if not name and allow_raw:
            name = _guess_raw_name(normalized_name)
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            usage = float(entry.get("percentage", 0) or 0)
        except Exception:
            usage = 0.0
        rows.append((name, usage))

    rows.sort(key=lambda item: item[1], reverse=True)
    return rows


def _extract_effort_rows_from_next(detail_text: str) -> list[tuple[int, int, int, int, int, int, int, float]]:
    payload = _extract_next_payload_text(detail_text)
    if not payload:
        return []
    marker = "能力ポイント 人気配分ランキング"
    marker_idx = payload.find(marker)
    if marker_idx < 0:
        return []

    fragment = payload[marker_idx: marker_idx + 80000]
    rows: list[tuple[int, int, int, int, int, int, int, float]] = []
    pos = 0
    while True:
        start = fragment.find('["$","tr","', pos)
        if start < 0:
            break
        arr_txt = _extract_balanced_fragment(fragment, start, "[", "]")
        if not arr_txt:
            break
        pos = start + len(arr_txt)
        try:
            row_data = json.loads(arr_txt)
        except Exception:
            continue
        if (
            not isinstance(row_data, list)
            or len(row_data) < 4
            or row_data[0] != "$"
            or row_data[1] != "tr"
            or not isinstance(row_data[3], dict)
        ):
            continue
        try:
            rank = int(row_data[2])
        except Exception:
            continue
        children = row_data[3].get("children", [])
        if not isinstance(children, list):
            continue

        values: list[int] = []
        usage_percent: float | None = None
        valid = True
        for cell in children:
            if isinstance(cell, str):
                # "$L22" 参照が混ざる行は数値が欠けるためスキップ。
                valid = False
                break
            if not (isinstance(cell, list) and len(cell) >= 4 and isinstance(cell[3], dict)):
                valid = False
                break
            cell_value = cell[3].get("children")
            if isinstance(cell_value, (int, float)):
                values.append(int(cell_value))
                continue
            if isinstance(cell_value, list) and cell_value:
                try:
                    usage_percent = float(cell_value[0])
                except Exception:
                    usage_percent = None
                continue
            valid = False
            break
        if not valid or len(values) < 7 or usage_percent is None:
            continue
        rows.append(
            (
                rank,
                values[1],  # hp
                values[2],  # attack
                values[3],  # defense
                values[4],  # sp_attack
                values[5],  # sp_defense
                values[6],  # speed
                usage_percent,
            )
        )
    rows.sort(key=lambda row: row[0])
    return rows


def _extract_section_rows(
    detail_text: str,
    expected_name_ja: str,
    section: str,
    ordered_names: list[str],
) -> list[tuple[str, float]]:
    spec = _SECTION_SPECS[section]
    rows: list[tuple[str, float]] = []
    if _looks_like_html(detail_text):
        rows = _extract_rows_from_html_section(
            detail_text,
            spec["anchors"],
            ordered_names,
            spec["allow_raw"],
        )
    if not rows:
        rows = _extract_rows_from_rsc_section(
            detail_text,
            expected_name_ja,
            spec["rsc_keys"],
            ordered_names,
            spec["allow_raw"],
        )
    if not rows:
        rows = _extract_rows_from_next_section(
            detail_text,
            section,
            ordered_names,
            spec["allow_raw"],
        )
    return rows


def _filter_slug_pairs_by_season(
    slug_season_pairs: list[tuple[str, str]],
    season: str,
) -> list[tuple[str, str]]:
    season_token = db.normalize_season_token(season)
    if not slug_season_pairs:
        return []
    filtered = [
        (slug, db.normalize_season_token(pair_season))
        for slug, pair_season in slug_season_pairs
        if db.normalize_season_token(pair_season) == season_token
    ]
    if filtered:
        return filtered
    # Fallback: keep ranking order from current page, force requested season.
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for slug, _ in slug_season_pairs:
        if slug in seen:
            continue
        seen.add(slug)
        result.append((slug, season_token))
    return result


# 図鑑番号+フォルム番号 → アプリ内日本語名のマッピング
# 体系：
#   オス/メス形 → 「(オスのすがた)」「(メスのすがた)」
#   地方フォルム（アローラ/ガラル/ヒスイ） → 「地方名+種名」
#   パルデアケンタロス → 「パルデアケンタロス(タイプ)」
#   ルガルガン時間フォルム → 「ルガルガン(XXのすがた)」
# pokechamdb ページ表記 → 正規アプリ名（半角括弧）変換テーブル
_POKECHAMDB_NAME_MAP: dict[str, str] = {
    "フラエッテ(えいえん)":           "フラエッテ (えいえんのはな)",
    "フラエッテ (えいえん)":          "フラエッテ (えいえんのはな)",
    "パルデアケンタロス（コンバット）": "パルデアケンタロス(格闘)",
    "パルデアケンタロス（ブレイズ）":  "パルデアケンタロス(炎)",
    "パルデアケンタロス（アクア）":    "パルデアケンタロス(水)",
}


def _normalize_pokechamdb_name(name_ja: str) -> str:
    """pokechamdb ページ名を正規アプリ名（半角括弧）に変換する。"""
    normalized = _POKECHAMDB_NAME_MAP.get(name_ja)
    if normalized:
        return normalized
    hw = name_ja.replace("（", "(").replace("）", ")")
    return _POKECHAMDB_NAME_MAP.get(hw, hw)


# 個別指定が必要なフォーム（汎用ルールでは対応できないもの）
_POKEDB_FORM_MAP: dict[str, str] = {
    "0670-05": "フラエッテ (えいえんのはな)",
    "0745-00": "ルガルガン(まひるのすがた)",
    "0745-01": "ルガルガン(まよなかのすがた)",
    "0745-02": "ルガルガン(たそがれのすがた)",
    "0128-01": "パルデアケンタロス(格闘)",
    "0128-02": "パルデアケンタロス(炎)",
    "0128-03": "パルデアケンタロス(水)",
    "0711-00": "パンプジン(ちゅうだましゅ)",
    "0711-01": "パンプジン(こだましゅ)",
    "0711-02": "パンプジン(おおだましゅ)",
    "0711-03": "パンプジン(ギガだましゅ)",
}

# 地方フォーム接頭辞: 「XX (ガラル)」→「ガラルXX」
_REGION_PREFIX_MAP: dict[str, str] = {
    "アローラ": "アローラ",
    "ガラル": "ガラル",
    "ヒスイ": "ヒスイ",
    "パルデア": "パルデア",
}

# パンプジン図鑑番号（サイズ形は個別対応）
_PUMPKABOO_IDS = {"0710", "0711"}


def _resolve_pokedb_name(form_id: str, breadcrumb_name: str) -> str:
    """Resolve app-side Japanese name from form_id and breadcrumb name.

    Priority:
    1. Exact match in _POKEDB_FORM_MAP → mapped name
    2. Breadcrumb suffix「 (オス)」→「(オスのすがた)」,「 (メス)」→「(メスのすがた)」
    3. Breadcrumb suffix「 (地方名)」→「地方名 + 本体名」
    4. breadcrumb_name as-is
    """
    if form_id in _POKEDB_FORM_MAP:
        return _POKEDB_FORM_MAP[form_id]

    name = breadcrumb_name.strip()

    # 「XX (オス)」「XX (メス)」→「XX(オスのすがた)」「XX(メスのすがた)」
    m = re.match(r"^(.+?)\s*\(([オメ][スス])\)$", name)
    if m:
        base, gender = m.group(1).strip(), m.group(2)
        return f"{base}({gender}のすがた)"

    # 「XX (地方名)」→「地方名XX」
    m = re.match(r"^(.+?)\s*\((.+?)\)$", name)
    if m:
        base, suffix = m.group(1).strip(), m.group(2).strip()
        if suffix in _REGION_PREFIX_MAP:
            return f"{_REGION_PREFIX_MAP[suffix]}{base}"

    return name


def _supplement_ev(ev: dict[str, int], species_id: int) -> dict[str, int]:
    """Fill remaining EV points (up to total 66) by priority rules.

    Rules (applied in order until remainder is consumed):
    1. S < 32 → add remainder to S
    2. H < 32 → add remainder to H
    3. H=32, S=32 → add to A or C, whichever base stat is higher
    """
    total = sum(ev.values())
    remainder = 66 - total
    if remainder <= 0:
        return ev

    ev = dict(ev)
    if ev.get("S", 0) < 32:
        ev["S"] = ev.get("S", 0) + remainder
    elif ev.get("H", 0) < 32:
        ev["H"] = ev.get("H", 0) + remainder
    else:
        species = db.get_species_by_id(species_id)
        if species and species.base_sp_attack > species.base_attack:
            ev["C"] = ev.get("C", 0) + remainder
        else:
            ev["A"] = ev.get("A", 0) + remainder
    return ev


def _log(message: str) -> None:
    """Write log message to file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(message)  # Also print to console


def _scrape_usage(
    scraper: UsageScraper | None = None,
    season: str = POKECHAMDB_DEFAULT_SEASON,
) -> dict[str, list[tuple]]:
    season_token = db.normalize_season_token(season)
    
    # Add session separator to log
    _log("=" * 60)
    _log(f"Starting usage data scraping for season: {season_token}")
    _log("=" * 60)
    
    slug_to_ja = _get_slug_to_ja()
    ordered_move_names = sorted(_unique(db.get_all_move_names_ja()), key=len, reverse=True)
    ordered_ability_names = sorted(_unique(list(ABILITIES_JA)), key=len, reverse=True)
    ordered_item_names = sorted(_unique(list(ITEMS_JA) + get_item_names()), key=len, reverse=True)
    ordered_nature_names = sorted(_unique(list(NATURES_JA.keys())), key=len, reverse=True)

    if not slug_to_ja or not ordered_move_names:
        _log("[ERROR] slug_to_ja or ordered_move_names is empty")
        return {}

    home_text = _fetch_text("{}/?view=pokemon".format(POKECHAMDB_BASE))
    if not home_text:
        _log("[ERROR] Failed to fetch home page")
        return {}
    
    # Debug: save home page HTML for inspection
    with open("debug_home_page.html", "w", encoding="utf-8") as f:
        f.write(home_text)
    _log("[DEBUG] Home page HTML saved to debug_home_page.html")

    rsc_id = _extract_latest_rsc_id(home_text)
    slug_season_pairs = _filter_slug_pairs_by_season(_extract_ranked_slugs(home_text), season_token)
    if not slug_season_pairs:
        return {}

    ranked_pokemon: list[tuple[str, int]] = []
    move_rows: list[tuple[str, str, int]] = []
    ability_rows: list[tuple[str, str, int]] = []
    item_rows: list[tuple[str, str, int]] = []
    nature_rows: list[tuple[str, str, int]] = []
    effort_rows: list[tuple[str, int, int, int, int, int, int, int, float]] = []

    mapped_slugs: list[tuple[str, str, str | None]] = []
    seen_pokemon: set[str] = set()
    failed_slugs: list[tuple[str, str, str]] = []  # (slug, season, reason)
    
    for slug, season in slug_season_pairs:
        name_ja = slug_to_ja.get(slug) or slug_to_ja.get(slug.replace("-", ""))
        mapped_slugs.append((slug, season, name_ja))

    total = len(mapped_slugs)
    for index, (slug, pair_season, name_ja_hint) in enumerate(mapped_slugs, start=1):
        if scraper is not None:
            scraper.progress.emit(
                int(index / max(total, 1) * 100),
                "使用率データ取得中[{}]: {}/{}".format(season_token, index, total),
            )

        if index > 1:
            time.sleep(10)

        detail_text = _fetch_text(_build_detail_url(slug, pair_season, rsc_id))
        if detail_text is None and rsc_id:
            detail_text = _fetch_text(_build_detail_url(slug, pair_season))
        if not detail_text:
            _log(f"[UsageScraper] Failed to fetch: {slug} (season: {pair_season})")
            failed_slugs.append((slug, pair_season, "fetch_failed"))
            continue

        # Prefer page H1 (actual displayed species/form) over slug-based guess.
        page_name_ja = _extract_page_pokemon_name_ja(detail_text)
        name_ja = page_name_ja or name_ja_hint or ""
        if not name_ja:
            _log(f"[UsageScraper] No name found: {slug} (page_name_ja: {page_name_ja}, hint: {name_ja_hint})")
            failed_slugs.append((slug, pair_season, "no_name"))
            continue

        # pokechamdb 表記を正規アプリ名に統一
        name_ja = _normalize_pokechamdb_name(name_ja)

        ranked_pokemon.append((name_ja, index))

        move_names = [name for name, _ in _extract_section_rows(detail_text, name_ja, "move", ordered_move_names)]
        ability_names = [name for name, _ in _extract_section_rows(detail_text, name_ja, "ability", ordered_ability_names)]
        item_names = [name for name, _ in _extract_section_rows(detail_text, name_ja, "item", ordered_item_names)]
        nature_names = [name for name, _ in _extract_section_rows(detail_text, name_ja, "nature", ordered_nature_names)]

        for rank, move_name in enumerate(move_names[:8], start=1):
            move_rows.append((name_ja, move_name, rank))
        for rank, ability_name in enumerate(ability_names[:4], start=1):
            ability_rows.append((name_ja, ability_name, rank))
        for rank, item_name in enumerate(item_names[:8], start=1):
            item_rows.append((name_ja, item_name, rank))
        for rank, nature_name in enumerate(nature_names[:4], start=1):
            nature_rows.append((name_ja, nature_name, rank))
        for effort in _extract_effort_rows_from_next(detail_text)[:10]:
            (
                effort_rank,
                hp_pt,
                attack_pt,
                defense_pt,
                sp_attack_pt,
                sp_defense_pt,
                speed_pt,
                usage_percent,
            ) = effort
            effort_rows.append(
                (
                    name_ja,
                    effort_rank,
                    hp_pt,
                    attack_pt,
                    defense_pt,
                    sp_attack_pt,
                    sp_defense_pt,
                    speed_pt,
                    usage_percent,
                )
            )
    
    # Retry failed slugs
    if failed_slugs:
        _log(f"[UsageScraper] Retrying {len(failed_slugs)} failed entries...")
        for retry_index, (slug, pair_season, reason) in enumerate(failed_slugs, start=1):
            if scraper is not None:
                scraper.progress.emit(
                    100,
                    "再試行中: {}/{} ({})".format(retry_index, len(failed_slugs), slug),
                )
            
            time.sleep(10)
            
            detail_text = _fetch_text(_build_detail_url(slug, pair_season, rsc_id))
            if detail_text is None and rsc_id:
                detail_text = _fetch_text(_build_detail_url(slug, pair_season))
            if not detail_text:
                _log(f"[UsageScraper] Retry failed: {slug} (reason: {reason})")
                continue
            
            page_name_ja = _extract_page_pokemon_name_ja(detail_text)
            name_ja = page_name_ja or slug_to_ja.get(slug) or slug_to_ja.get(slug.replace("-", "")) or ""
            if not name_ja:
                _log(f"[UsageScraper] Retry no name: {slug}")
                continue

            name_ja = _normalize_pokechamdb_name(name_ja)

            # Add to ranked_pokemon with original rank
            original_rank = next((i for i, (s, _, _) in enumerate(mapped_slugs, start=1) if s == slug), len(ranked_pokemon) + 1)
            ranked_pokemon.append((name_ja, original_rank))
            
            move_names = [name for name, _ in _extract_section_rows(detail_text, name_ja, "move", ordered_move_names)]
            ability_names = [name for name, _ in _extract_section_rows(detail_text, name_ja, "ability", ordered_ability_names)]
            item_names = [name for name, _ in _extract_section_rows(detail_text, name_ja, "item", ordered_item_names)]
            nature_names = [name for name, _ in _extract_section_rows(detail_text, name_ja, "nature", ordered_nature_names)]
            
            for rank, move_name in enumerate(move_names[:8], start=1):
                move_rows.append((name_ja, move_name, rank))
            for rank, ability_name in enumerate(ability_names[:4], start=1):
                ability_rows.append((name_ja, ability_name, rank))
            for rank, item_name in enumerate(item_names[:8], start=1):
                item_rows.append((name_ja, item_name, rank))
            for rank, nature_name in enumerate(nature_names[:4], start=1):
                nature_rows.append((name_ja, nature_name, rank))
            for effort in _extract_effort_rows_from_next(detail_text)[:10]:
                (
                    effort_rank,
                    hp_pt,
                    attack_pt,
                    defense_pt,
                    sp_attack_pt,
                    sp_defense_pt,
                    speed_pt,
                    usage_percent,
                ) = effort
                effort_rows.append(
                    (
                        name_ja,
                        effort_rank,
                        hp_pt,
                        attack_pt,
                        defense_pt,
                        sp_attack_pt,
                        sp_defense_pt,
                        speed_pt,
                        usage_percent,
                    )
                )
            _log(f"[UsageScraper] Retry success: {name_ja}")
        
        _log(f"[UsageScraper] Retry complete. Total: {len(ranked_pokemon)} pokemon")

    if not ranked_pokemon:
        return {}

    return {
        "season": season_token,
        "pokemon": ranked_pokemon,
        "moves": move_rows,
        "abilities": ability_rows,
        "items": item_rows,
        "natures": nature_rows,
        "efforts": effort_rows,
    }


def _scrape_usage_pokedb_tokyo(
    scraper: "UsageScraper | None" = None,
    season: str = POKECHAMDB_DEFAULT_SEASON,
) -> dict[str, list[tuple]]:
    """Scrape Pokemon Champions usage data from pokedb.tokyo.

    Returns a dict with pokemon rankings and move/ability/item/nature stats.
    """
    from bs4 import BeautifulSoup

    season_token = db.normalize_season_token(season)
    _log("=" * 60)
    _log(f"Starting pokedb.tokyo usage data scraping for season: {season_token}")
    _log("=" * 60)

    slug_to_ja = _get_slug_to_ja()
    ordered_move_names = sorted(_unique(db.get_all_move_names_ja()), key=len, reverse=True)
    ordered_ability_names = sorted(_unique(list(ABILITIES_JA)), key=len, reverse=True)
    ordered_item_names = sorted(_unique(list(ITEMS_JA) + get_item_names()), key=len, reverse=True)
    ordered_nature_names = sorted(_unique(list(NATURES_JA.keys())), key=len, reverse=True)

    if not slug_to_ja or not ordered_move_names:
        _log("[ERROR] slug_to_ja or ordered_move_names is empty")
        return {}

    # Fetch the list page
    list_url = f"{POKEDB_TOKYO_BASE}/pokemon/list?season=1&rule=0"
    list_html = _fetch_text(list_url)
    if not list_html:
        _log("[ERROR] Failed to fetch pokedb.tokyo list page")
        return {}

    soup = BeautifulSoup(list_html, "html.parser")

    # Find all Pokemon links on the list page
    pokemon_links = []
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "/pokemon/show/" in href:
            pokemon_links.append(href)

    if not pokemon_links:
        _log("[ERROR] No Pokemon links found on list page")
        return {}

    _log(f"Found {len(pokemon_links)} Pokemon links")

    ranked_pokemon: list[tuple[str, int]] = []
    move_rows: list[tuple[str, str, int]] = []
    ability_rows: list[tuple[str, str, int]] = []
    item_rows: list[tuple[str, str, int]] = []
    nature_rows: list[tuple[str, str, int]] = []
    effort_rows: list[tuple[str, int, int, int, int, int, int, int, float]] = []

    seen_pokemon: set[str] = set()

    for rank, link in enumerate(pokemon_links, start=1):
        detail_url = f"{POKEDB_TOKYO_BASE}{link}" if not link.startswith("http") else link
        detail_html = _fetch_text(detail_url)
        if not detail_html:
            _log(f"[WARN] Failed to fetch {detail_url}")
            continue

        detail_soup = BeautifulSoup(detail_html, "html.parser")

        # URL から図鑑番号+フォルム番号を取得
        form_id_m = re.search(r"/pokemon/show/(\d{4}-\d{2})", detail_url)
        form_id = form_id_m.group(1) if form_id_m else ""

        # ポケモン名：詳細ページのパンくずリスト最後の要素から取得
        lists_on_page = detail_soup.find_all(["ul", "ol"])
        breadcrumb_name = ""
        if lists_on_page:
            bc_items = lists_on_page[0].find_all("li")
            if bc_items:
                breadcrumb_name = bc_items[-1].get_text(strip=True)

        name_ja = _resolve_pokedb_name(form_id, breadcrumb_name)
        if not name_ja or name_ja in seen_pokemon:
            continue
        seen_pokemon.add(name_ja)

        ranked_pokemon.append((name_ja, rank))

        # CSS クラスで各セクションを取得
        moves_col = detail_soup.find(class_="pokemon-trend__moves")
        ab_col = detail_soup.find(class_="pokemon-trend__column-abilities")
        item_col = detail_soup.find(class_="pokemon-trend__column-items")
        nat_col = detail_soup.find(class_="pokemon-trend__column-personalities")
        stat_col = detail_soup.find(class_="pokemon-trend__column-stats")

        move_names = (
            [e.get_text(strip=True) for e in moves_col.find_all(class_="pokemon-trend__move-name")][:10]
            if moves_col else []
        )
        ability_names = _extract_col_items(ab_col, ordered_ability_names, limit=3) if ab_col else []
        item_names = _extract_col_items(item_col, ordered_item_names, limit=10) if item_col else []
        nature_names = _extract_col_items(nat_col, ordered_nature_names, limit=10) if nat_col else []

        for rank_inner, move_name in enumerate(move_names, start=1):
            move_rows.append((name_ja, move_name, rank_inner))
        for rank_inner, ability_name in enumerate(ability_names, start=1):
            ability_rows.append((name_ja, ability_name, rank_inner))
        for rank_inner, item_name in enumerate(item_names, start=1):
            item_rows.append((name_ja, item_name, rank_inner))
        for rank_inner, nature_name in enumerate(nature_names, start=1):
            nature_rows.append((name_ja, nature_name, rank_inner))

        # EV値（HABCDS形式で抽出 → 補完）
        if stat_col:
            ev = _extract_ev_pokedb(stat_col)
            if ev:
                species = db.get_species_by_name_ja(name_ja)
                species_id = species.species_id if species else 0
                ev = _supplement_ev(ev, species_id)
                effort_rows.append((
                    name_ja, 1,
                    ev.get("H", 0),
                    ev.get("A", 0),
                    ev.get("B", 0),
                    ev.get("C", 0),
                    ev.get("D", 0),
                    ev.get("S", 0),
                    0.0,
                ))

        _log(f"Processed {rank}: {name_ja}")

    _log(f"Scraped {len(ranked_pokemon)} Pokemon from pokedb.tokyo")

    return {
        "season": season_token,
        "pokemon": ranked_pokemon,
        "moves": move_rows,
        "abilities": ability_rows,
        "items": item_rows,
        "natures": nature_rows,
        "efforts": effort_rows,
    }


def _extract_ev_pokedb(stat_col: object) -> dict[str, int]:
    """Extract top EV spread from pokemon-trend__column-stats column.

    Returns dict in HABCDS format (e.g. {"A": 32, "S": 32}).
    Finds the first li matching "1AS78.6%A32S32..." and extracts the EV values.
    """
    for li in stat_col.find_all("li"):
        text = li.get_text(strip=True)
        if not re.match(r"^\d+[A-Z]", text):
            continue
        text = re.sub(r"^\d+", "", text)
        text = re.sub(r"^[A-Z]+[\d.]+%\s*", "", text)
        m = re.match(r"^((?:[HABCDS]\d+)+)", text)
        if m:
            return {k: int(v) for k, v in re.findall(r"([HABCDS])(\d+)", m.group(1))}
    return {}


def _clean_li_text(text: str) -> str:
    """Remove rank number, percentages, and parenthetical stat notes from li text."""
    text = re.sub(r"^\d+\s*", "", text)
    text = re.sub(r"\d+(?:\.\d+)?%", "", text)
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    return text.strip()


def _extract_col_items(
    col: object,
    ordered_names: list[str],
    limit: int,
) -> list[str]:
    """Extract item names from a pokemon-trend column using <li> elements."""
    raw = []
    for li in col.find_all("li")[:limit]:
        text = _clean_li_text(li.get_text(strip=True))
        if text:
            raw.append(text)

    matched = []
    for item in raw:
        found = _match_known_name(item, ordered_names)
        if found:
            matched.append(found)
    return matched if matched else raw


class UsageScraper(QThread):
    progress = pyqtSignal(int, str)   # (percent, message)
    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(
        self,
        season: str = POKECHAMDB_DEFAULT_SEASON,
        source: str = USAGE_SOURCE_DEFAULT,
    ):
        super().__init__()
        self.season = db.normalize_season_token(season)
        self.source = source

    def run(self) -> None:
        self.progress.emit(0, f"使用率データ取得を開始[{self.season}][{self.source}]")
        if self.source == "pokedb_tokyo":
            snapshot = _scrape_usage_pokedb_tokyo(self, season=self.season)
        else:
            snapshot = _scrape_usage(self, season=self.season)
        if snapshot:
            db.save_usage_snapshot(
                snapshot.get("pokemon", []),
                snapshot.get("moves", []),
                snapshot.get("abilities", []),
                snapshot.get("items", []),
                snapshot.get("natures", []),
                snapshot.get("efforts", []),
                season=self.season,
            )
            db.export_usage_to_json(self.season)
            self.finished.emit(
                True,
                "使用率データ取得[{}]: {}匹 / 技{}件 / 特性{}件 / 持ち物{}件 / 性格{}件 / 努力値{}件".format(
                    self.season,
                    len(snapshot.get("pokemon", [])),
                    len(snapshot.get("moves", [])),
                    len(snapshot.get("abilities", [])),
                    len(snapshot.get("items", [])),
                    len(snapshot.get("natures", [])),
                    len(snapshot.get("efforts", [])),
                ),
            )
        else:
            self.finished.emit(
                False,
                "使用率データの取得に失敗しました[{}]（ローカルキャッシュを継続使用）".format(self.season),
            )
