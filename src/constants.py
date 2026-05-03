# Screen capture resolution
CAPTURE_W = 1280
CAPTURE_H = 720

# --- Screen detection color thresholds (HSV) ---
# Battle screen: blue court floor is visible in lower-center
BATTLE_FLOOR_ROI = (400, 420, 880, 520)   # (x1, y1, x2, y2)
BATTLE_FLOOR_HUE = (90, 130)              # blue hue range in HSV

# Box screen: lavender/purple background in top area
BOX_BG_ROI = (330, 80, 960, 200)
BOX_BG_HUE = (130, 160)

# Party screen: dark gradient left panel
PARTY_LEFT_ROI = (50, 150, 320, 550)
PARTY_LEFT_HUE = (200, 260)               # dark blue/purple

# --- Battle screen OCR regions (1280x720) ---
# Opponent section (top-right)
OPP_NAME_ROI    = (1050, 38, 1260, 70)
OPP_HP_ROI      = (1060, 72, 1250, 108)

# User section (bottom-left)
MY_NAME_ROI     = (125, 588, 375, 618)
MY_HP_ROI       = (125, 618, 375, 652)

# Battle HUD icon areas
OPP_HUD_SPRITE_ROI   = (930, 8, 1068, 102)
MY_HUD_SPRITE_ROI    = (0, 620, 128, 720)
WATCH_COMMAND_ROI    = (1070, 260, 1275, 340)

# Battle sprite area (opponent active Pokemon)
BATTLE_OPP_POKEMON_ROI = (520, 110, 940, 430)

# Center battle text (move announcement: "X！")
BATTLE_TEXT_ROI = (330, 135, 900, 225)

# Move list (right panel, during move selection)
MOVE_ROI = [
    (832, 426, 1275, 502),
    (832, 504, 1275, 580),
    (832, 582, 1275, 658),
    (832, 660, 1275, 736),
]

# --- Party screen OCR regions ---
# Left party list slots (user)
MY_PARTY_ROIS = [
    (60,  178, 425, 255),
    (60,  257, 425, 334),
    (60,  336, 425, 413),
]
# Right opponent panel slots
OPP_PARTY_ROIS = [
    (980,  100, 1275, 255),
    (980,  258, 1275, 413),
    (980,  415, 1275, 570),
    (980,  572, 1275, 645),
    (980,  645, 1275, 718),
]

# --- Box screen OCR regions ---
BOX_POKEMON_NAME_ROI = (855, 115, 1200, 155)
# Stat columns: x=(1049,1096), y splits (202→389) into 6 equal rows
BOX_STAT_ROIS = {
    "hp":         (1049, 202, 1096, 234),
    "attack":     (1049, 234, 1096, 266),
    "defense":    (1049, 266, 1096, 298),
    "sp_attack":  (1049, 298, 1096, 330),
    "sp_defense": (1049, 330, 1096, 362),
    "speed":      (1049, 362, 1096, 394),
}
# EV columns: x=(1200,1241), same row heights
BOX_EV_ROIS = {
    "hp":         (1200, 202, 1241, 234),
    "attack":     (1200, 234, 1241, 266),
    "defense":    (1200, 266, 1241, 298),
    "sp_attack":  (1200, 298, 1241, 330),
    "sp_defense": (1200, 330, 1241, 362),
    "speed":      (1200, 362, 1241, 394),
}
# `BOX_NATURE_BOOST_ROIS`, `BOX_GRID_ROI`, `BOX_TYPE1_ROI`, `BOX_TYPE2_ROI`
# were removed per user request as they are not needed.
# Moves: x=(886,1166), y splits (407→560) into 4 equal rows
BOX_MOVE_ROIS = [
    (890, 407, 1166, 446),
    (890, 446, 1166, 485),
    (890, 485, 1166, 525),
    (890, 525, 1166, 564),
]
BOX_ABILITY_ROI = (1000, 580, 1200, 610)

# --- Type metadata (single source of truth) ---
TYPE_INFO: dict[str, tuple[str, str]] = {
    "ノーマル": ("normal", "#A8A878"),
    "ほのお": ("fire", "#F08030"),
    "みず": ("water", "#6890F0"),
    "でんき": ("electric", "#F8D030"),
    "くさ": ("grass", "#78C850"),
    "こおり": ("ice", "#98D8D8"),
    "かくとう": ("fighting", "#C03028"),
    "どく": ("poison", "#A040A0"),
    "じめん": ("ground", "#E0C068"),
    "ひこう": ("flying", "#A890F0"),
    "エスパー": ("psychic", "#F85888"),
    "むし": ("bug", "#A8B820"),
    "いわ": ("rock", "#B8A038"),
    "ゴースト": ("ghost", "#705898"),
    "ドラゴン": ("dragon", "#7038F8"),
    "あく": ("dark", "#705848"),
    "はがね": ("steel", "#B8B8D0"),
    "フェアリー": ("fairy", "#EE99AC"),
}

