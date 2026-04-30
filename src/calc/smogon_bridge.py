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

# ── Name mapping tables ───────────────────────────────────────────────────

NATURE_JA_TO_EN: dict[str, str] = {
    "がんばりや": "Hardy",  "すなお": "Docile",   "まじめ": "Serious",
    "てれや": "Bashful",    "きまぐれ": "Quirky",
    "さみしがり": "Lonely", "いじっぱり": "Adamant","やんちゃ": "Naughty",
    "ゆうかん": "Brave",
    "ずぶとい": "Bold",     "わんぱく": "Impish",  "のうてんき": "Lax",
    "のんき": "Relaxed",
    "ひかえめ": "Modest",   "おっとり": "Mild",    "うっかりや": "Rash",
    "れいせい": "Quiet",
    "おだやか": "Calm",     "おとなしい": "Gentle","しんちょう": "Careful",
    "なまいき": "Sassy",
    "おくびょう": "Timid",  "せっかち": "Hasty",   "ようき": "Jolly",
    "むじゃき": "Naive",
}

ABILITY_JA_TO_EN: dict[str, str] = {
    "ARシステム": "RKS System",
    "アイスフェイス": "Ice Face",
    "アイスボディ": "Ice Body",
    "あくしゅう": "Stench",
    "あついしぼう": "Thick Fat",
    "あとだし": "Stall",
    "アナライズ": "Analytic",
    "あまのじゃく": "Contrary",
    "あめうけざら": "Rain Dish",
    "あめふらし": "Drizzle",
    "ありじごく": "Arena Trap",
    "アロマベール": "Aroma Veil",
    "いかく": "Intimidate",
    "いかりのこうら": "Anger Shell",
    "いかりのつぼ": "Anger Point",
    "いしあたま": "Rock Head",
    "いたずらごころ": "Prankster",
    "いやしのこころ": "Healer",
    "イリュージョン": "Illusion",
    "いろめがね": "Tinted Lens",
    "いわはこび": "Rocky Payload",
    "うのミサイル": "Gulp Missile",
    "うるおいボイス": "Liquid Voice",
    "うるおいボディ": "Hydration",
    "エアロック": "Air Lock",
    "エレキスキン": "Galvanize",
    "エレキメイカー": "Electric Surge",
    "えんかく": "Long Reach",
    "おうごんのからだ": "Good as Gold",
    "おどりこ": "Dancer",
    "おみとおし": "Frisk",
    "おもてなし": "Hospitality",
    "おやこあい": "Parental Bond",
    "オーラブレイク": "Aura Break",
    "おわりのだいち": "Desolate Land",
    "かいりきバサミ": "Hyper Cutter",
    "かがくのちから": "Power of Alchemy",
    "かがくへんかガス": "Neutralizing Gas",
    "かげふみ": "Shadow Tag",
    "かぜのり": "Wind Rider",
    "かそく": "Speed Boost",
    "かたいツメ": "Tough Claws",
    "かたやぶり": "Mold Breaker",
    "かちき": "Competitive",
    "カブトアーマー": "Battle Armor",
    "カーリーヘアー": "Tangling Hair",
    "かるわざ": "Unburden",
    "かわりもの": "Imposter",
    "がんじょう": "Sturdy",
    "がんじょうあご": "Strong Jaw",
    "かんそうはだ": "Dry Skin",
    "かんつうドリル": "Piercing Drill",
    "かんろなミツ": "Supersweet Syrup",
    "ききかいひ": "Emergency Exit",
    "きけんよち": "Anticipation",
    "きずなへんげ": "Battle Bond",
    "ぎたい": "Mimicry",
    "きみょうなくすり": "Curious Medicine",
    "きもったま": "Scrappy",
    "ぎゃくじょう": "Berserk",
    "きゅうばん": "Suction Cups",
    "きょううん": "Super Luck",
    "きょうえん": "Costar",
    "きょうせい": "Symbiosis",
    "ぎょぐん": "Schooling",
    "きよめのしお": "Purifying Salt",
    "きれあじ": "Sharpness",
    "きんしのちから": "Mycelium Might",
    "きんちょうかん": "Unnerve",
    "くいしんぼう": "Gluttony",
    "クイックドロウ": "Quick Draw",
    "クォークチャージ": "Quark Drive",
    "くさのけがわ": "Grass Pelt",
    "くだけるよろい": "Weak Armor",
    "グラスメイカー": "Grassy Surge",
    "クリアボディ": "Clear Body",
    "くろのいななき": "Grim Neigh",
    "げきりゅう": "Torrent",
    "こおりのりんぷん": "Ice Scales",
    "こだいかっせい": "Protosynthesis",
    "こぼれダネ": "Seed Sower",
    "ごりむちゅう": "Gorilla Tactics",
    "こんがりボディ": "Well-Baked Body",
    "こんじょう": "Guts",
    "サイコメイカー": "Psychic Surge",
    "さいせいりょく": "Regenerator",
    "サーフテール": "Surge Surfer",
    "さまようたましい": "Wandering Spirit",
    "さめはだ": "Rough Skin",
    "サンパワー": "Solar Power",
    "シェルアーマー": "Shell Armor",
    "じきゅうりょく": "Stamina",
    "じしんかじょう": "Moxie",
    "しぜんかいふく": "Natural Cure",
    "しめりけ": "Damp",
    "しゅうかく": "Harvest",
    "じゅうなん": "Limber",
    "じゅくせい": "Ripen",
    "じょうききかん": "Steam Engine",
    "しょうりのほし": "Victory Star",
    "じょおうのいげん": "Queenly Majesty",
    "じりょく": "Magnet Pull",
    "しれいとう": "Commander",
    "しろいけむり": "White Smoke",
    "しろのいななき": "Chilling Neigh",
    "しんがん": "Mind's Eye",
    "シンクロ": "Synchronize",
    "しんりょく": "Overgrow",
    "すいすい": "Swift Swim",
    "スイートベール": "Sweet Veil",
    "すいほう": "Water Bubble",
    "スカイスキン": "Aerilate",
    "スキルリンク": "Skill Link",
    "スクリューおびれ": "Propeller Tail",
    "すじがねいり": "Stalwart",
    "すてみ": "Reckless",
    "スナイパー": "Sniper",
    "すなおこし": "Sand Stream",
    "すなかき": "Sand Rush",
    "すながくれ": "Sand Veil",
    "すなのちから": "Sand Force",
    "すなはき": "Sand Spit",
    "すりぬけ": "Infiltrator",
    "するどいめ": "Keen Eye",
    "スロースタート": "Slow Start",
    "スワームチェンジ": "Power Construct",
    "せいぎのこころ": "Justified",
    "せいしんりょく": "Inner Focus",
    "せいでんき": "Static",
    "ぜったいねむり": "Comatose",
    "ゼロフォーミング": "Teraform Zero",
    "そうしょく": "Sap Sipper",
    "そうだいしょう": "Supreme Overlord",
    "ソウルハート": "Soul-Heart",
    "たいねつ": "Heatproof",
    "ダウンロード": "Download",
    "ダークオーラ": "Dark Aura",
    "だっぴ": "Shed Skin",
    "ターボブレイズ": "Turboblaze",
    "たまひろい": "Ball Fetch",
    "ダルマモード": "Zen Mode",
    "たんじゅん": "Simple",
    "ちからずく": "Sheer Force",
    "ちからもち": "Huge Power",
    "ちくでん": "Volt Absorb",
    "ちどりあし": "Tangled Feet",
    "ちょすい": "Water Absorb",
    "テイルアーマー": "Armor Tail",
    "てきおうりょく": "Adaptability",
    "テクニシャン": "Technician",
    "てつのこぶし": "Iron Fist",
    "てつのトゲ": "Iron Barbs",
    "テラスシェル": "Tera Shell",
    "テラスチェンジ": "Tera Shift",
    "テラボルテージ": "Teravolt",
    "デルタストリーム": "Delta Stream",
    "テレパシー": "Telepathy",
    "でんきエンジン": "Motor Drive",
    "でんきにかえる": "Electromorphosis",
    "てんきや": "Forecast",
    "てんねん": "Unaware",
    "てんのめぐみ": "Serene Grace",
    "とうそうしん": "Rivalry",
    "どくくぐつ": "Poison Puppeteer",
    "どくげしょう": "Toxic Debris",
    "どくしゅ": "Poison Touch",
    "どくのくさり": "Toxic Chain",
    "どくのトゲ": "Poison Point",
    "どくぼうそう": "Toxic Boost",
    "どしょく": "Earth Eater",
    "とびだすなかみ": "Innards Out",
    "とびだすハバネロ": "Spicy Spray",
    "ドラゴンスキン": "Dragonize",
    "トランジスタ": "Transistor",
    "トレース": "Trace",
    "とれないにおい": "Lingering Aroma",
    "どんかん": "Oblivious",
    "ナイトメア": "Bad Dreams",
    "なまけ": "Truant",
    "にげあし": "Run Away",
    "にげごし": "Wimp Out",
    "ぬめぬめ": "Gooey",
    "ねつこうかん": "Thermal Exchange",
    "ねつぼうそう": "Flare Boost",
    "ねんちゃく": "Sticky Hold",
    "ノーガード": "No Guard",
    "ノーてんき": "Cloud Nine",
    "ノーマルスキン": "Normalize",
    "のろわれボディ": "Cursed Body",
    "はがねつかい": "Steelworker",
    "はがねのせいしん": "Steely Spirit",
    "ばけのかわ": "Disguise",
    "はじまりのうみ": "Primordial Sea",
    "パステルベール": "Pastel Veil",
    "はっこう": "Illuminate",
    "バッテリー": "Battery",
    "はとむね": "Big Pecks",
    "バトルスイッチ": "Stance Change",
    "ハードロック": "Solid Rock",
    "ハドロンエンジン": "Hadron Engine",
    "はやあし": "Quick Feet",
    "はやおき": "Early Bird",
    "はやてのつばさ": "Gale Wings",
    "はらぺこスイッチ": "Hunger Switch",
    "バリアフリー": "Screen Cleaner",
    "はりきり": "Hustle",
    "はりこみ": "Stakeout",
    "パワースポット": "Power Spot",
    "パンクロック": "Punk Rock",
    "ばんけん": "Guard Dog",
    "はんすう": "Cud Chew",
    "ビーストブースト": "Beast Boost",
    "ひでり": "Drought",
    "ひとでなし": "Merciless",
    "ひひいろのこどう": "Orichalcum Pulse",
    "ビビッドボディ": "Dazzling",
    "びびり": "Rattled",
    "ひらいしん": "Lightning Rod",
    "ヒーリングシフト": "Triage",
    "びんじょう": "Opportunist",
    "ファーコート": "Fur Coat",
    "ファントムガード": "Shadow Shield",
    "フィルター": "Filter",
    "ふうりょくでんき": "Wind Power",
    "フェアリーオーラ": "Fairy Aura",
    "フェアリースキン": "Pixilate",
    "ふかしのこぶし": "Unseen Fist",
    "ぶきよう": "Klutz",
    "ふくがん": "Compound Eyes",
    "ふくつのこころ": "Steadfast",
    "ふくつのたて": "Dauntless Shield",
    "ふしぎなうろこ": "Marvel Scale",
    "ふしぎなまもり": "Wonder Guard",
    "ふしょく": "Corrosion",
    "ふとうのけん": "Intrepid Sword",
    "ふみん": "Insomnia",
    "ふゆう": "Levitate",
    "プラス": "Plus",
    "フラワーギフト": "Flower Gift",
    "フラワーベール": "Flower Veil",
    "フリーズスキン": "Refrigerate",
    "プリズムアーマー": "Prism Armor",
    "ブレインフォース": "Neuroforce",
    "プレッシャー": "Pressure",
    "フレンドガード": "Friend Guard",
    "ヘヴィメタル": "Heavy Metal",
    "ヘドロえき": "Liquid Ooze",
    "へんげんじざい": "Protean",
    "へんしょく": "Color Change",
    "ポイズンヒール": "Poison Heal",
    "ぼうおん": "Soundproof",
    "ほうし": "Effect Spore",
    "ぼうじん": "Overcoat",
    "ぼうだん": "Bulletproof",
    "ほおぶくろ": "Cheek Pouch",
    "ほのおのからだ": "Flame Body",
    "ほろびのボディ": "Perish Body",
    "マイティチェンジ": "Zero to Hero",
    "マイナス": "Minus",
    "マイペース": "Own Tempo",
    "マグマのよろい": "Magma Armor",
    "まけんき": "Defiant",
    "マジシャン": "Magician",
    "マジックガード": "Magic Guard",
    "マジックミラー": "Magic Bounce",
    "マルチスケイル": "Multiscale",
    "マルチタイプ": "Multitype",
    "ミイラ": "Mummy",
    "みずがため": "Water Compaction",
    "ミストメイカー": "Misty Surge",
    "みずのベール": "Water Veil",
    "みつあつめ": "Honey Gather",
    "ミラーアーマー": "Mirror Armor",
    "ミラクルスキン": "Wonder Skin",
    "むしのしらせ": "Swarm",
    "ムラっけ": "Moody",
    "メガソーラー": "Mega Sol",
    "メガランチャー": "Mega Launcher",
    "メタルプロテクト": "Full Metal Body",
    "メロメロボディ": "Cute Charm",
    "めんえき": "Immunity",
    "もうか": "Blaze",
    "ものひろい": "Pickup",
    "もふもふ": "Fluffy",
    "もらいび": "Flash Fire",
    "やるき": "Vital Spirit",
    "ゆうばく": "Aftermath",
    "ゆきかき": "Slush Rush",
    "ゆきがくれ": "Snow Cloak",
    "ゆきふらし": "Snow Warning",
    "ようりょくそ": "Chlorophyll",
    "ヨガパワー": "Pure Power",
    "よちむ": "Forewarn",
    "よびみず": "Storm Drain",
    "よわき": "Defeatist",
    "ライトメタル": "Light Metal",
    "リーフガード": "Leaf Guard",
    "リベロ": "Libero",
    "リミットシールド": "Shields Down",
    "りゅうのあぎと": "Dragon's Maw",
    "りんぷん": "Shield Dust",
    "レシーバー": "Receiver",
    "わざわいのうつわ": "Vessel of Ruin",
    "わざわいのおふだ": "Tablets of Ruin",
    "わざわいのたま": "Beads of Ruin",
    "わざわいのつるぎ": "Sword of Ruin",
    "わたげ": "Cotton Down",
    "わるいてぐせ": "Pickpocket",
}

