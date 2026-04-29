"""Shared UI utilities: local type icons and champion sprite loading."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from src.ui.pokemon_edit_dialog import PokemonEditDialog
    from src.models import PokemonInstance

_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"


def open_pokemon_edit_dialog(
    pokemon: "PokemonInstance | None",
    parent: QWidget | None,
    *,
    save_to_db: bool = True,
) -> "PokemonEditDialog":
    """PokemonEditDialogを生成してトップウィンドウにローディングオーバーレイを表示する。

    ダイアログの __init__ 中の画像読み込みで UIが固まらないよう、
    構築完了まで親ウィンドウを半透明でマスクする。
    """
    top: QWidget | None = parent.window() if parent else None
    overlay: QWidget | None = None

    if top:
        overlay = QWidget(top)
        overlay.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
        overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        overlay.setGeometry(top.rect())
        layout = QVBoxLayout(overlay)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel("読み込み中...")
        lbl.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        layout.addWidget(lbl)
        overlay.show()
        overlay.raise_()
        QApplication.processEvents()

    from src.ui.pokemon_edit_dialog import PokemonEditDialog

    dlg = PokemonEditDialog(pokemon, parent, save_to_db=save_to_db)

    if overlay:
        overlay.hide()
        overlay.deleteLater()

    return dlg
_ICONS_DIR = _ASSETS_DIR / "templates" / "icons"
_SPRITES_DIR = _ASSETS_DIR / "champions_menu_sprites"

_TYPE_PIXMAP_CACHE: dict[tuple[str, int, int], QPixmap | None] = {}
_SPRITE_PIXMAP_CACHE: dict[tuple[str, int, int | str], QPixmap | None] = {}
_SPRITE_BY_NAME_JA: dict[str, str] | None = None
_SPRITE_ENTRIES: list[dict] | None = None

def type_pixmap(type_name: str, width: int, height: int) -> QPixmap | None:
    """Return a QPixmap for the given type from local PNG/GIF assets, or None."""
    key = (type_name, width, height)
    if key in _TYPE_PIXMAP_CACHE:
        return _TYPE_PIXMAP_CACHE[key]
    pm: QPixmap | None = None
    for ext in ("gif", "png"):
        path = _ICONS_DIR / "{}.{}".format(type_name, ext)
        if path.exists():
            src = QPixmap(str(path))
            if not src.isNull():
                pm = src.scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                break
    _TYPE_PIXMAP_CACHE[key] = pm
    return pm


def _ensure_sprite_manifest() -> dict[str, str]:
    global _SPRITE_BY_NAME_JA
    if _SPRITE_BY_NAME_JA is not None:
        return _SPRITE_BY_NAME_JA
    _SPRITE_BY_NAME_JA = {}
    manifest_path = _SPRITES_DIR / "manifest.json"
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in data.get("entries", []):
                if entry.get("is_shiny") or entry.get("category") != "normal":
                    continue
                name_ja = entry.get("name_ja", "")
                local_path = entry.get("local_path", "")
                if not name_ja or not local_path:
                    continue
                is_base = not entry.get("form", "")
                if name_ja not in _SPRITE_BY_NAME_JA or is_base:
                    _SPRITE_BY_NAME_JA[name_ja] = local_path
        except Exception:
            pass
    return _SPRITE_BY_NAME_JA


def _load_sprite_entries() -> list[dict]:
    global _SPRITE_ENTRIES
    if _SPRITE_ENTRIES is not None:
        return _SPRITE_ENTRIES
    _SPRITE_ENTRIES = []
    manifest_path = _SPRITES_DIR / "manifest.json"
    if not manifest_path.exists():
        return _SPRITE_ENTRIES
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in data.get("entries", []):
            if row.get("is_shiny") or row.get("category") != "normal":
                continue
            local_path = str(row.get("local_path") or "").strip()
            if not local_path:
                continue
            _SPRITE_ENTRIES.append(
                {
                    "name_ja": str(row.get("name_ja") or "").strip(),
                    "name_en": str(row.get("name_en") or "").strip().lower(),
                    "form": str(row.get("form") or "").strip(),
                    "form_key": _norm_key(str(row.get("form") or "")),
                    "local_path": local_path,
                }
            )
    except Exception:
        _SPRITE_ENTRIES = []
    return _SPRITE_ENTRIES


def _norm_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").strip().lower())


def _norm_ja_name(name_ja: str) -> str:
    text = (name_ja or "").strip()
    text = re.sub(r"[（(].*?[)）]", "", text)
    text = text.replace("♂", "").replace("♀", "")
    return re.sub(r"\s+", "", text)


def _unique_texts(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = _norm_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _resolve_by_manifest(
    *,
    base_name_ja: str = "",
    base_name_en: str = "",
    desired_forms: list[str] | None = None,
) -> str:
    entries = _load_sprite_entries()
    if not entries:
        return ""

    base_ja = _norm_ja_name(base_name_ja)
    base_en = (base_name_en or "").strip().lower()

    candidates: list[dict] = []
    for row in entries:
        row_name_ja = _norm_ja_name(str(row.get("name_ja") or ""))
        row_name_en = str(row.get("name_en") or "").strip().lower()
        match_ja = bool(base_ja) and row_name_ja == base_ja
        match_en = bool(base_en) and row_name_en == base_en
        if match_ja or match_en:
            candidates.append(row)
    if not candidates:
        return ""

    want_forms = desired_forms or []
    want_keys = [_norm_key(f) for f in _unique_texts(want_forms)]
    if want_keys:
        # Exact single-key match
        for want_key in want_keys:
            for row in candidates:
                row_key = str(row.get("form_key") or "")
                if row_key == want_key:
                    return str(row.get("local_path") or "")
        # Compound match: all want_keys joined == row_key (e.g. ["paldea","combat"] → "paldeacombat")
        joined_key = "".join(want_keys)
        for row in candidates:
            row_key = str(row.get("form_key") or "")
            if row_key == joined_key:
                return str(row.get("local_path") or "")
        # Substring match: row_key contains all want_keys
        for row in candidates:
            row_key = str(row.get("form_key") or "")
            if row_key and all(k in row_key for k in want_keys):
                return str(row.get("local_path") or "")
        # Male often maps to base art; allow base fallback only for male.
        if "male" in want_keys:
            for row in candidates:
                if not str(row.get("form_key") or ""):
                    return str(row.get("local_path") or "")

    for row in candidates:
        if not str(row.get("form_key") or ""):
            return str(row.get("local_path") or "")
    return str(candidates[0].get("local_path") or "")


def _name_en_form_hints(name_en: str) -> tuple[str, list[str]]:
    normalized = (name_en or "").strip().lower()
    if not normalized:
        return "", []

    # Strip PokeAPI -breed suffix (e.g. tauros-paldea-combat-breed → tauros-paldea-combat)
    if normalized.endswith("-breed"):
        normalized = normalized[:-6]

    forms: list[str] = []
    base = normalized
    if normalized.startswith("mega-"):
        base = normalized[5:]
        forms.extend(["Mega"])
    elif "-mega-" in normalized:
        base, tail = normalized.split("-mega-", 1)
        if tail:
            forms.extend(["Mega {}".format(tail.replace("-", " ")), "Mega"])
        else:
            forms.extend(["Mega"])
    elif normalized.endswith("-mega"):
        base = normalized[:-5]
        forms.extend(["Mega"])
    elif "-" in normalized:
        head, tail = normalized.split("-", 1)
        base = head
        tail_text = tail.replace("-", " ")
        if tail_text:
            forms.append(tail_text)
        if tail in ("m", "male"):
            forms.append("Male")
        elif tail in ("f", "female"):
            forms.append("Female")

    # Smogon style for Basculegion male omits "-male".
    if base == "basculegion" and not forms:
        forms.append("Male")

    return base, forms


_JA_FORM_KEYWORD_MAP: list[tuple[str, str]] = [
    ("ヒスイのすがた", "Hisui"),
    ("ヒスイ", "Hisui"),
    ("ガラルのすがた", "Galar"),
    ("ガラル", "Galar"),
    ("アローラのすがた", "Alola"),
    ("アローラ", "Alola"),
    ("パルデアのすがた", "Paldea"),
    ("パルデア", "Paldea"),
    ("キョダイマックスのすがた", "Gigantamax"),
]


def _name_ja_form_hints(name_ja: str) -> tuple[str, list[str]]:
    text = (name_ja or "").strip()
    base = _norm_ja_name(text)
    forms: list[str] = []

    for prefix, en_form in (
        ("アローラ", "Alola"),
        ("ガラル", "Galar"),
        ("ヒスイ", "Hisui"),
        ("パルデア", "Paldea"),
    ):
        if text.startswith(prefix) and len(text) > len(prefix):
            forms.append(en_form)
            base = _norm_ja_name(text[len(prefix):])
            break

    if text.startswith("メガ"):
        trimmed = text[2:]
        if trimmed.endswith(("X", "Ｘ")):
            forms.append("Mega X")
            trimmed = trimmed[:-1]
        elif trimmed.endswith(("Y", "Ｙ")):
            forms.append("Mega Y")
            trimmed = trimmed[:-1]
        else:
            forms.append("Mega")
        base = _norm_ja_name(trimmed)

    if "ロトム" in text:
        base = "ロトム"
        if "ヒート" in text:
            forms.append("Heat")
        elif "ウォッシュ" in text:
            forms.append("Wash")
        elif "フロスト" in text:
            forms.append("Frost")
        elif "スピン" in text:
            forms.append("Fan")
        elif "カット" in text:
            forms.append("Mow")

    if "イダイトウ" in text:
        base = "イダイトウ"
        if "メス" in text or "♀" in text:
            forms.append("Female")
        elif "オス" in text or "♂" in text:
            forms.append("Male")

    if "ケンタロス" in text and ("格闘" in text or "コンバット" in text or "combat" in text.lower()):
        base = "ケンタロス"
        forms = ["Paldea", "Combat"]
    elif "ケンタロス" in text and ("炎" in text or "ブレイズ" in text or "blaze" in text.lower()):
        base = "ケンタロス"
        forms = ["Paldea", "Blaze"]
    elif "ケンタロス" in text and ("水" in text or "アクア" in text or "aqua" in text.lower()):
        base = "ケンタロス"
        forms = ["Paldea", "Aqua"]

    # 括弧内のリージョンフォームキーワードをマッピング
    m = re.search(r"[\(（](.+?)[\)）]", text)
    if m:
        sub = m.group(1).strip()
        for ja_kw, en_form in _JA_FORM_KEYWORD_MAP:
            if ja_kw in sub:
                forms.append(en_form)
                break

    return base, forms


def get_local_sprite_path(name_ja: str, name_en: str = "") -> str:
    """Return the relative local_path for a Pokemon's champion sprite, or ''.

    Tries exact `name_ja` first, then falls back to a normalized base name
    (removes gender markers and parenthetical form suffixes) to find a match
    when sprites are stored by base species name.
    """
    mapping = _ensure_sprite_manifest()
    if name_ja in mapping:
        return mapping[name_ja]

    en_base, en_forms = _name_en_form_hints(name_en)
    path = _resolve_by_manifest(base_name_en=en_base, desired_forms=en_forms)
    if path:
        return path

    ja_base, ja_forms = _name_ja_form_hints(name_ja)
    path = _resolve_by_manifest(base_name_ja=ja_base, desired_forms=ja_forms)
    if path:
        return path

    # Fallback to base mapping
    base = _norm_ja_name(name_ja)
    if base in mapping:
        return mapping[base]

    if en_base:
        path = _resolve_by_manifest(base_name_en=en_base)
        if path:
            return path
    return ""


def sprite_pixmap(name_ja: str, width: int, height: int, name_en: str = "") -> QPixmap | None:
    """Load a champion sprite by Japanese name from local assets; None if not found."""
    local_path = get_local_sprite_path(name_ja, name_en=name_en)
    if not local_path:
        return None
    key = (local_path, width, height)
    if key in _SPRITE_PIXMAP_CACHE:
        return _SPRITE_PIXMAP_CACHE[key]
    full_path = _SPRITES_DIR / local_path
    pm: QPixmap | None = None
    if full_path.exists():
        src = QPixmap(str(full_path))
        if not src.isNull():
            pm = src.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    _SPRITE_PIXMAP_CACHE[key] = pm
    return pm


def sprite_pixmap_or_zukan(name_ja: str, width: int, height: int, name_en: str = "") -> QPixmap | None:
    """Local champion sprite first; fall back to Zukan image if not available locally."""
    pm = sprite_pixmap(name_ja, width, height, name_en=name_en)
    if pm:
        return pm
    from src.data import zukan_client
    entries = zukan_client.get_pokemon_index()
    # 完全一致を優先し、なければ "base_name (sub_name)" 形式でフォルム画像を検索
    url = next((e.image_small_url for e in entries if e.name_ja == name_ja), "")
    if not url:
        import re as _re
        m = _re.match(r"^(.+?)\s*[\(（](.+?)[\)）]$", name_ja)
        if m:
            base, sub = m.group(1).strip(), m.group(2).strip()
            url = next(
                (e.image_small_url for e in entries
                 if e.name_ja == base and (e.sub_name or "").replace("・", "・") == sub),
                "",
            )
    if not url:
        for prefix, sub_name in (
            ("アローラ", "アローラのすがた"),
            ("ガラル", "ガラルのすがた"),
            ("ヒスイ", "ヒスイのすがた"),
            ("パルデア", "パルデアのすがた"),
        ):
            if not name_ja.startswith(prefix):
                continue
            base = name_ja[len(prefix):].strip()
            if not base:
                continue
            url = next(
                (e.image_small_url for e in entries if e.name_ja == base and sub_name in (e.sub_name or "")),
                "",
            )
            if url:
                break
    if not url and "ロトム" in name_ja and name_ja != "ロトム":
        for token in ("ヒート", "ウォッシュ", "フロスト", "スピン", "カット"):
            if token not in name_ja:
                continue
            url = next(
                (e.image_small_url for e in entries if e.name_ja == "ロトム" and token in (e.sub_name or "")),
                "",
            )
            if url:
                break
    if not url:
        return None
    cache_key = (url, width, height)
    if cache_key in _SPRITE_PIXMAP_CACHE:
        return _SPRITE_PIXMAP_CACHE[cache_key]
    payload = zukan_client.get_cached_asset_bytes(url)
    pm = None
    if payload:
        src = QPixmap()
        if src.loadFromData(payload):
            pm = src.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    _SPRITE_PIXMAP_CACHE[cache_key] = pm
    return pm