TYPE_JA_TO_EN = {ja: en for ja, (en, _color) in TYPE_INFO.items()}
TYPE_EN_TO_JA = {en: ja for ja, (en, _color) in TYPE_INFO.items()}
TYPE_COLORS = {en: color for _ja, (en, color) in TYPE_INFO.items()}
TYPE_COLORS[""] = "#888888"

# Type effectiveness chart: TYPE_CHART[atk_type][def_type] = multiplier
TYPE_CHART: dict[str, dict[str, float]] = {
    "normal":   {"rock": 0.5, "ghost": 0, "steel": 0.5},
    "fire":     {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 2,
                 "bug": 2, "rock": 0.5, "dragon": 0.5, "steel": 2},
    "water":    {"water": 0.5, "grass": 0.5, "fire": 2,
                 "ground": 2, "rock": 2, "dragon": 0.5},
    "electric": {"water": 2, "electric": 0.5, "grass": 0.5,
                 "ground": 0, "flying": 2, "dragon": 0.5},
    "grass":    {"fire": 0.5, "water": 2, "grass": 0.5, "poison": 0.5,
                 "ground": 2, "flying": 0.5, "bug": 0.5, "rock": 2,
                 "dragon": 0.5, "steel": 0.5},
    "ice":      {"water": 0.5, "grass": 2, "ice": 0.5, "ground": 2,
                 "flying": 2, "dragon": 2, "steel": 0.5},
    "fighting": {"normal": 2, "ice": 2, "poison": 0.5, "flying": 0.5,
                 "psychic": 0.5, "bug": 0.5, "rock": 2, "ghost": 0,
                 "dark": 2, "steel": 2, "fairy": 0.5},
    "poison":   {"grass": 2, "poison": 0.5, "ground": 0.5, "rock": 0.5,
                 "ghost": 0.5, "steel": 0, "fairy": 2},
    "ground":   {"fire": 2, "electric": 2, "grass": 0.5, "poison": 2,
                 "flying": 0, "bug": 0.5, "rock": 2, "steel": 2},
    "flying":   {"electric": 0.5, "grass": 2, "fighting": 2,
                 "bug": 2, "rock": 0.5, "steel": 0.5},
    "psychic":  {"fighting": 2, "poison": 2, "psychic": 0.5,
                 "dark": 0, "steel": 0.5},
    "bug":      {"fire": 0.5, "grass": 2, "fighting": 0.5, "flying": 0.5,
                 "psychic": 2, "ghost": 0.5, "dark": 2,
                 "steel": 0.5, "fairy": 0.5},
    "rock":     {"fire": 2, "ice": 2, "fighting": 0.5, "ground": 0.5,
                 "flying": 2, "bug": 2, "steel": 0.5},
    "ghost":    {"normal": 0, "psychic": 2, "ghost": 2, "dark": 0.5},
    "dragon":   {"dragon": 2, "steel": 0.5, "fairy": 0},
    "dark":     {"fighting": 0.5, "psychic": 2, "ghost": 2,
                 "dark": 0.5, "fairy": 0.5},
    "steel":    {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2,
                 "rock": 2, "steel": 0.5, "fairy": 2},
    "fairy":    {"fire": 0.5, "fighting": 2, "poison": 0.5,
                 "dragon": 2, "dark": 2, "steel": 0.5},
}

# Move category (Japanese → English)
CATEGORY_JA_TO_EN = {
    "ぶつり": "physical", "とくしゅ": "special", "へんか": "status",
}

