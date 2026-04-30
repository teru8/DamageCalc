import re
import sqlite3
from pathlib import Path
from src.models import PokemonInstance, SpeciesInfo, MoveInfo
from src.constants import TYPE_EN_TO_JA, TYPE_JA_TO_EN

DEFAULT_USAGE_SEASON = "M-1"
_ACTIVE_USAGE_SEASON = DEFAULT_USAGE_SEASON
_TERA_EN_TO_JA: dict[str, str] = {
    **TYPE_EN_TO_JA,
    "stellar": "ステラ",
}
_TERA_JA_TO_EN: dict[str, str] = {
    **TYPE_JA_TO_EN,
    "ステラ": "stellar",
}


def _terastal_to_db_ja(terastal_type_en: str) -> str:
    en = (terastal_type_en or "").strip().lower()
    if not en:
        return "ノーマル"
    return _TERA_EN_TO_JA.get(en, "ノーマル")


def _terastal_from_db_ja(terastal_type_db: str) -> str:
    ja = (terastal_type_db or "").strip()
    if not ja:
        return "normal"
    return _TERA_JA_TO_EN.get(ja, "normal")


def normalize_season_token(season: str | None) -> str:
    text = str(season or "").strip().upper()
    if not text:
        return DEFAULT_USAGE_SEASON
    text = re.sub(r"\s+", "", text)
    return text


def get_active_usage_season() -> str:
    return _ACTIVE_USAGE_SEASON


def set_active_usage_season(season: str | None) -> str:
    global _ACTIVE_USAGE_SEASON
    _ACTIVE_USAGE_SEASON = normalize_season_token(season)
    return _ACTIVE_USAGE_SEASON


def _season_or_active(season: str | None) -> str:
    return normalize_season_token(season or _ACTIVE_USAGE_SEASON)


def _db_path() -> Path:
    cache = Path.home() / ".pokemon_damage_calc"
    cache.mkdir(exist_ok=True)
    return cache / "data.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute("PRAGMA table_info({})".format(table_name)).fetchall()
    return [str(row["name"]) for row in rows]


