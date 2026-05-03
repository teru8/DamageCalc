import re
import sqlite3
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
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


_write_generation: int = 0


def normalize_species_name_ja(name_ja: str) -> str:
    """Normalize Japanese species names for stable cross-source matching."""
    text = str(name_ja or "").strip()
    # Unify full-width/half-width parenthesis variants.
    text = text.replace("（", "(").replace("）", ")")
    return text


def get_write_generation() -> int:
    """Return a monotonically increasing counter that increments on every DB write.

    Callers can cache this value and compare on next use to detect stale data.
    """
    return _write_generation


def _bump_generation() -> None:
    global _write_generation
    _write_generation += 1


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


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
    with connection() as conn:
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
        c.execute(
            """
            UPDATE species_cache
            SET name_ja = REPLACE(REPLACE(name_ja, '（', '('), '）', ')')
            WHERE name_ja LIKE '%（%' OR name_ja LIKE '%）%'
            """
        )
        pokemon_cols = [row["name"] for row in c.execute("PRAGMA table_info(registered_pokemon)").fetchall()]
        if "usage_name" not in pokemon_cols:
            c.execute("ALTER TABLE registered_pokemon ADD COLUMN usage_name TEXT DEFAULT ''")
        if "terastal_type" not in pokemon_cols:
            c.execute("ALTER TABLE registered_pokemon ADD COLUMN terastal_type TEXT DEFAULT 'ノーマル'")
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

    # Import usage data from JSON if exists in project root
    import_usage_from_json()


# ── Species ──────────────────────────────────────────────────────────

def upsert_species(s: SpeciesInfo) -> None:
    _bump_generation()
    normalized_name = normalize_species_name_ja(s.name_ja)
    with connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO species_cache
            (species_id, name_ja, name_en, type1, type2,
             base_hp, base_attack, base_defense, base_sp_attack, base_sp_defense, base_speed, weight_kg)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (s.species_id, normalized_name, s.name_en, s.type1, s.type2,
              s.base_hp, s.base_attack, s.base_defense,
              s.base_sp_attack, s.base_sp_defense, s.base_speed, float(s.weight_kg or 0)))
        conn.commit()


def get_species_by_name_ja(name_ja: str) -> SpeciesInfo | None:
    normalized_name = normalize_species_name_ja(name_ja)
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM species_cache WHERE name_ja=? OR name_ja=?",
            (name_ja, normalized_name),
        ).fetchone()
        if row is not None:
            return SpeciesInfo(**dict(row))
        return None


def get_species_by_id(species_id: int) -> SpeciesInfo | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM species_cache WHERE species_id=?", (species_id,)
        ).fetchone()
        if row is None:
            return None
        return SpeciesInfo(**dict(row))


def has_species_learnset(species_id: int) -> bool:
    with connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM species_move_cache WHERE species_id=? LIMIT 1",
            (species_id,),
        ).fetchone()
        return row is not None


def replace_species_learnset(species_id: int, move_ids: list[int]) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM species_move_cache WHERE species_id=?", (species_id,))
        if move_ids:
            rows = [(species_id, move_id) for move_id in sorted(set(move_ids))]
            conn.executemany(
                "INSERT OR REPLACE INTO species_move_cache VALUES (?,?)",
                rows,
            )
        conn.commit()


# ── Moves ─────────────────────────────────────────────────────────────

def upsert_move(m: MoveInfo, move_id: int) -> None:
    _bump_generation()
    with connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO move_cache
            (move_id, name_ja, name_en, type_name, category, power, accuracy, pp, priority)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (move_id, m.name_ja, m.name_en, m.type_name, m.category,
              m.power, m.accuracy, m.pp, m.priority))
        conn.commit()


def get_move_by_name_ja(name_ja: str) -> MoveInfo | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM move_cache WHERE name_ja=?", (name_ja,)
        ).fetchone()
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

    moves = (pokemon.moves + ["", "", "", ""])[:4]
    ev_hp_db = _to_db_ev(pokemon.ev_hp)
    ev_attack_db = _to_db_ev(pokemon.ev_attack)
    ev_defense_db = _to_db_ev(pokemon.ev_defense)
    ev_sp_attack_db = _to_db_ev(pokemon.ev_sp_attack)
    ev_sp_defense_db = _to_db_ev(pokemon.ev_sp_defense)
    ev_speed_db = _to_db_ev(pokemon.ev_speed)
    with connection() as conn:
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
    return new_id