# Nature metadata: Japanese name -> (boost, reduce, Smogon English)
NATURE_JA_INFO: dict[str, tuple[str | None, str | None, str]] = {
    "いじっぱり": ("attack", "sp_attack", "Adamant"),
    "うっかりや": ("sp_attack", "sp_defense", "Rash"),
    "おくびょう": ("speed", "attack", "Timid"),
    "おだやか": ("sp_defense", "attack", "Calm"),
    "おっとり": ("sp_attack", "defense", "Mild"),
    "おとなしい": ("sp_defense", "defense", "Gentle"),
    "がんばりや": (None, None, "Hardy"),
    "きまぐれ": (None, None, "Hardy"),
    "さみしがり": ("attack", "defense", "Lonely"),
    "しんちょう": ("sp_defense", "sp_attack", "Careful"),
    "すなお": (None, None, "Hardy"),
    "ずぶとい": ("defense", "attack", "Bold"),
    "せっかち": ("speed", "defense", "Hasty"),
    "てれや": (None, None, "Hardy"),
    "なまいき": ("sp_defense", "speed", "Sassy"),
    "のうてんき": ("defense", "sp_defense", "Lax"),
    "のんき": ("defense", "speed", "Relaxed"),
    "ひかえめ": ("sp_attack", "attack", "Modest"),
    "まじめ": (None, None, "Hardy"),
    "むじゃき": ("speed", "sp_defense", "Naive"),
    "やんちゃ": ("attack", "sp_defense", "Naughty"),
    "ゆうかん": ("attack", "speed", "Brave"),
    "ようき": ("speed", "sp_attack", "Jolly"),
    "れいせい": ("sp_attack", "speed", "Quiet"),
    "わんぱく": ("defense", "sp_attack", "Impish"),
}
# Compatibility view used by stat/nature calculations.
NATURES_JA: dict[str, tuple[str | None, str | None]] = {
    ja: (boost, reduce) for ja, (boost, reduce, _en) in NATURE_JA_INFO.items()
}
def nature_ja_to_en(nature_ja: str) -> str:
    _boost, _reduce, en = NATURE_JA_INFO.get(nature_ja, (None, None, "Hardy"))
    return en

# This is used to determine whether a move is a physical or special move,
# and to select the optimal nature for the defending Pokémon (in order to estimate its defensive capabilities).
BEST_DEF_NATURE_FOR = {
    "defense":    "ずぶとい",
    "sp_defense": "おだやか",
}