def _migrate_legacy_usage_tables(conn: sqlite3.Connection) -> None:
    legacy_tables = {
        "pokemon_usage": ["pokemon_name_ja", "usage_rank"],
        "usage_option": ["pokemon_name_ja", "category", "option_name_ja", "usage_rank"],
        "usage_ranking": ["pokemon_name_ja", "move_name_ja", "usage_rank"],
        "usage_effort": [
            "pokemon_name_ja",
            "usage_rank",
            "hp_pt",
            "attack_pt",
            "defense_pt",
            "sp_attack_pt",
            "sp_defense_pt",
            "speed_pt",
            "usage_percent",
        ],
    }

    needs_migration = False
    for table_name in legacy_tables:
        cols = _table_columns(conn, table_name)
        if cols and "season" not in cols:
            needs_migration = True
            break
    if not needs_migration:
        return

    cur = conn.cursor()
    if "season" not in _table_columns(conn, "pokemon_usage"):
        cur.execute("ALTER TABLE pokemon_usage RENAME TO pokemon_usage_legacy")
        cur.executescript(
            """
            CREATE TABLE pokemon_usage (
                season          TEXT NOT NULL DEFAULT 'M-1',
                pokemon_name_ja TEXT NOT NULL,
                usage_rank      INTEGER NOT NULL,
                PRIMARY KEY (season, pokemon_name_ja)
            );
            INSERT OR REPLACE INTO pokemon_usage
            (season, pokemon_name_ja, usage_rank)
            SELECT 'M-1', pokemon_name_ja, usage_rank
            FROM pokemon_usage_legacy;
            DROP TABLE pokemon_usage_legacy;
            """
        )

    if "season" not in _table_columns(conn, "usage_option"):
        cur.execute("ALTER TABLE usage_option RENAME TO usage_option_legacy")
        cur.executescript(
            """
            CREATE TABLE usage_option (
                season          TEXT NOT NULL DEFAULT 'M-1',
                pokemon_name_ja TEXT NOT NULL,
                category        TEXT NOT NULL,
                option_name_ja  TEXT NOT NULL,
                usage_rank      INTEGER NOT NULL,
                PRIMARY KEY (season, pokemon_name_ja, category, option_name_ja)
            );
            INSERT OR REPLACE INTO usage_option
            (season, pokemon_name_ja, category, option_name_ja, usage_rank)
            SELECT 'M-1', pokemon_name_ja, category, option_name_ja, usage_rank
            FROM usage_option_legacy;
            DROP TABLE usage_option_legacy;
            """
        )

    if "season" not in _table_columns(conn, "usage_ranking"):
        cur.execute("ALTER TABLE usage_ranking RENAME TO usage_ranking_legacy")
        cur.executescript(
            """
            CREATE TABLE usage_ranking (
                season          TEXT NOT NULL DEFAULT 'M-1',
                pokemon_name_ja TEXT,
                move_name_ja    TEXT,
                usage_rank      INTEGER,
                PRIMARY KEY (season, pokemon_name_ja, move_name_ja)
            );
            INSERT OR REPLACE INTO usage_ranking
            (season, pokemon_name_ja, move_name_ja, usage_rank)
            SELECT 'M-1', pokemon_name_ja, move_name_ja, usage_rank
            FROM usage_ranking_legacy;
            DROP TABLE usage_ranking_legacy;
            """
        )

    if "season" not in _table_columns(conn, "usage_effort"):
        cur.execute("ALTER TABLE usage_effort RENAME TO usage_effort_legacy")
        cur.executescript(
            """
            CREATE TABLE usage_effort (
                season          TEXT NOT NULL DEFAULT 'M-1',
                pokemon_name_ja TEXT NOT NULL,
                usage_rank      INTEGER NOT NULL,
                hp_pt           INTEGER NOT NULL,
                attack_pt       INTEGER NOT NULL,
                defense_pt      INTEGER NOT NULL,
                sp_attack_pt    INTEGER NOT NULL,
                sp_defense_pt   INTEGER NOT NULL,
                speed_pt        INTEGER NOT NULL,
                usage_percent   REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (season, pokemon_name_ja, usage_rank)
            );
            INSERT OR REPLACE INTO usage_effort
            (season, pokemon_name_ja, usage_rank, hp_pt, attack_pt, defense_pt, sp_attack_pt, sp_defense_pt, speed_pt, usage_percent)
            SELECT 'M-1', pokemon_name_ja, usage_rank, hp_pt, attack_pt, defense_pt, sp_attack_pt, sp_defense_pt, speed_pt, usage_percent
            FROM usage_effort_legacy;
            DROP TABLE usage_effort_legacy;
            """
        )

    cur.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_pokemon_usage_rank
            ON pokemon_usage(season, usage_rank);
        CREATE INDEX IF NOT EXISTS idx_usage_option_lookup
            ON usage_option(season, pokemon_name_ja, category, usage_rank);
        CREATE INDEX IF NOT EXISTS idx_usage_effort_lookup
            ON usage_effort(season, pokemon_name_ja, usage_rank);
        """
    )


def init_db() -> None:
    conn = get_connection()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS species_cache (
        species_id   INTEGER PRIMARY KEY,
        name_ja      TEXT NOT NULL,
        name_en      TEXT NOT NULL,
        type1        TEXT NOT NULL,
        type2        TEXT DEFAULT '',
        base_hp      INTEGER,
        base_attack  INTEGER,
        base_defense INTEGER,
        base_sp_attack  INTEGER,
        base_sp_defense INTEGER,
        base_speed   INTEGER,
        weight_kg    REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS move_cache (
        move_id   INTEGER PRIMARY KEY,
        name_ja   TEXT,
        name_en   TEXT NOT NULL,
        type_name TEXT,
        category  TEXT,
        power     INTEGER DEFAULT 0,
        accuracy  INTEGER DEFAULT 100,
        pp        INTEGER DEFAULT 10,
        priority  INTEGER DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_move_ja ON move_cache(name_ja);
    CREATE INDEX IF NOT EXISTS idx_species_ja ON species_cache(name_ja);

    CREATE TABLE IF NOT EXISTS registered_pokemon (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        species_id    INTEGER NOT NULL,
        name_ja       TEXT NOT NULL,
        name_en       TEXT NOT NULL,
        types_json    TEXT DEFAULT '[]',
        nature        TEXT DEFAULT 'まじめ',
        ability       TEXT DEFAULT '',
        item          TEXT DEFAULT '',
        hp            INTEGER DEFAULT 0,
        attack        INTEGER DEFAULT 0,
        defense       INTEGER DEFAULT 0,
        sp_attack     INTEGER DEFAULT 0,
        sp_defense    INTEGER DEFAULT 0,
        speed         INTEGER DEFAULT 0,
        ev_hp         INTEGER DEFAULT 0,
        ev_attack     INTEGER DEFAULT 0,
        ev_defense    INTEGER DEFAULT 0,
        ev_sp_attack  INTEGER DEFAULT 0,
        ev_sp_defense INTEGER DEFAULT 0,
        ev_speed      INTEGER DEFAULT 0,
        terastal_type TEXT DEFAULT 'ノーマル',
        move1         TEXT DEFAULT '',
        move2         TEXT DEFAULT '',
        move3         TEXT DEFAULT '',
        move4         TEXT DEFAULT '',
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS usage_ranking (
        season          TEXT NOT NULL DEFAULT 'M-1',
        pokemon_name_ja TEXT,
        move_name_ja    TEXT,
        usage_rank      INTEGER,
        PRIMARY KEY (season, pokemon_name_ja, move_name_ja)
    );

    CREATE TABLE IF NOT EXISTS pokemon_usage (
        season          TEXT NOT NULL DEFAULT 'M-1',
        pokemon_name_ja TEXT NOT NULL,
        usage_rank      INTEGER NOT NULL,
        PRIMARY KEY (season, pokemon_name_ja)
    );

    CREATE TABLE IF NOT EXISTS usage_option (
        season          TEXT NOT NULL DEFAULT 'M-1',
        pokemon_name_ja TEXT NOT NULL,
        category        TEXT NOT NULL,
        option_name_ja  TEXT NOT NULL,
        usage_rank      INTEGER NOT NULL,
        PRIMARY KEY (season, pokemon_name_ja, category, option_name_ja)
    );

    CREATE TABLE IF NOT EXISTS usage_effort (
        season          TEXT NOT NULL DEFAULT 'M-1',
        pokemon_name_ja TEXT NOT NULL,
        usage_rank      INTEGER NOT NULL,
        hp_pt           INTEGER NOT NULL,
        attack_pt       INTEGER NOT NULL,
        defense_pt      INTEGER NOT NULL,
        sp_attack_pt    INTEGER NOT NULL,
        sp_defense_pt   INTEGER NOT NULL,
        speed_pt        INTEGER NOT NULL,
        usage_percent   REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (season, pokemon_name_ja, usage_rank)
    );

    CREATE TABLE IF NOT EXISTS species_move_cache (
        species_id INTEGER NOT NULL,
        move_id    INTEGER NOT NULL,
        PRIMARY KEY (species_id, move_id)
    );

    CREATE INDEX IF NOT EXISTS idx_pokemon_usage_rank
        ON pokemon_usage(season, usage_rank);
    CREATE INDEX IF NOT EXISTS idx_usage_option_lookup
        ON usage_option(season, pokemon_name_ja, category, usage_rank);
    CREATE INDEX IF NOT EXISTS idx_usage_effort_lookup
        ON usage_effort(season, pokemon_name_ja, usage_rank);
    CREATE INDEX IF NOT EXISTS idx_species_move_lookup
        ON species_move_cache(species_id, move_id);

    CREATE TABLE IF NOT EXISTS app_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)
    _migrate_legacy_usage_tables(conn)
    species_cols = [row["name"] for row in c.execute("PRAGMA table_info(species_cache)").fetchall()]
    if "weight_kg" not in species_cols:
        c.execute("ALTER TABLE species_cache ADD COLUMN weight_kg REAL DEFAULT 0")
    pokemon_cols = [row["name"] for row in c.execute("PRAGMA table_info(registered_pokemon)").fetchall()]
    if "usage_name" not in pokemon_cols:
        c.execute("ALTER TABLE registered_pokemon ADD COLUMN usage_name TEXT DEFAULT ''")
    if "terastal_type" not in pokemon_cols:
        c.execute("ALTER TABLE registered_pokemon ADD COLUMN terastal_type TEXT DEFAULT 'ノーマル'")
    # Normalize terastal_type storage to Japanese labels in DB.
    c.execute(
        """
        UPDATE registered_pokemon
        SET terastal_type='ノーマル'
        WHERE terastal_type IS NULL OR TRIM(terastal_type)=''
        """
    )
    for en, ja in _TERA_EN_TO_JA.items():
        c.execute(
            "UPDATE registered_pokemon SET terastal_type=? WHERE terastal_type=?",
            (ja, en),
        )
    c.execute(
        """
        UPDATE registered_pokemon
        SET terastal_type='ノーマル'
        WHERE terastal_type IS NULL OR TRIM(terastal_type)=''
        """
    )
    ev_migration_done = c.execute(
        "SELECT value FROM app_meta WHERE key='registered_pokemon_ev_storage_v2'"
    ).fetchone()
    if ev_migration_done is None:
        c.execute(
            """
            UPDATE registered_pokemon
            SET
                ev_hp = CASE WHEN ev_hp > 0 THEN MAX(ev_hp - 4, 0) ELSE 0 END,
                ev_attack = CASE WHEN ev_attack > 0 THEN MAX(ev_attack - 4, 0) ELSE 0 END,
                ev_defense = CASE WHEN ev_defense > 0 THEN MAX(ev_defense - 4, 0) ELSE 0 END,
                ev_sp_attack = CASE WHEN ev_sp_attack > 0 THEN MAX(ev_sp_attack - 4, 0) ELSE 0 END,
                ev_sp_defense = CASE WHEN ev_sp_defense > 0 THEN MAX(ev_sp_defense - 4, 0) ELSE 0 END,
                ev_speed = CASE WHEN ev_speed > 0 THEN MAX(ev_speed - 4, 0) ELSE 0 END
            """
        )
        c.execute(
            """
            INSERT OR REPLACE INTO app_meta (key, value)
            VALUES ('registered_pokemon_ev_storage_v2', '1')
            """
        )
    conn.commit()
    conn.close()
    
    # Import usage data from JSON if exists in project root
    import_usage_from_json()


# ── Species ──────────────────────────────────────────────────────────

def upsert_species(s: SpeciesInfo) -> None:
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO species_cache
        (species_id, name_ja, name_en, type1, type2,
         base_hp, base_attack, base_defense, base_sp_attack, base_sp_defense, base_speed, weight_kg)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (s.species_id, s.name_ja, s.name_en, s.type1, s.type2,
          s.base_hp, s.base_attack, s.base_defense,
          s.base_sp_attack, s.base_sp_defense, s.base_speed, float(s.weight_kg or 0)))
    conn.commit()
    conn.close()


def get_species_by_name_ja(name_ja: str) -> SpeciesInfo | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM species_cache WHERE name_ja=?", (name_ja,)
        ).fetchone()
        if row is not None:
            return SpeciesInfo(**dict(row))
        return None
    finally:
        conn.close()


def get_species_by_id(species_id: int) -> SpeciesInfo | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM species_cache WHERE species_id=?", (species_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return SpeciesInfo(**dict(row))


def has_species_learnset(species_id: int) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM species_move_cache WHERE species_id=? LIMIT 1",
        (species_id,),
    ).fetchone()
    conn.close()
    return row is not None


def replace_species_learnset(species_id: int, move_ids: list[int]) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM species_move_cache WHERE species_id=?", (species_id,))
    if move_ids:
        rows = [(species_id, move_id) for move_id in sorted(set(move_ids))]
        conn.executemany(
            "INSERT OR REPLACE INTO species_move_cache VALUES (?,?)",
            rows,
        )
    conn.commit()
    conn.close()


# ── Moves ─────────────────────────────────────────────────────────────

def upsert_move(m: MoveInfo, move_id: int) -> None:
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO move_cache
        (move_id, name_ja, name_en, type_name, category, power, accuracy, pp, priority)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (move_id, m.name_ja, m.name_en, m.type_name, m.category,
          m.power, m.accuracy, m.pp, m.priority))
    conn.commit()
    conn.close()


def get_move_by_name_ja(name_ja: str) -> MoveInfo | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM move_cache WHERE name_ja=?", (name_ja,)).fetchone()
    conn.close()
    if row is None:
        return None
    return MoveInfo(
        name_ja=row["name_ja"] or name_ja,
        name_en=row["name_en"],
        type_name=row["type_name"] or "normal",
        category=row["category"] or "physical",
        power=row["power"],
        accuracy=row["accuracy"],
        pp=row["pp"],
        priority=row["priority"],
    )


# ── Registered Pokemon ────────────────────────────────────────────────

def save_pokemon(pokemon: PokemonInstance) -> int:
    import json
    def _to_db_ev(ev_value: int) -> int:
        # Champions points are handled as multiples of 8 in-app.
        # Persist to DB as (8x points - 4), with zero staying zero.
        value = int(ev_value or 0)
        if value <= 0:
            return 0
        return max(0, value - 4)

    conn = get_connection()
    moves = (pokemon.moves + ["", "", "", ""])[:4]
    ev_hp_db = _to_db_ev(pokemon.ev_hp)
    ev_attack_db = _to_db_ev(pokemon.ev_attack)
    ev_defense_db = _to_db_ev(pokemon.ev_defense)
    ev_sp_attack_db = _to_db_ev(pokemon.ev_sp_attack)
    ev_sp_defense_db = _to_db_ev(pokemon.ev_sp_defense)
    ev_speed_db = _to_db_ev(pokemon.ev_speed)
    if pokemon.db_id:
        conn.execute("""
            UPDATE registered_pokemon SET
            species_id=?, name_ja=?, usage_name=?, name_en=?, types_json=?,
            nature=?, ability=?, item=?,
            hp=?, attack=?, defense=?, sp_attack=?, sp_defense=?, speed=?,
            ev_hp=?, ev_attack=?, ev_defense=?, ev_sp_attack=?, ev_sp_defense=?, ev_speed=?,
            terastal_type=?,
            move1=?, move2=?, move3=?, move4=?,
            updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (pokemon.species_id, pokemon.name_ja, pokemon.usage_name, pokemon.name_en,
              json.dumps(pokemon.types), pokemon.nature, pokemon.ability, pokemon.item,
              pokemon.hp, pokemon.attack, pokemon.defense,
              pokemon.sp_attack, pokemon.sp_defense, pokemon.speed,
              ev_hp_db, ev_attack_db, ev_defense_db,
              ev_sp_attack_db, ev_sp_defense_db, ev_speed_db,
              _terastal_to_db_ja(pokemon.terastal_type),
              moves[0], moves[1], moves[2], moves[3],
              pokemon.db_id))
        new_id = pokemon.db_id
    else:
        cur = conn.execute("""
            INSERT INTO registered_pokemon
            (species_id, name_ja, usage_name, name_en, types_json,
             nature, ability, item,
             hp, attack, defense, sp_attack, sp_defense, speed,
             ev_hp, ev_attack, ev_defense, ev_sp_attack, ev_sp_defense, ev_speed,
             terastal_type,
             move1, move2, move3, move4)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (pokemon.species_id, pokemon.name_ja, pokemon.usage_name, pokemon.name_en,
              json.dumps(pokemon.types), pokemon.nature, pokemon.ability, pokemon.item,
              pokemon.hp, pokemon.attack, pokemon.defense,
              pokemon.sp_attack, pokemon.sp_defense, pokemon.speed,
              ev_hp_db, ev_attack_db, ev_defense_db,
              ev_sp_attack_db, ev_sp_defense_db, ev_speed_db,
              _terastal_to_db_ja(pokemon.terastal_type),
              moves[0], moves[1], moves[2], moves[3]))
        new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def load_all_pokemon() -> list[PokemonInstance]:
    import json
    def _from_db_ev(ev_value: int) -> int:
        # Restore in-app representation from persisted (8x points - 4).
        value = int(ev_value or 0)
        if value <= 0:
            return 0
        return value + 4

    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM registered_pokemon ORDER BY updated_at DESC").fetchall()
    conn.close()
    result = []
    for row in rows:
        p = PokemonInstance(
            species_id=row["species_id"],
            name_ja=row["name_ja"],
            usage_name=row["usage_name"] or "",
            name_en=row["name_en"],
            types=json.loads(row["types_json"] or "[]"),
            nature=row["nature"],
            ability=row["ability"],
            item=row["item"],
            hp=row["hp"], attack=row["attack"], defense=row["defense"],
            sp_attack=row["sp_attack"], sp_defense=row["sp_defense"],
            speed=row["speed"],
            ev_hp=_from_db_ev(row["ev_hp"]), ev_attack=_from_db_ev(row["ev_attack"]),
            ev_defense=_from_db_ev(row["ev_defense"]), ev_sp_attack=_from_db_ev(row["ev_sp_attack"]),
            ev_sp_defense=_from_db_ev(row["ev_sp_defense"]), ev_speed=_from_db_ev(row["ev_speed"]),
            terastal_type=_terastal_from_db_ja(row["terastal_type"]),
            moves=[m for m in [row["move1"], row["move2"],
                                row["move3"], row["move4"]] if m],
            db_id=row["id"],
        )
        result.append(p)
    return result


def delete_pokemon(db_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM registered_pokemon WHERE id=?", (db_id,))
    conn.commit()
    conn.close()


# ── Usage ranking ─────────────────────────────────────────────────────

def save_usage_ranking(
    data: list[tuple[str, str, int]],
    season: str | None = None,
) -> None:
    """data: list of (pokemon_name_ja, move_name_ja, rank)"""
    season_token = _season_or_active(season)
    conn = get_connection()
    conn.execute("DELETE FROM usage_ranking WHERE season=?", (season_token,))
    if data:
        conn.executemany(
            """
            INSERT OR REPLACE INTO usage_ranking
            (season, pokemon_name_ja, move_name_ja, usage_rank)
            VALUES (?,?,?,?)
            """,
            [(season_token, pokemon_name, move_name, rank) for pokemon_name, move_name, rank in data],
        )
    conn.commit()
    conn.close()


def save_usage_snapshot(
    pokemon_rows: list[tuple[str, int]],
    move_rows: list[tuple[str, str, int]],
    ability_rows: list[tuple[str, str, int]],
    item_rows: list[tuple[str, str, int]],
    nature_rows: list[tuple[str, str, int]] | None = None,
    effort_rows: list[tuple[str, int, int, int, int, int, int, int, float]] | None = None,
    season: str | None = None,
) -> None:
    season_token = _season_or_active(season)
    if nature_rows is None:
        nature_rows = []
    if effort_rows is None:
        effort_rows = []
    conn = get_connection()
    conn.execute("DELETE FROM pokemon_usage WHERE season=?", (season_token,))
    conn.execute("DELETE FROM usage_option WHERE season=?", (season_token,))
    conn.execute("DELETE FROM usage_ranking WHERE season=?", (season_token,))
    conn.execute("DELETE FROM usage_effort WHERE season=?", (season_token,))

    if pokemon_rows:
        conn.executemany(
            """
            INSERT OR REPLACE INTO pokemon_usage
            (season, pokemon_name_ja, usage_rank)
            VALUES (?,?,?)
            """,
            [(season_token, pokemon_name, rank) for pokemon_name, rank in pokemon_rows],
        )

    option_rows = (
        [(season_token, pokemon_name, "move", option_name, rank) for pokemon_name, option_name, rank in move_rows]
        + [(season_token, pokemon_name, "ability", option_name, rank) for pokemon_name, option_name, rank in ability_rows]
        + [(season_token, pokemon_name, "item", option_name, rank) for pokemon_name, option_name, rank in item_rows]
        + [(season_token, pokemon_name, "nature", option_name, rank) for pokemon_name, option_name, rank in nature_rows]
    )
    if option_rows:
        conn.executemany(
            """
            INSERT OR REPLACE INTO usage_option
            (season, pokemon_name_ja, category, option_name_ja, usage_rank)
            VALUES (?,?,?,?,?)
            """,
            option_rows,
        )

    if move_rows:
        conn.executemany(
            """
            INSERT OR REPLACE INTO usage_ranking
            (season, pokemon_name_ja, move_name_ja, usage_rank)
            VALUES (?,?,?,?)
            """,
            [(season_token, pokemon_name, move_name, rank) for pokemon_name, move_name, rank in move_rows],
        )

    if effort_rows:
        conn.executemany(
            """
            INSERT OR REPLACE INTO usage_effort
            (season, pokemon_name_ja, usage_rank, hp_pt, attack_pt, defense_pt, sp_attack_pt, sp_defense_pt, speed_pt, usage_percent)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (season_token, pokemon_name, usage_rank, hp_pt, attack_pt, defense_pt, sp_attack_pt, sp_defense_pt, speed_pt, usage_percent)
                for (
                    pokemon_name,
                    usage_rank,
                    hp_pt,
                    attack_pt,
                    defense_pt,
                    sp_attack_pt,
                    sp_defense_pt,
                    speed_pt,
                    usage_percent,
                ) in effort_rows
            ],
        )

    conn.commit()
    conn.close()