def load_all_pokemon() -> list[PokemonInstance]:
    import json
    def _from_db_ev(ev_value: int) -> int:
        # Restore in-app representation from persisted (8x points - 4).
        value = int(ev_value or 0)
        if value <= 0:
            return 0
        return value + 4

    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM registered_pokemon ORDER BY updated_at DESC"
        ).fetchall()
    result = []
    for row in rows:
        try:
            types = json.loads(row["types_json"] or "[]")
        except json.JSONDecodeError:
            types = []
        pokemon = PokemonInstance(
            species_id=row["species_id"],
            name_ja=row["name_ja"],
            usage_name=row["usage_name"] or "",
            name_en=row["name_en"],
            types=types,
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
            moves=[move for move in [row["move1"], row["move2"],
                                     row["move3"], row["move4"]] if move],
            db_id=row["id"],
        )
        result.append(pokemon)
    return result


def delete_pokemon(db_id: int) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM registered_pokemon WHERE id=?", (db_id,))
        conn.commit()


# ── Usage ranking ─────────────────────────────────────────────────────

def save_usage_ranking(
    data: list[tuple[str, str, int]],
    season: str | None = None,
) -> None:
    """data: list of (pokemon_name_ja, move_name_ja, rank)"""
    season_token = _season_or_active(season)
    _bump_generation()
    with connection() as conn:
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
    _bump_generation()
    with connection() as conn:
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


def get_all_species_names_ja() -> list[str]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT name_ja FROM species_cache ORDER BY name_ja"
        ).fetchall()
    return [r["name_ja"] for r in rows]


def get_available_usage_seasons() -> list[str]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT season FROM pokemon_usage WHERE season IS NOT NULL AND season != '' ORDER BY season DESC"
        ).fetchall()
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
    with connection() as conn:
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
    with connection() as conn:
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
    with connection() as conn:
        rows = conn.execute(
            "SELECT species_id, name_ja, name_en FROM species_cache ORDER BY species_id"
        ).fetchall()
    return [(r["species_id"], r["name_ja"], r["name_en"]) for r in rows]


def get_all_species() -> list[SpeciesInfo]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM species_cache ORDER BY species_id ASC"
        ).fetchall()
    return [SpeciesInfo(**dict(row)) for row in rows]


def get_species_usage_rank_map(season: str | None = None) -> dict[str, int]:
    season_token = _season_or_active(season)
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT pokemon_name_ja, usage_rank
            FROM pokemon_usage
            WHERE season=?
            """,
            (season_token,),
        ).fetchall()
    return {
        row["pokemon_name_ja"]: row["usage_rank"]
        for row in rows
        if row["pokemon_name_ja"]
    }


def get_move_by_id(move_id: int) -> MoveInfo | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM move_cache WHERE move_id=?", (move_id,)
        ).fetchone()
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
    with connection() as conn:
        rows = conn.execute(
            "SELECT name_ja FROM move_cache WHERE name_ja IS NOT NULL ORDER BY name_ja"
        ).fetchall()
    return [r["name_ja"] for r in rows]


def get_all_moves() -> list[MoveInfo]:
    with connection() as conn:
        rows = conn.execute("""
            SELECT * FROM move_cache
            WHERE name_ja IS NOT NULL AND name_ja != ''
            ORDER BY name_ja ASC
        """).fetchall()
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
    with connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT s.name_ja
            FROM move_cache m
            JOIN species_move_cache sm ON sm.move_id = m.move_id
            JOIN species_cache s ON s.species_id = sm.species_id
            WHERE m.name_ja=?
            ORDER BY s.name_ja ASC
        """, (move_name_ja,)).fetchall()
    return [row["name_ja"] for row in rows]


def get_species_names_by_ability_usage(
    ability_name_ja: str,
    season: str | None = None,
) -> list[str]:
    season_token = _season_or_active(season)
    with connection() as conn:
        rows = conn.execute("""
            SELECT pokemon_name_ja
            FROM usage_option
            WHERE season=? AND category='ability' AND option_name_ja=?
            ORDER BY usage_rank ASC
        """, (season_token, ability_name_ja)).fetchall()
    return [row["pokemon_name_ja"] for row in rows if row["pokemon_name_ja"]]