ITEM_JA_TO_EN: dict[str, str] = {
    "あいいろのたま": "Blue Orb",
    "アイスメモリ": "Ice Memory",
    "あおぞらプレート": "Sky Plate",
    "あかいいと": "Destiny Knot",
    "アクアカセット": "Douse Drive",
    "あついいわ": "Heat Rock",
    "アッキのみ": "Kee Berry",
    "あつぞこブーツ": "Heavy-Duty Boots",
    "アブソルナイト": "Absolite",
    "アブソルナイトZ": "",
    "イアのみ": "Iapapa Berry",
    "いかさまダイス": "Loaded Dice",
    "いかずちプレート": "Zap Plate",
    "いしずえのめん": "Cornerstone Mask",
    "イトケのみ": "Passho Berry",
    "いどのめん": "Wellspring Mask",
    "イナズマカセット": "Shock Drive",
    "いのちのたま": "Life Orb",
    "イバンのみ": "Custap Berry",
    "ウイのみ": "Wiki Berry",
    "ウタンのみ": "Payapa Berry",
    "ウツボットナイト": "",
    "ウブのみ": "Grepa Berry",
    "エアームドナイト": "",
    "エルレイドナイト": "Galladite",
    "エレキシード": "Electric Seed",
    "エレクトロメモリ": "Electric Memory",
    "エンブオナイト": "",
    "おうじゃのしるし": "King's Rock",
    "おおきなねっこ": "Big Root",
    "オーダイルナイト": "",
    "オッカのみ": "Occa Berry",
    "オニゴーリナイト": "Glalitite",
    "オボンのみ": "Sitrus Berry",
    "オレンのみ": "Oran Berry",
    "おんみつマント": "Covert Cloak",
    "かいがらのすず": "Shell Bell",
    "カイリュナイト": "",
    "カイロスナイト": "Pinsirite",
    "カエンジシナイト": "",
    "かえんだま": "Flame Orb",
    "カゴのみ": "Chesto Berry",
    "カシブのみ": "Kasib Berry",
    "かたいいし": "Hard Stone",
    "ガブリアスナイト": "Garchompite",
    "かまどのめん": "Hearthflame Mask",
    "カムラのみ": "Salac Berry",
    "カメックスナイト": "Blastoisinite",
    "ガメノデスナイト": "",
    "からぶりほけん": "Blunder Policy",
    "カラマネロナイト": "",
    "かるいし": "Float Stone",
    "ガルーラナイト": "Kangaskhanite",
    "がんせきプレート": "Stone Plate",
    "きあいのタスキ": "Focus Sash",
    "きあいのハチマキ": "Focus Band",
    "きせきのタネ": "Miracle Seed",
    "キーのみ": "Persim Berry",
    "ギャラドスナイト": "Gyaradosite",
    "きゅうこん": "Absorb Bulb",
    "キラフロルナイト": "",
    "きれいなぬけがら": "Shed Shell",
    "ぎんのこな": "Silver Powder",
    "クイックボール": "Quick Ball",
    "グソクムシャナイト": "",
    "くちたけん": "Rusted Sword",
    "くちたたて": "Rusted Shield",
    "クチートナイト": "Mawilite",
    "くっつきバリ": "Sticky Barb",
    "グラウンドメモリ": "Ground Memory",
    "グラスシード": "Grassy Seed",
    "グラスメモリ": "Grass Memory",
    "クラボのみ": "Cheri Berry",
    "グランドコート": "Terrain Extender",
    "クリアチャーム": "Clear Amulet",
    "くろいてっきゅう": "Iron Ball",
    "くろいヘドロ": "Black Sludge",
    "くろいメガネ": "Black Glasses",
    "くろおび": "Black Belt",
    "ケケンカニナイト": "",
    "ゲッコウガナイト": "",
    "ゲンガナイト": "Gengarite",
    "こうかくレンズ": "Wide Lens",
    "こうこうのしっぽ": "Lagging Tail",
    "こうてつプレート": "Iron Plate",
    "こころのしずく": "Soul Dew",
    "ゴーストメモリ": "Ghost Memory",
    "こだわりスカーフ": "Choice Scarf",
    "こだわりハチマキ": "Choice Band",
    "こだわりメガネ": "Choice Specs",
    "ゴツゴツメット": "Rocky Helmet",
    "こぶしのプレート": "Fist Plate",
    "ゴルーグナイト": "",
    "こわもてプレート": "Dread Plate",
    "こんごうだま": "Adamant Orb",
    "サイキックメモリ": "Psychic Memory",
    "サイコシード": "Psychic Seed",
    "サーナイトナイト": "Gardevoirite",
    "サメハダナイト": "Sharpedonite",
    "さらさらいわ": "Smooth Rock",
    "ザロクのみ": "Pomeg Berry",
    "サンのみ": "Lansat Berry",
    "しあわせタマゴ": "Lucky Egg",
    "ジガルデナイト": "",
    "じしゃく": "Magnet",
    "ジジーロンナイト": "",
    "しずくプレート": "Splash Plate",
    "シビルドナイト": "",
    "しめつけバンド": "Binding Band",
    "しめったいわ": "Damp Rock",
    "じゃくてんほけん": "Weakness Policy",
    "ジャポのみ": "Jaboca Berry",
    "シャリタツナイト": "",
    "シャンデラナイト": "",
    "じゅうでんち": "Cell Battery",
    "ジュカインナイト": "Sceptilite",
    "シュカのみ": "Shuca Berry",
    "ジュペッタナイト": "Banettite",
    "しらたま": "Lustrous Orb",
    "シルクのスカーフ": "Silk Scarf",
    "しろいハーブ": "White Herb",
    "しんかのきせき": "Eviolite",
    "しんぴのしずく": "Mystic Water",
    "ズアのみ": "Apicot Berry",
    "スコヴィラナイト": "",
    "スターのみ": "Starf Berry",
    "スターミナイト": "",
    "スチールメモリ": "Steel Memory",
    "スピアナイト": "Beedrillite",
    "スピードパウダー": "Quick Powder",
    "ズルズキンナイト": "",
    "するどいキバ": "Razor Fang",
    "するどいくちばし": "Sharp Beak",
    "するどいツメ": "Razor Claw",
    "せいれいプレート": "Pixie Plate",
    "セグレイブナイト": "",
    "ゼラオラナイト": "",
    "せんせいのツメ": "Quick Claw",
    "ソクノのみ": "Wacan Berry",
    "だいこんごうだま": "Adamant Crystal",
    "だいしらたま": "Lustrous Globe",
    "だいちのプレート": "Earth Plate",
    "だいはっきんだま": "Griseous Core",
    "タイレーツナイト": "",
    "ダークメモリ": "Dark Memory",
    "ダークライナイト": "",
    "だっしゅつパック": "Eject Pack",
    "だっしゅつボタン": "Eject Button",
    "たつじんのおび": "Expert Belt",
    "タブンネナイト": "Audinite",
    "たべのこし": "Leftovers",
    "タポルのみ": "Qualot Berry",
    "たまむしプレート": "Insect Plate",
    "タラプのみ": "Maranga Berry",
    "タンガのみ": "Tanga Berry",
    "チイラのみ": "Liechi Berry",
    "ちからのハチマキ": "Muscle Band",
    "チーゴのみ": "Rawst Berry",
    "チャーレムナイト": "Medichamite",
    "チリーンナイト": "",
    "チルタリスナイト": "Altarianite",
    "つめたいいわ": "Icy Rock",
    "つららのプレート": "Icicle Plate",
    "ディアンシナイト": "Diancite",
    "でんきだま": "Light Ball",
    "デンリュウナイト": "Ampharosite",
    "とくせいガード": "Ability Shield",
    "どくどくだま": "Toxic Orb",
    "どくバリ": "Poison Barb",
    "とけないこおり": "Never-Melt Ice",
    "とつげきチョッキ": "Assault Vest",
    "ドラゴンメモリ": "Dragon Memory",
    "ドラミドロナイト": "",
    "ドリュウズナイト": "",
    "ながねぎ": "Leek",
    "ナゾのみ": "Enigma Berry",
    "ナナシのみ": "Aspear Berry",
    "ナモのみ": "Colbur Berry",
    "ニャオニクスナイト": "",
    "ネコブのみ": "Kelpsy Berry",
    "ねばりのかぎづめ": "Grip Claw",
    "ねらいのまと": "Ring Target",
    "のどスプレー": "Throat Spray",
    "ノーマルジュエル": "Normal Gem",
    "のろいのおふだ": "Spell Tag",
    "ハガネールナイト": "Steelixite",
    "バクーダナイト": "Cameruptite",
    "バグメモリ": "Bug Memory",
    "バコウのみ": "Coba Berry",
    "バシャーモナイト": "Blazikenite",
    "はっきんだま": "Griseous Orb",
    "ハッサムナイト": "Scizorite",
    "ハバンのみ": "Haban Berry",
    "パワフルハーブ": "Power Herb",
    "バンギラスナイト": "Tyranitarite",
    "バンジのみ": "Aguav Berry",
    "パンチグローブ": "Punching Glove",
    "ばんのうがさ": "Utility Umbrella",
    "ビアンのみ": "Kebia Berry",
    "ひかりごけ": "Luminous Moss",
    "ひかりのこな": "Bright Powder",
    "ひかりのねんど": "Light Clay",
    "ピクシナイト": "",
    "ピジョットナイト": "Pidgeotite",
    "ヒードラナイト": "",
    "ひのたまプレート": "Flame Plate",
    "ビビリだま": "Adrenaline Orb",
    "ヒメリのみ": "Leppa Berry",
    "ピントレンズ": "Scope Lens",
    "ファイトメモリ": "Fighting Memory",
    "ファイヤーメモリ": "Fire Memory",
    "フィラのみ": "Figy Berry",
    "ふうせん": "Air Balloon",
    "フェアリーメモリ": "Fairy Memory",
    "フォーカスレンズ": "Zoom Lens",
    "ふしぎのプレート": "Mind Plate",
    "フシギバナイト": "Venusaurite",
    "ブーストエナジー": "Booster Energy",
    "フーディナイト": "Alakazite",
    "プテラナイト": "Aerodactylite",
    "ふといホネ": "Thick Club",
    "フライングメモリ": "Flying Memory",
    "フラエッテナイト": "",
    "ブリガロンナイト": "",
    "フリーズカセット": "Chill Drive",
    "ブレイズカセット": "Burn Drive",
    "べにいろのたま": "Red Orb",
    "ヘラクロスナイト": "Heracronite",
    "ヘルガナイト": "Houndoominite",
    "ペンドラナイト": "",
    "ポイズンメモリ": "Poison Memory",
    "ぼうごパッド": "Protective Pads",
    "ぼうじんゴーグル": "Safety Goggles",
    "ボスゴドラナイト": "Aggronite",
    "ホズのみ": "Chilan Berry",
    "ボーマンダナイト": "Salamencite",
    "まがったスプーン": "Twisted Spoon",
    "マギアナイト": "",
    "マゴのみ": "Mago Berry",
    "マトマのみ": "Tamato Berry",
    "マフォクシナイト": "",
    "ミクルのみ": "Micle Berry",
    "ミストシード": "Misty Seed",
    "みどりのプレート": "Meadow Plate",
    "ミミロップナイト": "Lopunnite",
    "ミュウツナイトX": "Mewtwonite X",
    "ミュウツナイトY": "Mewtwonite Y",
    "ムクホークナイト": "",
    "メガニウムナイト": "",
    "メタグロスナイト": "Metagrossite",
    "メタルコート": "Metal Coat",
    "メタルパウダー": "Metal Powder",
    "メトロノーム": "Metronome",
    "メンタルハーブ": "Mental Herb",
    "もうどくプレート": "Toxic Plate",
    "もくたん": "Charcoal",
    "ものしりメガネ": "Wise Glasses",
    "もののけプレート": "Spooky Plate",
    "ものまねハーブ": "Mirror Herb",
    "モモンのみ": "Pecha Berry",
    "ヤタピのみ": "Petaya Berry",
    "ヤチェのみ": "Yache Berry",
    "ヤドランナイト": "Slowbronite",
    "ヤミラミナイト": "Sablenite",
    "やわらかいすな": "Soft Sand",
    "ゆきだま": "Snowball",
    "ユキノオナイト": "Abomasite",
    "ユキメノコナイト": "",
    "ようせいのハネ": "Fairy Feather",
    "ヨプのみ": "Chople Berry",
    "ヨロギのみ": "Charti Berry",
    "ライチュウナイトX": "",
    "ライチュウナイトY": "",
    "ライボルトナイト": "Manectite",
    "ラグラージナイト": "Swampertite",
    "ラティアスナイト": "Latiasite",
    "ラティオスナイト": "Latiosite",
    "ラムのみ": "Lum Berry",
    "リザードナイトX": "Charizardite X",
    "リザードナイトY": "Charizardite Y",
    "りゅうのキバ": "Dragon Fang",
    "りゅうのプレート": "Draco Plate",
    "リュガのみ": "Ganlon Berry",
    "リリバのみ": "Babiri Berry",
    "リンドのみ": "Rindo Berry",
    "ルカリオナイト": "Lucarionite",
    "ルカリオナイトZ": "",
    "ルチャブルナイト": "",
    "ルームサービス": "Room Service",
    "レッドカード": "Red Card",
    "レンブのみ": "Rowap Berry",
    "ロゼルのみ": "Roseli Berry",
    "ロックメモリ": "Rock Memory",
    "ロメのみ": "Hondew Berry",
}