def get_all_species_names_ja() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT name_ja FROM species_cache ORDER BY name_ja").fetchall()
    conn.close()
    return [r["name_ja"] for r in rows]


def get_available_usage_seasons() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT season FROM pokemon_usage WHERE season IS NOT NULL AND season != '' ORDER BY season DESC"
    ).fetchall()
    conn.close()
    seasons = [normalize_season_token(row["season"]) for row in rows if row["season"]]
    if DEFAULT_USAGE_SEASON not in seasons:
        seasons.append(DEFAULT_USAGE_SEASON)
    seen: set[str] = set()
    ordered: list[str] = []
    for season in seasons:
        if season in seen:
            continue
        seen.add(season)
        ordered.append(season)
    return ordered


def get_usage_pool_species_names(season: str | None = None) -> list[str]:
    season_token = _season_or_active(season)
    conn = get_connection()
    ranked_rows = conn.execute(
        """
        SELECT pokemon_name_ja
        FROM pokemon_usage
        WHERE season=?
        ORDER BY usage_rank ASC
        """,
        (season_token,),
    ).fetchall()
    all_rows = conn.execute(
        "SELECT name_ja FROM species_cache ORDER BY species_id ASC"
    ).fetchall()
    conn.close()

    ranked: list[str] = []
    seen: set[str] = set()
    for row in ranked_rows:
        name = str(row["pokemon_name_ja"] or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        ranked.append(name)

    if not ranked:
        return []

    extras: list[str] = []
    for row in all_rows:
        name = str(row["name_ja"] or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        extras.append(name)
    return ranked + extras


def get_species_names_by_usage(
    season: str | None = None,
    include_all_species: bool = True,
) -> list[str]:
    season_token = _season_or_active(season)
    conn = get_connection()
    ranked_rows = conn.execute(
        """
        SELECT pokemon_name_ja
        FROM pokemon_usage
        WHERE season=?
        ORDER BY usage_rank ASC
        """,
        (season_token,),
    ).fetchall()
    all_rows = conn.execute(
        "SELECT name_ja FROM species_cache ORDER BY name_ja ASC"
    ).fetchall()
    conn.close()

    ordered: list[str] = []
    seen: set[str] = set()
    for row in ranked_rows:
        name = row["pokemon_name_ja"]
        if name and name not in seen:
            ordered.append(name)
            seen.add(name)
    if include_all_species:
        for row in all_rows:
            name = row["name_ja"]
            if name and name not in seen:
                ordered.append(name)
                seen.add(name)
    return ordered


def get_all_species_name_entries() -> list[tuple[int, str, str]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT species_id, name_ja, name_en FROM species_cache ORDER BY species_id"
    ).fetchall()
    conn.close()
    return [(r["species_id"], r["name_ja"], r["name_en"]) for r in rows]


def get_all_species() -> list[SpeciesInfo]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM species_cache ORDER BY species_id ASC"
    ).fetchall()
    conn.close()
    return [SpeciesInfo(**dict(row)) for row in rows]


def get_species_usage_rank_map(season: str | None = None) -> dict[str, int]:
    season_token = _season_or_active(season)
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT pokemon_name_ja, usage_rank
        FROM pokemon_usage
        WHERE season=?
        """,
        (season_token,),
    ).fetchall()
    conn.close()
    return {
        row["pokemon_name_ja"]: row["usage_rank"]
        for row in rows
        if row["pokemon_name_ja"]
    }


def get_move_by_id(move_id: int) -> MoveInfo | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM move_cache WHERE move_id=?", (move_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return MoveInfo(
        name_ja=row["name_ja"] or "",
        name_en=row["name_en"],
        type_name=row["type_name"] or "normal",
        category=row["category"] or "physical",
        power=row["power"],
        accuracy=row["accuracy"],
        pp=row["pp"],
        priority=row["priority"],
    )


def get_all_move_names_ja() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT name_ja FROM move_cache WHERE name_ja IS NOT NULL ORDER BY name_ja"
    ).fetchall()
    conn.close()
    return [r["name_ja"] for r in rows]


def get_all_moves() -> list[MoveInfo]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM move_cache
        WHERE name_ja IS NOT NULL AND name_ja != ''
        ORDER BY name_ja ASC
    """).fetchall()
    conn.close()
    result: list[MoveInfo] = []
    for row in rows:
        result.append(MoveInfo(
            name_ja=row["name_ja"],
            name_en=row["name_en"],
            type_name=row["type_name"] or "normal",
            category=row["category"] or "physical",
            power=row["power"],
            accuracy=row["accuracy"],
            pp=row["pp"],
            priority=row["priority"],
        ))
    return result