def get_all_usage_ability_names(season: str | None = None) -> list[str]:
    season_token = _season_or_active(season)
    with connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT option_name_ja
            FROM usage_option
            WHERE season=? AND category='ability' AND option_name_ja != ''
            ORDER BY option_name_ja ASC
        """, (season_token,)).fetchall()
    return [row["option_name_ja"] for row in rows if row["option_name_ja"]]


def get_moves_for_species(species_id: int) -> list[MoveInfo]:
    with connection() as conn:
        rows = conn.execute("""
            SELECT m.*
            FROM species_move_cache sm
            JOIN move_cache m ON m.move_id = sm.move_id
            WHERE sm.species_id=? AND m.name_ja IS NOT NULL AND m.name_ja != ''
            ORDER BY m.name_ja ASC
        """, (species_id,)).fetchall()
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
    with connection() as conn:
        for name in _usage_name_variants(pokemon_name_ja):
            rows = conn.execute("""
                SELECT option_name_ja FROM usage_option
                WHERE season=? AND pokemon_name_ja=? AND category='move'
                ORDER BY usage_rank ASC
            """, (season_token, name)).fetchall()
            if rows:
                return [r["option_name_ja"] for r in rows]

        for name in _usage_name_variants(pokemon_name_ja):
            rows = conn.execute("""
                SELECT move_name_ja FROM usage_ranking
                WHERE season=? AND pokemon_name_ja=?
                ORDER BY usage_rank ASC
            """, (season_token, name)).fetchall()
            if rows:
                return [r["move_name_ja"] for r in rows]

    return []


def get_abilities_by_usage(
    pokemon_name_ja: str,
    season: str | None = None,
) -> list[str]:
    season_token = _season_or_active(season)
    with connection() as conn:
        for name in _usage_name_variants(pokemon_name_ja):
            rows = conn.execute("""
                SELECT option_name_ja FROM usage_option
                WHERE season=? AND pokemon_name_ja=? AND category='ability'
                ORDER BY usage_rank ASC
            """, (season_token, name)).fetchall()
            if rows:
                return [r["option_name_ja"] for r in rows]
    return []


def get_items_by_usage(
    pokemon_name_ja: str,
    season: str | None = None,
) -> list[str]:
    season_token = _season_or_active(season)
    with connection() as conn:
        for name in _usage_name_variants(pokemon_name_ja):
            rows = conn.execute("""
                SELECT option_name_ja FROM usage_option
                WHERE season=? AND pokemon_name_ja=? AND category='item'
                ORDER BY usage_rank ASC
            """, (season_token, name)).fetchall()
            if rows:
                return [r["option_name_ja"] for r in rows]
    return []


def get_natures_by_usage(
    pokemon_name_ja: str,
    season: str | None = None,
) -> list[str]:
    season_token = _season_or_active(season)
    with connection() as conn:
        for name in _usage_name_variants(pokemon_name_ja):
            rows = conn.execute("""
                SELECT option_name_ja FROM usage_option
                WHERE season=? AND pokemon_name_ja=? AND category='nature'
                ORDER BY usage_rank ASC
            """, (season_token, name)).fetchall()
            if rows:
                return [r["option_name_ja"] for r in rows]
    return []


def get_effort_spreads_by_usage(
    pokemon_name_ja: str,
    season: str | None = None,
) -> list[tuple[int, int, int, int, int, int, float]]:
    season_token = _season_or_active(season)
    with connection() as conn:
        for name in _usage_name_variants(pokemon_name_ja):
            rows = conn.execute("""
                SELECT hp_pt, attack_pt, defense_pt, sp_attack_pt, sp_defense_pt, speed_pt, usage_percent
                FROM usage_effort
                WHERE season=? AND pokemon_name_ja=?
                ORDER BY usage_rank ASC
            """, (season_token, name)).fetchall()
            if rows:
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
    return []


def get_local_data_status(season: str | None = None) -> dict[str, int]:
    season_token = _season_or_active(season)
    with connection() as conn:
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
    return status


# ── Usage Data Export/Import ────────────────────────────────────────────

def _get_usage_json_path(season: str | None = None) -> Path:
    """Get path to usage JSON file in project root or executable directory."""
    import sys
    season_token = _season_or_active(season)
    if getattr(sys, "frozen", False):
        json_dir = Path(sys.executable).parent
    else:
        import os
        json_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return json_dir / f"usage_data_{season_token}.json"


def export_usage_to_json(season: str | None = None) -> bool:
    """Export usage data to JSON file in project root."""
    import json
    import logging
    season_token = _season_or_active(season)
    try:
        with connection() as conn:
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

        json_path = _get_usage_json_path(season)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except (OSError, sqlite3.DatabaseError, TypeError, ValueError, json.JSONDecodeError) as e:
        logging.warning("export_usage_snapshot failed: %s", e)
        return False


def import_usage_from_json(season: str | None = None) -> bool:
    """Import usage data from JSON file in project root if exists."""
    import json
    import logging
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
    except (OSError, sqlite3.DatabaseError, TypeError, ValueError, json.JSONDecodeError) as e:
        logging.warning("import_usage_from_json failed: %s", e)
        return False


def has_usage_json_file(season: str | None = None) -> bool:
    """Check if usage JSON file exists in project root."""
    return _get_usage_json_path(season).exists()


def check_usage_data_integrity(season: str | None = None) -> dict[str, object]:
    """Check consistency between usage tables, species cache, and usage JSON file."""
    season_token = _season_or_active(season)
    issues: list[str] = []
    summary: dict[str, int] = {}

    with connection() as conn:
        species_names = {
            normalize_species_name_ja(str(row["name_ja"]).strip())
            for row in conn.execute(
                "SELECT name_ja FROM species_cache WHERE name_ja IS NOT NULL AND name_ja != ''"
            ).fetchall()
        }
        usage_names = {
            normalize_species_name_ja(str(row["pokemon_name_ja"]).strip())
            for row in conn.execute(
                "SELECT pokemon_name_ja FROM pokemon_usage WHERE season=?",
                (season_token,),
            ).fetchall()
            if str(row["pokemon_name_ja"]).strip()
        }
        option_names = {
            normalize_species_name_ja(str(row["pokemon_name_ja"]).strip())
            for row in conn.execute(
                "SELECT DISTINCT pokemon_name_ja FROM usage_option WHERE season=?",
                (season_token,),
            ).fetchall()
            if str(row["pokemon_name_ja"]).strip()
        }
        effort_names = {
            normalize_species_name_ja(str(row["pokemon_name_ja"]).strip())
            for row in conn.execute(
                "SELECT DISTINCT pokemon_name_ja FROM usage_effort WHERE season=?",
                (season_token,),
            ).fetchall()
            if str(row["pokemon_name_ja"]).strip()
        }

    missing_in_species_usage = sorted(usage_names - species_names)
    missing_in_usage_option = sorted(option_names - usage_names)
    missing_in_usage_effort = sorted(effort_names - usage_names)

    if missing_in_species_usage:
        issues.append(
            "species_cache に存在しない pokemon_usage 名が {} 件".format(
                len(missing_in_species_usage)
            )
        )
    if missing_in_usage_option:
        issues.append(
            "pokemon_usage に存在しない usage_option 名が {} 件".format(
                len(missing_in_usage_option)
            )
        )
    if missing_in_usage_effort:
        issues.append(
            "pokemon_usage に存在しない usage_effort 名が {} 件".format(
                len(missing_in_usage_effort)
            )
        )

    json_path = _get_usage_json_path(season_token)
    json_missing_names: list[str] = []
    json_parse_error = ""
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            json_pokemon = payload.get("pokemon", [])
            json_names = {
                str(row.get("name_ja", "")).strip()
                for row in json_pokemon
                if isinstance(row, dict) and str(row.get("name_ja", "")).strip()
            }
            json_missing_names = sorted(usage_names - json_names)
            if json_missing_names:
                issues.append(
                    "JSON usage_data と DB(pokemon_usage) の差分が {} 件".format(
                        len(json_missing_names)
                    )
                )
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            json_parse_error = str(exc)
            issues.append("usage_data JSON の読み込みに失敗: {}".format(exc))

    summary["species_count"] = len(species_names)
    summary["usage_count"] = len(usage_names)
    summary["option_count"] = len(option_names)
    summary["effort_count"] = len(effort_names)
    summary["missing_in_species_count"] = len(missing_in_species_usage)
    summary["missing_in_usage_option_count"] = len(missing_in_usage_option)
    summary["missing_in_usage_effort_count"] = len(missing_in_usage_effort)
    summary["json_missing_count"] = len(json_missing_names)

    if json_parse_error:
        logging.warning("usage_data integrity check json parse error: %s", json_parse_error)

    return {
        "season": season_token,
        "ok": len(issues) == 0,
        "issues": issues,
        "summary": summary,
        "details": {
            "missing_in_species": missing_in_species_usage[:50],
            "missing_in_usage_option": missing_in_usage_option[:50],
            "missing_in_usage_effort": missing_in_usage_effort[:50],
            "json_missing_in_file": json_missing_names[:50],
            "json_path": str(json_path),
            "json_exists": json_path.exists(),
        },
    }
