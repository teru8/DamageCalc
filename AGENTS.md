---
paths:
  - "**/*.py"
  - "**/*.pyi"

---

# Project Overview

## 概要

**PokemonDamageCalc** — ポケモンチャンピオンズ向け PyQt5 製ダメージ計算ツール。

- OCR（Tesseract + OpenCV）でゲーム画面のボックス・バトル画面を自動認識
- Smogon calc（Node.js `@smogon/calc`）をブリッジ経由で呼び出してダメージ計算
- PokeAPI + 図鑑サイトからポケモンデータを取得し SQLite にキャッシュ
- 使用率データをスクレイピングして表示

## ディレクトリ構成

```
main.py                      # エントリポイント
src/
  models.py                  # PokemonInstance, MoveInfo, SpeciesInfo 等のデータクラス
  constants.py               # タイプ色・自然・定数
  ui/
    main_window.py           # メインウィンドウ（登録・バトル管理）
    damage_panel.py          # ダメージ計算パネル（攻撃側/防御側選択・結果表示）
    pokemon_edit_dialog.py   # ポケモン編集ダイアログ（手動登録・スペック入力）
    battle_panel.py          # バトル状態パネル
    ui_utils.py              # 共有UIユーティリティ（スプライト読み込み・ローディングオーバーレイ）
    styles.py                # QSS スタイル定義
  calc/
    damage_calc.py           # ダメージ計算ロジック
    smogon_bridge.py         # Node.js smogon/calc への橋渡し
  capture/
    ocr_engine.py            # Tesseract OCR ラッパー
    video_thread.py          # キャプチャスレッド
  recognition/
    box_reader.py            # ボックス画面 OCR
    live_battle_reader.py    # バトル画面リアルタイム認識
    champions_sprite_matcher.py  # スプライトマッチング
    opponent_party_reader.py # 相手パーティ認識
    text_matcher.py          # テキストマッチング
  data/
    database.py              # SQLite キャッシュ管理
    pokeapi_client.py        # PokeAPI クライアント
    zukan_client.py          # 日本語図鑑サイトクライアント
    usage_scraper.py         # 使用率スクレイパー
    item_catalog.py          # アイテムカタログ
assets/
  templates/icons/           # タイプアイコン PNG/GIF
  champions_menu_sprites/    # チャンピオンズスプライト + manifest.json
```

## 主要な制約・注意点

- **Python 3.11 + PyQt5** 環境（`requirements.txt` 参照）
- `PokemonEditDialog` の `__init__` は画像読み込みで重いため、呼び出し時は必ず `ui_utils.open_pokemon_edit_dialog()` を使用すること（ローディングオーバーレイが自動表示される）
- ポケモンチャンピオンズのスプライトは全種存在しない（`assets/champions_menu_sprites/`）
- EVはチャンピオンズ仕様（ポイント × 8 = 従来 EVに相当）

## Hooks

### PostToolUse Hooks

Configure in `~/.claude/settings.json`:

- **black/ruff**: Auto-format `.py` files after edit
- **mypy/pyright**: Run type checking after editing `.py` files

## Sprite & Image Resources

- The sprites consist solely of Pokémon that appear in Pokémon Champions, so it’s only natural that some Pokémon are missing
- As long as images can be supplemented from the Japanese Pokémon Pokédex website, there’s generally no problem
- In some cases, such as with Bakeccha, the base image may be sufficient for size forms (to be determined on a case-by-case basis)

## Cache Management

### Multi-Layer Cache Updates

When updating Pokemon form names in `_SPECIAL_FORM_NAME_MAP`, multiple cache layers must be updated:

1. **Database caches**: `species_cache` (name_ja), `usage_ranking` (pokemon_name_ja)
2. **Usage data**: `src/usage_data_M-1.json` (pokemon_name_ja, name_ja)
3. **_EXPECTED_FORM_NAMES**: Add entries to trigger cache refresh on app startup

### Immediate Updates

- `_EXPECTED_FORM_NAMES` only triggers cache refresh on app startup
- For immediate updates, directly update database using SQLite scripts
- Usage data JSON must be updated manually or via script

### Bulk Update Strategy

- Create scripts to update database and JSON simultaneously when changing form names
- Consider implementing automated cache invalidation mechanism for future changes

## Smogon Bridge Debugging

- When a calculation error occurs, do not immediately assume it's a smogon_bridge conversion issue
- Before making any corrections, first investigate how the Pokemon is named in both PokeAPI and Smogon
- Only make changes after confirming the correct naming conventions from official sources
- Use web search and official documentation (Smogon FORMES.md, PokeAPI docs) to verify species names
- This prevents circular debugging and ensures accurate fixes based on verified information