def get_species_names_by_move(move_name_ja: str) -> list[str]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT s.name_ja
        FROM move_cache m
        JOIN species_move_cache sm ON sm.move_id = m.move_id
        JOIN species_cache s ON s.species_id = sm.species_id
        WHERE m.name_ja=?
        ORDER BY s.name_ja ASC
    """, (move_name_ja,)).fetchall()
    conn.close()
    return [row["name_ja"] for row in rows]


def get_species_names_by_ability_usage(
    ability_name_ja: str,
    season: str | None = None,
) -> list[str]:
    season_token = _season_or_active(season)
    conn = get_connection()
    rows = conn.execute("""
        SELECT pokemon_name_ja
        FROM usage_option
        WHERE season=? AND category='ability' AND option_name_ja=?
        ORDER BY usage_rank ASC
    """, (season_token, ability_name_ja)).fetchall()
    conn.close()
    return [row["pokemon_name_ja"] for row in rows if row["pokemon_name_ja"]]


def get_all_usage_ability_names(season: str | None = None) -> list[str]:
    season_token = _season_or_active(season)
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT option_name_ja
        FROM usage_option
        WHERE season=? AND category='ability' AND option_name_ja != ''
        ORDER BY option_name_ja ASC
    """, (season_token,)).fetchall()
    conn.close()
    return [row["option_name_ja"] for row in rows if row["option_name_ja"]]