# ── Ability name map (Japanese → English) ─────────────────────────────
ABILITY_JA_TO_EN: dict[str, str] = {
    "ARシステム": "RKS System", "アイスフェイス": "Ice Face", "アイスボディ": "Ice Body", "あくしゅう": "Stench", "あついしぼう": "Thick Fat",
    "あとだし": "Stall", "アナライズ": "Analytic", "あまのじゃく": "Contrary", "あめうけざら": "Rain Dish", "あめふらし": "Drizzle",
    "ありじごく": "Arena Trap", "アロマベール": "Aroma Veil", "いかく": "Intimidate", "いかりのこうら": "Anger Shell", "いかりのつぼ": "Anger Point",
    "いしあたま": "Rock Head", "いたずらごころ": "Prankster", "いやしのこころ": "Healer", "イリュージョン": "Illusion", "いろめがね": "Tinted Lens",
    "いわはこび": "Rocky Payload", "うのミサイル": "Gulp Missile", "うるおいボイス": "Liquid Voice", "うるおいボディ": "Hydration", "エアロック": "Air Lock",
    "エレキスキン": "Galvanize", "エレキメイカー": "Electric Surge", "えんかく": "Long Reach", "おうごんのからだ": "Good as Gold", "おどりこ": "Dancer",
    "おみとおし": "Frisk", "おもてなし": "Hospitality", "おやこあい": "Parental Bond", "オーラブレイク": "Aura Break", "おわりのだいち": "Desolate Land",
    "かいりきバサミ": "Hyper Cutter", "かがくのちから": "Power of Alchemy", "かがくへんかガス": "Neutralizing Gas", "かげふみ": "Shadow Tag", "かぜのり": "Wind Rider",
    "かそく": "Speed Boost", "かたいツメ": "Tough Claws", "かたやぶり": "Mold Breaker", "かちき": "Competitive", "カブトアーマー": "Battle Armor",
    "カーリーヘアー": "Tangling Hair", "かるわざ": "Unburden", "かわりもの": "Imposter", "がんじょう": "Sturdy", "がんじょうあご": "Strong Jaw",
    "かんそうはだ": "Dry Skin", "かんつうドリル": "Piercing Drill", "かんろなミツ": "Supersweet Syrup", "ききかいひ": "Emergency Exit", "きけんよち": "Anticipation",
    "きずなへんげ": "Battle Bond", "ぎたい": "Mimicry", "きみょうなくすり": "Curious Medicine", "きもったま": "Scrappy", "ぎゃくじょう": "Berserk",
    "きゅうばん": "Suction Cups", "きょううん": "Super Luck", "きょうえん": "Costar", "きょうせい": "Symbiosis", "ぎょぐん": "Schooling",
    "きよめのしお": "Purifying Salt", "きれあじ": "Sharpness", "きんしのちから": "Mycelium Might", "きんちょうかん": "Unnerve", "くいしんぼう": "Gluttony",
    "クイックドロウ": "Quick Draw", "クォークチャージ": "Quark Drive", "くさのけがわ": "Grass Pelt", "くだけるよろい": "Weak Armor", "グラスメイカー": "Grassy Surge",
    "クリアボディ": "Clear Body", "くろのいななき": "Grim Neigh", "げきりゅう": "Torrent", "こおりのりんぷん": "Ice Scales", "こだいかっせい": "Protosynthesis",
    "こぼれダネ": "Seed Sower", "ごりむちゅう": "Gorilla Tactics", "こんがりボディ": "Well-Baked Body", "こんじょう": "Guts", "サイコメイカー": "Psychic Surge",
    "さいせいりょく": "Regenerator", "サーフテール": "Surge Surfer", "さまようたましい": "Wandering Spirit", "さめはだ": "Rough Skin", "サンパワー": "Solar Power",
    "シェルアーマー": "Shell Armor", "じきゅうりょく": "Stamina", "じしんかじょう": "Moxie", "しぜんかいふく": "Natural Cure", "しめりけ": "Damp",
    "しゅうかく": "Harvest", "じゅうなん": "Limber", "じゅくせい": "Ripen", "じょうききかん": "Steam Engine", "しょうりのほし": "Victory Star",
    "じょおうのいげん": "Queenly Majesty", "じりょく": "Magnet Pull", "しれいとう": "Commander", "しろいけむり": "White Smoke", "しろのいななき": "Chilling Neigh",
    "しんがん": "Mind's Eye", "シンクロ": "Synchronize", "しんりょく": "Overgrow", "すいすい": "Swift Swim", "スイートベール": "Sweet Veil",
    "すいほう": "Water Bubble", "スカイスキン": "Aerilate", "スキルリンク": "Skill Link", "スクリューおびれ": "Propeller Tail", "すじがねいり": "Stalwart",
    "すてみ": "Reckless", "スナイパー": "Sniper", "すなおこし": "Sand Stream", "すなかき": "Sand Rush", "すながくれ": "Sand Veil",
    "すなのちから": "Sand Force", "すなはき": "Sand Spit", "すりぬけ": "Infiltrator", "するどいめ": "Keen Eye", "スロースタート": "Slow Start",
    "スワームチェンジ": "Power Construct", "せいぎのこころ": "Justified", "せいしんりょく": "Inner Focus", "せいでんき": "Static", "ぜったいねむり": "Comatose",
    "ゼロフォーミング": "Teraform Zero", "そうしょく": "Sap Sipper", "そうだいしょう": "Supreme Overlord", "ソウルハート": "Soul-Heart", "たいねつ": "Heatproof",
    "ダウンロード": "Download", "ダークオーラ": "Dark Aura", "だっぴ": "Shed Skin", "ターボブレイズ": "Turboblaze", "たまひろい": "Ball Fetch",
    "ダルマモード": "Zen Mode", "たんじゅん": "Simple", "ちからずく": "Sheer Force", "ちからもち": "Huge Power", "ちくでん": "Volt Absorb",
    "ちどりあし": "Tangled Feet", "ちょすい": "Water Absorb", "テイルアーマー": "Armor Tail", "てきおうりょく": "Adaptability", "テクニシャン": "Technician",
    "てつのこぶし": "Iron Fist", "てつのトゲ": "Iron Barbs", "テラスシェル": "Tera Shell", "テラスチェンジ": "Tera Shift", "テラボルテージ": "Teravolt",
    "デルタストリーム": "Delta Stream", "テレパシー": "Telepathy", "でんきエンジン": "Motor Drive", "でんきにかえる": "Electromorphosis", "てんきや": "Forecast",
    "てんねん": "Unaware", "てんのめぐみ": "Serene Grace", "とうそうしん": "Rivalry", "どくくぐつ": "Poison Puppeteer", "どくげしょう": "Toxic Debris",
    "どくしゅ": "Poison Touch", "どくのくさり": "Toxic Chain", "どくのトゲ": "Poison Point", "どくぼうそう": "Toxic Boost", "どしょく": "Earth Eater",
    "とびだすなかみ": "Innards Out", "とびだすハバネロ": "Spicy Spray", "ドラゴンスキン": "Dragonize", "トランジスタ": "Transistor", "トレース": "Trace",
    "とれないにおい": "Lingering Aroma", "どんかん": "Oblivious", "ナイトメア": "Bad Dreams", "なまけ": "Truant", "にげあし": "Run Away",
    "にげごし": "Wimp Out", "ぬめぬめ": "Gooey", "ねつこうかん": "Thermal Exchange", "ねつぼうそう": "Flare Boost", "ねんちゃく": "Sticky Hold",
    "ノーガード": "No Guard", "ノーてんき": "Cloud Nine", "ノーマルスキン": "Normalize", "のろわれボディ": "Cursed Body", "はがねつかい": "Steelworker",
    "はがねのせいしん": "Steely Spirit", "ばけのかわ": "Disguise", "はじまりのうみ": "Primordial Sea", "パステルベール": "Pastel Veil", "はっこう": "Illuminate",
    "バッテリー": "Battery", "はとむね": "Big Pecks", "バトルスイッチ": "Stance Change", "ハードロック": "Solid Rock", "ハドロンエンジン": "Hadron Engine",
    "はやあし": "Quick Feet", "はやおき": "Early Bird", "はやてのつばさ": "Gale Wings", "はらぺこスイッチ": "Hunger Switch", "バリアフリー": "Screen Cleaner",
    "はりきり": "Hustle", "はりこみ": "Stakeout", "パワースポット": "Power Spot", "パンクロック": "Punk Rock", "ばんけん": "Guard Dog",
    "はんすう": "Cud Chew", "ビーストブースト": "Beast Boost", "ひでり": "Drought", "ひとでなし": "Merciless", "ひひいろのこどう": "Orichalcum Pulse",
    "ビビッドボディ": "Dazzling", "びびり": "Rattled", "ひらいしん": "Lightning Rod", "ヒーリングシフト": "Triage", "びんじょう": "Opportunist",
    "ファーコート": "Fur Coat", "ファントムガード": "Shadow Shield", "フィルター": "Filter", "ふうりょくでんき": "Wind Power", "フェアリーオーラ": "Fairy Aura",
    "フェアリースキン": "Pixilate", "ふかしのこぶし": "Unseen Fist", "ぶきよう": "Klutz", "ふくがん": "Compound Eyes", "ふくつのこころ": "Steadfast",
    "ふくつのたて": "Dauntless Shield", "ふしぎなうろこ": "Marvel Scale", "ふしぎなまもり": "Wonder Guard", "ふしょく": "Corrosion", "ふとうのけん": "Intrepid Sword",
    "ふみん": "Insomnia", "ふゆう": "Levitate", "プラス": "Plus", "フラワーギフト": "Flower Gift", "フラワーベール": "Flower Veil",
    "フリーズスキン": "Refrigerate", "プリズムアーマー": "Prism Armor", "ブレインフォース": "Neuroforce", "プレッシャー": "Pressure", "フレンドガード": "Friend Guard",
    "ヘヴィメタル": "Heavy Metal", "ヘドロえき": "Liquid Ooze", "へんげんじざい": "Protean", "へんしょく": "Color Change", "ポイズンヒール": "Poison Heal",
    "ぼうおん": "Soundproof", "ほうし": "Effect Spore", "ぼうじん": "Overcoat", "ぼうだん": "Bulletproof", "ほおぶくろ": "Cheek Pouch",
    "ほのおのからだ": "Flame Body", "ほろびのボディ": "Perish Body", "マイティチェンジ": "Zero to Hero", "マイナス": "Minus", "マイペース": "Own Tempo",
    "マグマのよろい": "Magma Armor", "まけんき": "Defiant", "マジシャン": "Magician", "マジックガード": "Magic Guard", "マジックミラー": "Magic Bounce",
    "マルチスケイル": "Multiscale", "マルチタイプ": "Multitype", "ミイラ": "Mummy", "みずがため": "Water Compaction", "ミストメイカー": "Misty Surge",
    "みずのベール": "Water Veil", "みつあつめ": "Honey Gather", "ミラーアーマー": "Mirror Armor", "ミラクルスキン": "Wonder Skin", "むしのしらせ": "Swarm",
    "ムラっけ": "Moody", "メガソーラー": "Mega Sol", "メガランチャー": "Mega Launcher", "メタルプロテクト": "Full Metal Body", "メロメロボディ": "Cute Charm",
    "めんえき": "Immunity", "もうか": "Blaze", "ものひろい": "Pickup", "もふもふ": "Fluffy", "もらいび": "Flash Fire",
    "やるき": "Vital Spirit", "ゆうばく": "Aftermath", "ゆきかき": "Slush Rush", "ゆきがくれ": "Snow Cloak", "ゆきふらし": "Snow Warning",
    "ようりょくそ": "Chlorophyll", "ヨガパワー": "Pure Power", "よちむ": "Forewarn", "よびみず": "Storm Drain", "よわき": "Defeatist",
    "ライトメタル": "Light Metal", "リーフガード": "Leaf Guard", "リベロ": "Libero", "リミットシールド": "Shields Down", "りゅうのあぎと": "Dragon's Maw",
    "りんぷん": "Shield Dust", "レシーバー": "Receiver", "わざわいのうつわ": "Vessel of Ruin", "わざわいのおふだ": "Tablets of Ruin", "わざわいのたま": "Beads of Ruin",
    "わざわいのつるぎ": "Sword of Ruin", "わたげ": "Cotton Down", "わるいてぐせ": "Pickpocket",
}
# ── Ability list (Japanese) derived from mapping ─────────────────────────
ABILITIES_JA: list[str] = list(ABILITY_JA_TO_EN.keys())

