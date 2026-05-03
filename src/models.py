from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class MoveInfo:
    """Represents a move's static battle metadata."""
    name_ja: str
    name_en: str = ""
    type_name: str = "normal"
    category: str = "physical"  # physical / special / status
    power: int = 0
    accuracy: int = 100
    pp: int = 10
    priority: int = 0
    makes_contact: bool = False


@dataclass
class SpeciesInfo:
    """Represents a Pokemon species entry cached from external sources."""
    species_id: int
    name_ja: str
    name_en: str
    type1: str
    type2: str  # "" if none
    base_hp: int
    base_attack: int
    base_defense: int
    base_sp_attack: int
    base_sp_defense: int
    base_speed: int
    weight_kg: float = 0.0


@dataclass
class PokemonInstance:
    """Represents an individual Pokemon with battle and build state."""
    species_id: int = 0
    name_ja: str = ""
    usage_name: str = ""  # DB()。/FC,
    name_en: str = ""
    types: list[str] = field(default_factory=list)
    weight_kg: float = 0.0
    level: int = 50
    nature: str = "がんばりや"
    ability: str = ""
    item: str = ""
    # Actual stat values (0 = not yet known)
    hp: int = 0
    attack: int = 0
    defense: int = 0
    sp_attack: int = 0
    sp_defense: int = 0
    speed: int = 0
    # EVs (Pokemon Champions uses points × 8 = traditional EVs)
    ev_hp: int = 0
    ev_attack: int = 0
    ev_defense: int = 0
    ev_sp_attack: int = 0
    ev_sp_defense: int = 0
    ev_speed: int = 0
    # IVs (assumed 31 for opponent)
    iv_hp: int = 31
    iv_attack: int = 31
    iv_defense: int = 31
    iv_sp_attack: int = 31
    iv_sp_defense: int = 31
    iv_speed: int = 31
    # Moves (Japanese names)
    moves: list[str] = field(default_factory=list)
    # Current HP state
    current_hp: int = 0        # actual HP (user's Pokemon)
    current_hp_percent: float = 100.0  # % (opponent)
    max_hp: int = 0
    # Status condition
    status: str = ""  # burn / poison / paralysis / sleep / freeze / ""
    # Terastal
    terastal_type: str = ""  # English type name, "" = not terastalized
    # DB registration id
    db_id: int | None = None

    @property
    def is_registered(self) -> bool:
        """Return True when this instance is persisted in registered_pokemon."""
        return self.db_id is not None


@dataclass
class DamageResult:
    """Represents one move's damage range and derived KO flags."""
    move_name: str
    move_type: str
    category: str
    power: int
    min_percent: float
    max_percent: float
    type_mult: float
    is_ohko: bool = False
    is_2hko: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class BattleState:
    """Represents the current battle context shared across UI modules."""
    my_pokemon: PokemonInstance | None = None
    opponent_pokemon: PokemonInstance | None = None
    my_party: list[PokemonInstance | None] = field(default_factory=list)
    opponent_party: list[PokemonInstance | None] = field(default_factory=list)
    last_opponent_move: str = ""
    weather: str = "none"        # sun / rain / sand / hail / none
    terrain: str = "none"        # electric / grassy / misty / psychic / none
    has_reflect: bool = False
    has_light_screen: bool = False
    helping_hand: bool = False
    charged: bool = False