def _item_name_to_en(item_name_ja: str) -> str:
    name = (item_name_ja or "").strip()
    if not name:
        return ""
    mapped = ITEM_JA_TO_EN.get(name, "")
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
    return get_ability_name_en(name)


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
    "minior-red-meteor":  "Minior-Meteor",  # りゅうせいのすがた (防御的)
    "minior-red":  "Minior",                # コアのすがた (攻撃的)
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
            logging.warning("SmogonBridge calc error: %s", e, exc_info=True)
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
    nature_en = NATURE_JA_TO_EN.get(p.nature, "Hardy")

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

    ivs = {
        "hp":  p.iv_hp,
        "atk": p.iv_attack,
        "def": p.iv_defense,
        "spa": p.iv_sp_attack,
        "spd": p.iv_sp_defense,
        "spe": p.iv_speed,
    }

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
            boosts["atk" if not is_physical else "spa"] = atk_rank

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

    ability_en = ABILITY_JA_TO_EN.get(p.ability or "", "") or "No Ability"
    result = {
        "species":  smogon_mega_species(p.name_en, p.name_ja) or p.name_ja or "Bulbasaur",
        "level":    p.level,
        "nature":   NATURE_JA_TO_EN.get(p.nature, "Hardy"),
        "evs": {
            "hp":  p.ev_hp,
            "atk": p.ev_attack,
            "def": p.ev_defense,
            "spa": p.ev_sp_attack,
            "spd": p.ev_sp_defense,
            "spe": p.ev_speed,
        },
        "ivs": {
            "hp":  p.iv_hp,
            "atk": p.iv_attack,
            "def": p.iv_defense,
            "spa": p.iv_sp_attack,
            "spd": p.iv_sp_defense,
            "spe": p.iv_speed,
        },
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

    # じゅうでん (Charge): doubles electric move power
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