# ── Punching moves ─────────────────────────────────────
PUNCHING_MOVES_JA: frozenset[str] = frozenset([
    "アームハンマー", "アイスハンマー", "あんこくきょうだ", "かみなりパンチ", "きあいパンチ",
    "グロウパンチ", "コメットパンチ", "ジェットパンチ", "シャドーパンチ", "すいりゅうれんだ",
    "スカイアッパー", "ダブルパンツァー", "ドレインパンチ", "ばくれつパンチ", "バレットパンチ",
    "ピヨピヨパンチ", "ぶちかまし", "プラズマフィスト", "ふんどのこぶし", "ほのおのパンチ",
    "マッハパンチ", "メガトンパンチ", "れいとうパンチ", "れんぞくパンチ",
])
# ── Slicing moves ─────────────────────────────────────
SLICING_MOVES_JA: frozenset[str] = frozenset([
    "アクアカッター", "いあいぎり", "エアカッター", "エアスラッシュ", "がんせきアックス",
    "きょじゅうざん", "きりさく", "クロスポイズン", "サイコカッター", "サイコブレイド",
    "シェルブレード", "シザークロス", "シャドークロー", "しんぴのつるぎ", "せいなるつるぎ",
    "ソーラーブレード", "タキオンカッター", "つじぎり", "つばめがえし", "ドゲザン",
    "ドラゴンクロー", "ネズミざん", "はっぱカッター", "パワフルエッジ", "ひけん・ちえなみ",
    "フェイタルクロー", "ブレイククロー", "むねんのつるぎ", "リーフブレード", "れんぞくぎり",
])
# ── Pulse moves  ─────────────────────────────────────
PULSE_MOVES_JA: frozenset[str] = frozenset([
    "あくのはどう", "いやしのはどう", "こんげんのはどう", "だいちのはどう", "はどうだん",
    "みずのはどう", "りゅうのはどう",
])
# ── Bite moves ─────────────────────────────────────
BITE_MOVES_JA: frozenset[str] = frozenset([
    "エラがみ", "かみくだく", "かみつく", "かみなりのキバ", "くらいつく",
    "こおりのキバ", "サイコファング", "どくどくのキバ", "ひっさつまえば", "ほのおのキバ",
])
# ── Sound moves ─────────────────────────────────────
SOUND_MOVES_JA: frozenset[str] = frozenset([
    "いにしえのうた", "いびき", "いやしのすず", "いやなおと", "うたう",
    "うたかたのアリア", "エコーボイス", "オーバードライブ", "おしゃべり", "おたけび",
    "きんぞくおん", "くさぶえ", "サイコノイズ", "さわぐ", "スケイルノイズ",
    "すてゼリフ", "ソウルビート", "ダークパニック", "チャームボイス", "ちょうおんぱ",
    "とおぼえ", "ドラゴンエール", "ないしょばなし", "なきごえ", "バークアウト",
    "ハイパーボイス", "ばくおんぱ", "ぶきみなじゅもん", "フレアソング", "ブレイジングソウルビート",
    "ほえる", "ほろびのうた", "みわくのボイス", "むしのさざめき", "りんしょう"
])
# ── Wind moves ─────────────────────────────────────
WIND_MOVES_JA: frozenset[str] = frozenset([
    "エアカッター", "エアロブラスト", "おいかぜ", "かぜおこし", "かみなりあらし",
    "こがらしあらし", "こごえるかぜ", "すなあらし", "たつまき", "ねっさのあらし",
    "ねっぷう", "はなふぶき", "はるのあらし", "ふきとばし", "ふぶき",
    "ぼうふう", "ようせいのかぜ",
])
# ── Bomb moves ───────────────────────────────────────────
DAMP_BLOCKED_MOVES_JA: frozenset[str] = frozenset([
    "じばく", "だいばくはつ", "ビックリヘッド", "ミストバースト",
])
# ── Bullet moves ───────────────────────────────────────────
BULLET_MOVES_JA: frozenset[str] = frozenset([
    "アイスボール","アシッドボム","ウェザーボール","エナジーボール","エレキボール",
    "オクタンほう","かえんだん","かえんボール","かふんだんご","がんせきほう",
    "きあいだま","くちばしキャノン","ジャイロボール","シャドーボール","タネばくだん",
    "タネマシンガン","タマゴばくだん","たまなげ","でんじほう","どろばくだん",
    "はどうだん","ヘドロばくだん","マグネットボム","みずあめボム","ミストボール",
    "ロックブラスト",
])
# ── Reckless moves ─────────────────────────────────────
RECKLESS_MOVES_JA: frozenset[str] = frozenset([
    "アフロブレイク", "ウェーブタックル", "ウッドハンマー", "かかとおとし", "サンダーダイブ",
    "じごくぐるま", "すてみタックル", "とっしん", "とびげり", "とびひざげり",
    "はめつのひかり", "フレアドライブ", "ブレイブバード", "ボルテッカー", "もろはのずつき",
    "ワイルドボルト",
])

