---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Coding Rules

> Comprehensive Python coding guidelines for AI-assisted development

## AI Model Usage

- When using **Sonnet 4.6 Effort:Medium Thinking:ON**, you must first request permission.
If permission is granted, use **Plan mode** to perform complex thinking, make architectural decisions, and solve problems.
Afterward, carry out the actual implementation using **Haiku 4.5**.
If permission is not granted, perform all tasks using **Haiku 4.5**.
You must not use any models other than these two.

## Bug fix rules
-When fixing bugs or addressing requests, please check to see if there are any similar cases.
-Once you have checked, you must implement a comprehensive fix. It is pointless to resolve only the specific case that was shared.

## Coding Style

### Standards
- Follow **PEP 8** conventions
- Use **type annotations** on all function signatures

### Immutability
Prefer immutable data structures:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class User:
    name: str
    email: str

from typing import NamedTuple

class Point(NamedTuple):
    x: float
    y: float
```

### Formatting
- **black** for code formatting
- **isort** for import sorting
- **ruff** for linting

## Patterns

### Protocol (Duck Typing)
```python
from typing import Protocol

class Repository(Protocol):
    def find_by_id(self, id: str) -> dict | None: ...
    def save(self, entity: dict) -> dict: ...
```

### Dataclasses as DTOs
```python
from dataclasses import dataclass

@dataclass
class CreateUserRequest:
    name: str
    email: str
    age: int | None = None
```

### Context Managers & Generators
- Use context managers (`with` statement) for resource management
- Use generators for lazy evaluation and memory-efficient iteration

## Security

### Secret Management
```python
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ["OPENAI_API_KEY"]  # Raises KeyError if missing
```

### Security Scanning
- Use **bandit** for static security analysis:
  ```bash
  bandit -r src/
  ```
### Framework
Use **pytest** as the testing framework.

### Coverage
```bash
pytest --cov=src --cov-report=term-missing
```
### Test Organization
Use `pytest.mark` for test categorization:

```python
import pytest

@pytest.mark.unit
def test_calculate_total():
    ...

@pytest.mark.integration
def test_database_connection():
    ...
```
## Hooks

### PostToolUse Hooks
Configure in `~/.claude/settings.json`:
- **black/ruff**: Auto-format `.py` files after edit
- **mypy/pyright**: Run type checking after editing `.py` files

### Warning
- Issue a warning regarding `print()` statements in edited files (use the `logging` module instead)
- **Conciseness**: Keep code explanations to a minimum and clearly state only the changes in Japanese. Avoid consuming tokens with redundant explanations.

### Rule
- Do not read, use, or import files whose names begin with **deprecated_** unless explicitly instructed to do so by the user
- These files are for backup purposes and serve as a repository for deprecated code
- When writing new code, do not reference these files; refer only to existing, valid code

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