def get_moves_for_species(species_id: int) -> list[MoveInfo]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT m.*
        FROM species_move_cache sm
        JOIN move_cache m ON m.move_id = sm.move_id
        WHERE sm.species_id=? AND m.name_ja IS NOT NULL AND m.name_ja != ''
        ORDER BY m.name_ja ASC
    """, (species_id,)).fetchall()
    conn.close()
    result: list[MoveInfo] = []
    for row in rows:
        result.append(MoveInfo(
            name_ja=row["name_ja"],
            name_en=row["name_en"],
            type_name=row["type_name"] or "normal",
            category=row["category"] or "physical",
            power=row["power"],
            accuracy=row["accuracy"],
            pp=row["pp"],
            priority=row["priority"],
        ))
    return result


def _usage_name_variants(name: str) -> list[str]:
    """Return lookup name variants to try in order.

    Handles:
    - Full-width ↔ half-width paren mismatch (species_cache uses 「（）」,
      pokedb_tokyo stores「()」)
    - Gender form base name fallback (pokechamdb stores base name e.g.「イダイトウ」
      instead of「イダイトウ(オスのすがた)」)
    """
    import re as _re
    seen: list[str] = []
    for v in [
        name,
        name.replace("（", "(").replace("）", ")"),
    ]:
        if v not in seen:
            seen.append(v)
    base = _re.sub(r"\s*\((?:オス|メス)のすがた\)\s*$", "", seen[-1]).strip()
    if base and base not in seen:
        seen.append(base)
    return seen


def get_moves_by_usage(
    pokemon_name_ja: str,
    season: str | None = None,
) -> list[str]:
    """Return move names sorted by usage rank for the given Pokemon."""
    season_token = _season_or_active(season)
    conn = get_connection()
    for name in _usage_name_variants(pokemon_name_ja):
        rows = conn.execute("""
            SELECT option_name_ja FROM usage_option
            WHERE season=? AND pokemon_name_ja=? AND category='move'
            ORDER BY usage_rank ASC
        """, (season_token, name)).fetchall()
        if rows:
            conn.close()
            return [r["option_name_ja"] for r in rows]

    for name in _usage_name_variants(pokemon_name_ja):
        rows = conn.execute("""
            SELECT move_name_ja FROM usage_ranking
            WHERE season=? AND pokemon_name_ja=?
            ORDER BY usage_rank ASC
        """, (season_token, name)).fetchall()
        if rows:
            conn.close()
            return [r["move_name_ja"] for r in rows]

    conn.close()
    return []


def get_abilities_by_usage(
    pokemon_name_ja: str,
    season: str | None = None,
) -> list[str]:
    season_token = _season_or_active(season)
    conn = get_connection()
    for name in _usage_name_variants(pokemon_name_ja):
        rows = conn.execute("""
            SELECT option_name_ja FROM usage_option
            WHERE season=? AND pokemon_name_ja=? AND category='ability'
            ORDER BY usage_rank ASC
        """, (season_token, name)).fetchall()
        if rows:
            conn.close()
            return [r["option_name_ja"] for r in rows]
    conn.close()
    return []


def get_items_by_usage(
    pokemon_name_ja: str,
    season: str | None = None,
) -> list[str]:
    season_token = _season_or_active(season)
    conn = get_connection()
    for name in _usage_name_variants(pokemon_name_ja):
        rows = conn.execute("""
            SELECT option_name_ja FROM usage_option
            WHERE season=? AND pokemon_name_ja=? AND category='item'
            ORDER BY usage_rank ASC
        """, (season_token, name)).fetchall()
        if rows:
            conn.close()
            return [r["option_name_ja"] for r in rows]
    conn.close()
    return []


def get_natures_by_usage(
    pokemon_name_ja: str,
    season: str | None = None,
) -> list[str]:
    season_token = _season_or_active(season)
    conn = get_connection()
    for name in _usage_name_variants(pokemon_name_ja):
        rows = conn.execute("""
            SELECT option_name_ja FROM usage_option
            WHERE season=? AND pokemon_name_ja=? AND category='nature'
            ORDER BY usage_rank ASC
        """, (season_token, name)).fetchall()
        if rows:
            conn.close()
            return [r["option_name_ja"] for r in rows]
    conn.close()
    return []


def get_effort_spreads_by_usage(
    pokemon_name_ja: str,
    season: str | None = None,
) -> list[tuple[int, int, int, int, int, int, float]]:
    season_token = _season_or_active(season)
    conn = get_connection()
    for name in _usage_name_variants(pokemon_name_ja):
        rows = conn.execute("""
            SELECT hp_pt, attack_pt, defense_pt, sp_attack_pt, sp_defense_pt, speed_pt, usage_percent
            FROM usage_effort
            WHERE season=? AND pokemon_name_ja=?
            ORDER BY usage_rank ASC
        """, (season_token, name)).fetchall()
        if rows:
            conn.close()
            return [
                (
                    int(r["hp_pt"]),
                    int(r["attack_pt"]),
                    int(r["defense_pt"]),
                    int(r["sp_attack_pt"]),
                    int(r["sp_defense_pt"]),
                    int(r["speed_pt"]),
                    float(r["usage_percent"]),
                )
                for r in rows
            ]
    conn.close()
    return []


def get_local_data_status(season: str | None = None) -> dict[str, int]:
    season_token = _season_or_active(season)
    conn = get_connection()
    status = {
        "species_count": conn.execute(
            "SELECT COUNT(*) AS count FROM species_cache"
        ).fetchone()["count"],
        "move_count": conn.execute(
            "SELECT COUNT(*) AS count FROM move_cache WHERE name_ja IS NOT NULL AND name_ja != ''"
        ).fetchone()["count"],
        "usage_pokemon_count": conn.execute(
            "SELECT COUNT(*) AS count FROM pokemon_usage WHERE season=?",
            (season_token,),
        ).fetchone()["count"],
        "usage_season_count": conn.execute(
            "SELECT COUNT(DISTINCT season) AS count FROM pokemon_usage"
        ).fetchone()["count"],
        "learnset_species_count": conn.execute(
            "SELECT COUNT(DISTINCT species_id) AS count FROM species_move_cache"
        ).fetchone()["count"],
    }
    conn.close()
    return status


# ── Usage Data Export/Import ────────────────────────────────────────────

def _get_usage_json_path(season: str | None = None) -> Path:
    """Get path to usage JSON file in project root or executable directory."""
    import sys
    season_token = _season_or_active(season)
    if getattr(sys, "frozen", False):
        # ビルド版: 実行ファイルと同じ場所
        json_dir = Path(sys.executable).parent
    else:
        # 開発環境: プロジェクトルート
        import os
        json_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return json_dir / f"usage_data_{season_token}.json"


def export_usage_to_json(season: str | None = None) -> bool:
    """Export usage data to JSON file in project root."""
    import json
    season_token = _season_or_active(season)
    conn = get_connection()
    
    try:
        data = {
            "season": season_token,
            "pokemon": [
                {"name_ja": r["pokemon_name_ja"], "rank": r["usage_rank"]}
                for r in conn.execute(
                    "SELECT pokemon_name_ja, usage_rank FROM pokemon_usage WHERE season=? ORDER BY usage_rank",
                    (season_token,)
                ).fetchall()
            ],
            "moves": [
                {"pokemon_name_ja": r["pokemon_name_ja"], "name_ja": r["option_name_ja"], "rank": r["usage_rank"]}
                for r in conn.execute(
                    "SELECT pokemon_name_ja, option_name_ja, usage_rank FROM usage_option WHERE season=? AND category='move' ORDER BY usage_rank",
                    (season_token,)
                ).fetchall()
            ],
            "abilities": [
                {"pokemon_name_ja": r["pokemon_name_ja"], "name_ja": r["option_name_ja"], "rank": r["usage_rank"]}
                for r in conn.execute(
                    "SELECT pokemon_name_ja, option_name_ja, usage_rank FROM usage_option WHERE season=? AND category='ability' ORDER BY usage_rank",
                    (season_token,)
                ).fetchall()
            ],
            "items": [
                {"pokemon_name_ja": r["pokemon_name_ja"], "name_ja": r["option_name_ja"], "rank": r["usage_rank"]}
                for r in conn.execute(
                    "SELECT pokemon_name_ja, option_name_ja, usage_rank FROM usage_option WHERE season=? AND category='item' ORDER BY usage_rank",
                    (season_token,)
                ).fetchall()
            ],
            "natures": [
                {"pokemon_name_ja": r["pokemon_name_ja"], "name_ja": r["option_name_ja"], "rank": r["usage_rank"]}
                for r in conn.execute(
                    "SELECT pokemon_name_ja, option_name_ja, usage_rank FROM usage_option WHERE season=? AND category='nature' ORDER BY usage_rank",
                    (season_token,)
                ).fetchall()
            ],
            "efforts": [
                {
                    "pokemon_name_ja": r["pokemon_name_ja"],
                    "rank": r["usage_rank"],
                    "hp_pt": r["hp_pt"],
                    "attack_pt": r["attack_pt"],
                    "defense_pt": r["defense_pt"],
                    "sp_attack_pt": r["sp_attack_pt"],
                    "sp_defense_pt": r["sp_defense_pt"],
                    "speed_pt": r["speed_pt"],
                    "usage_percent": r["usage_percent"],
                }
                for r in conn.execute(
                    "SELECT pokemon_name_ja, usage_rank, hp_pt, attack_pt, defense_pt, sp_attack_pt, sp_defense_pt, speed_pt, usage_percent FROM usage_effort WHERE season=? ORDER BY usage_rank",
                    (season_token,)
                ).fetchall()
            ],
        }
        conn.close()
        
        json_path = _get_usage_json_path(season)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        import logging
        logging.warning("export_usage_snapshot failed: %s", e)
        try:
            conn.close()
        except Exception:
            pass
        return False


def import_usage_from_json(season: str | None = None) -> bool:
    """Import usage data from JSON file in project root if exists."""
    import json
    json_path = _get_usage_json_path(season)
    
    if not json_path.exists():
        return False
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        season_token = data.get("season", _season_or_active(season))
        
        pokemon_rows = [(r["name_ja"], r["rank"]) for r in data.get("pokemon", [])]
        move_rows = [(r["pokemon_name_ja"], r["name_ja"], r["rank"]) for r in data.get("moves", [])]
        ability_rows = [(r["pokemon_name_ja"], r["name_ja"], r["rank"]) for r in data.get("abilities", [])]
        item_rows = [(r["pokemon_name_ja"], r["name_ja"], r["rank"]) for r in data.get("items", [])]
        nature_rows = [(r["pokemon_name_ja"], r["name_ja"], r["rank"]) for r in data.get("natures", [])]
        effort_rows = [
            (
                r["pokemon_name_ja"],
                r["rank"],
                r["hp_pt"],
                r["attack_pt"],
                r["defense_pt"],
                r["sp_attack_pt"],
                r["sp_defense_pt"],
                r["speed_pt"],
                r["usage_percent"],
            )
            for r in data.get("efforts", [])
        ]
        
        save_usage_snapshot(
            pokemon_rows,
            move_rows,
            ability_rows,
            item_rows,
            nature_rows,
            effort_rows,
            season=season_token,
        )
        return True
    except Exception as e:
        import logging
        logging.warning("import_usage_from_json failed: %s", e)
        return False


def has_usage_json_file(season: str | None = None) -> bool:
    """Check if usage JSON file exists in project root."""
    return _get_usage_json_path(season).exists()