SHEER_FORCE_MOVES_JA: frozenset[str] = frozenset([
# ── Moves that lower the opponent's Pokémon's rank
    "オーロラビーム", "ようかいえき", "サイコキネシス", "あわ", "からみつく",
    "バブルこうせん", "じゃれつく", "はるのあらし", "うらみつらみ", "とびかかる",
    "トロピカルキック", "ひやみず", "ワイドブレイカー", "アクアブレイク", "かみくだく",
    "シャドーボーン", "アイアンテール", "3ぼんのや", "いわくだき", "シェルブレード",
    "ブレイククロー", "Gのちから", "ほのおのムチ", "らいめいげり", "ムーンフォース",
    "ミストボール", "ソウルクラッシュ", "バークアウト", "はいよるいちげき", "マジカルフレイム",
    "むしのていこう", "エナジーボール", "きあいだま", "シードフレア", "シャドーボール",
    "だいちのちから", "むしのさざめき", "ラスターカノン", "ラスターパージ", "アシッドボム",
    "りんごさん", "ルミナコリジョン", "エレキネット", "がんせきふうじ", "こがらしあらし",
    "こごえるかぜ", "こごえるせかい", "じならし", "とびつく", "ドラムアタック",
    "マッドショット", "ローキック", "オクタンほう", "グラスミキサー", "だくりゅう",
    "どろかけ", "どろばくだん", "ナイトバースト", "ミラーショット",
# ── Moves that raise your Pokémon's rank
    "メタルクロー", "コメットパンチ", "グロウパンチ", "はがねのつばさ", "ダイヤストーム",
    "バリアーラッシュ", "ほのおのまい", "チャージビーム", "しんぴのちから", "フレアソング",
    "アクアステップ", "オーラウイング", "オーラぐるま", "くさわけ", "こうそくスピン",
    "ニトロチャージ", "あやしいかぜ", "げんしのちから", "ぎんいろのかぜ", "ブレイジングソウルビート",
    "いっちょうあがり",
# ── Moves that can cause poison 
    "クロスポイズン", "ヘドロウェーブ", "ポイズンテール", "フェイタルクロー", "シェルアームズ",
    "ダブルニードル", "ダストシュート", "どくづき", "どくばり", "ヘドロこうげき",
    "ヘドロばくだん", "ポイズンアクセル", "スモッグ", "どくばりセンボン", "キラースピン",
# ── Moves that can cause paralysis
    "かみなりのキバ", "かみなりパンチ", "でんきショック", "10まんボルト", "フェイタルクロー",
    "かみなりあらし", "らいげき", "かみなり", "したでなめる", "スパーク",
    "とびはねる", "のしかかり", "はっけい", "ほうでん", "りゅうのいぶき",
    "ファイトアクセル", "フリーズボルト", "でんじほう", "ほっぺすりすり", "ライトニングサーフライド",
    "ボルテッカー", "びりびりエレキ", "トライアタック",
# ── Moves that can cause burn
    "かえんぐるま", "かえんほうしゃ", "かえんボール", "だいもんじ", "ねっぷう",
    "ひのこ", "フレアドライブ", "ブレイズキック", "ほのおのキバ", "ほのおのパンチ",
    "あおいほのお", "ねっさのあらし", "シャカシャカほう", "かえんだん", "コールドフレア",
    "スチームバースト", "ねっさのだいち", "ねっとう", "バーンアクセル", "ひゃっきやこう",
    "ふんえん", "せいなるほのお", "れんごく", "しっとのほのお",
    "めらめらバーン", "トライアタック",
# ── Moves that can cause freeze
    "こなゆき", "れいとうビーム", "ふぶき", "れいとうパンチ", "こおりのキバ",
    "フリーズドライ", "トライアタック","いてつくしせん",
# ── Moves that can cause sleep
    "いにしえのうた",
# ── Other
    "アンカーショット", "うたかたのアリア", "オリジンズスーパーノヴァ", "かげぬい", "がんせきアックス",
    "キラースピン", "こうそくスピン", "サイコノイズ", "しおづけ", "じごくづき",
    "ひけん・ちえなみ", "ぶきみなじゅもん", "みずあめボム",
])

# ── Contact move overrides ───────────────────────────────────────────────
CONTACT_MOVES_JA: frozenset[str] = frozenset([
    # Special-category moves that still make contact.
    "イナズマドライブ", "きりふだ", "くさむすび","しぼりとる", "ドレインキッス", 
    "はなびらのまい", "まとわりつく",
])
# Physical moves that do not make contact.
NON_CONTACT_PHYSICAL_MOVES_JA: frozenset[str] = frozenset([
    "3ぼんのや", "Gのちから", "アクアカッター", "いじげんラッシュ", "いっちょうあがり",
    "いわおとし", "いわなだれ", "うちおとす", "オーラぐるま", "おはかまいり",
    "かえんボール", "かげぬい", "がんせきふうじ", "がんせきほう", "グランドフォース",
    "クロスサンダー", "こうげきしれい", "こおりのつぶて", "ゴッドバード", "このは",
    "サイコカッター", "サウザンアロー", "サウザンウェーブ", "しおづけ", "じしん",
    "しぜんのめぐみ", "じならし", "じばく", "シャドーボーン", "じわれ",
    "スケイルショット", "スターアサルト", "ストーンエッジ", "すなじごく", "せいなるほのお",
    "ダークアクセル", "だいばくはつ", "だいふんげき", "ダイヤストーム", "ダストシュート",
    "タネばくだん", "タネマシンガン", "ダブルニードル", "タマゴばくだん", "たまなげ",
    "だんがいのつるぎ", "ツタこんぼう", "つららおとし", "つららばり", "デカハンマー",
    "どくばり", "どくばりセンボン", "とげキャノン", "ドラゴンアロー", "ドラムアタック",
    "トリックフラワー", "なげつける", "ネコにこばん", "バーンアクセル", "はっぱカッター",
    "はなふぶき", "ひみつのちから", "ひょうざんおろし", "ファイトアクセル", "フェイント",
    "ふくろだたき", "フリーズボルト", "ブリザードランス", "プレゼント", "ボーンラッシュ",
    "ポイズンアクセル", "ポルターガイスト", "ホネこんぼう", "ホネブーメラン", "マジカルアクセル",
    "マグニチュード", "マグネットボム", "ミサイルばり", "メタルバースト", "ロックブラスト",
    "シャドーアローズストライク", "ラジアルエッジストーム",
])

# ── Multi-hit moves: name → (min_hits, max_hits, default_hits) ───────────
MULTI_HIT_MOVES_JA: dict[str, tuple[int, int, int]] = {
    # ── 2 times only
    "ダブルニードル": (2, 2, 2),
    "にどげり": (2, 2, 2),
    "ホネブーメラン": (2, 2, 2),
    "ダブルアタック": (2, 2, 2),
    "ギアソーサー": (2, 2, 2),
    "ダブルチョップ": (2, 2, 2),
    "ダブルパンツァー": (2, 2, 2),
    "ドラゴンアロー": (2, 2, 2),
    "ダブルウイング": (2, 2, 2),
    "タキオンカッター": (2, 2, 2),
    "ツインビーム": (2, 2, 2),
    # ── 3 times only
    "すいりゅうれんだ": (3, 3, 3),
    "トリプルダイブ": (3, 3, 3),
    # ── 2-5 times
    "おうふくビンタ": (2, 5, 5),
    "たまなげ": (2, 5, 5),
    "とげキャノン": (2, 5, 5),
    "ミサイルばり": (2, 5, 5),
    "みだれづき": (2, 5, 5),
    "みだれひっかき": (2, 5, 5),
    "れんぞくパンチ": (2, 5, 5),
    "ボーンラッシュ": (2, 5, 5),
    "タネマシンガン": (2, 5, 5),
    "つっぱり": (2, 5, 5),
    "つららばり": (2, 5, 5),
    "ロックブラスト": (2, 5, 5),
    "スイープビンタ": (2, 5, 5),
    "みずしゅりけん": (2, 5, 5),
    "スケイルショット": (2, 5, 5),
    # ── 1-3 times
    "トリプルアクセル": (1, 3, 3),
    "トリプルキック": (1, 3, 3),
    # ── Other
    "ふくろだたき": (1, 5, 2),
}

# ── Stealth Rock multiplier by type chart (rock vs defender type) ──────
STEALTH_ROCK_CHART: dict[str, float] = {
    "fire":     2.0, "ice":    2.0, "flying": 2.0, "bug":    2.0,
    "rock":     0.5, "steel":  0.5, "fighting":0.5, "ground": 0.5,
}

# OCR throttle interval (ms) between OCR calls
OCR_INTERVAL_MS = 800

# PokeAPI base URL
POKEAPI_BASE = "https://pokeapi.co/api/v2"

# Pokemon Champions level (all Pokemon at level 50)
GAME_LEVEL = 50

# EV points × 8 = traditional EV value (confirmed from screenshot analysis)
EV_POINT_FACTOR = 8
