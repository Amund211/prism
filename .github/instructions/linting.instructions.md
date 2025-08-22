---
applyTo:
  - "**/*.py"
  - ".pre-commit-config.yaml"
  - "pyproject.toml"
  - "setup.cfg"
---

# Code Quality and Linting Instructions for Prism

## Code Quality Standards
Prism enforces strict code quality standards through automated tooling. ALL code must pass these checks before committing.

## Required Tools and Configurations

### Code Formatters (REQUIRED - Auto-fixes)
```bash
# Black - code formatter (REQUIRED)
black .

# isort - import sorter (REQUIRED)  
isort .
```

### Linters (REQUIRED - Must pass)
```bash
# Flake8 - style and error linting (REQUIRED)
flake8 --count --statistics .

# MyPy - type checking (REQUIRED - strict mode)
mypy --strict .
```

### All Quality Checks in Order
```bash
# ALWAYS run in this exact order before committing:
isort .
black .
flake8 .
mypy --strict .
```

## Pre-commit Hooks (STRONGLY RECOMMENDED)
```bash
# Install pre-commit (if not already installed)
pip install pre-commit

# Install hooks to run automatically on commit
pre-commit install

# Run all hooks manually
pre-commit run --all-files

# Run specific hook
pre-commit run black
pre-commit run mypy
```

## Tool Configurations

### Black Configuration (pyproject.toml)
```toml
[tool.black]
exclude = '''
/(
    \.git
  | \.mypy_cache
  | __pycache__
  | build
  | dist
  | venv
)/
'''
```

### isort Configuration (pyproject.toml)
```toml
[tool.isort]
profile = "black"
known_first_party = "prism"
skip = ".git,.mypy_cache,__pycache__,build,dist,venv"
```

### Flake8 Configuration (setup.cfg)
```ini
[flake8]
max-line-length = 88
extend-ignore = E203
exclude = .git,.mypy_cache,__pycache__,build,dist,venv
```

### MyPy Configuration (pyproject.toml)
```toml
[tool.mypy]
exclude = [
  '^\.git/$',
  '^\.mypy_cache/$', 
  '^__pycache__/$',
  '^build/$',
  '^dist/$',
  '^venv/$',
]
```

## Code Quality Requirements

### 1. Black Formatting
- **Line length**: 88 characters (Black default)
- **String quotes**: Double quotes preferred
- **Must pass**: `black --check .` (no changes needed)

### 2. Import Organization (isort)
- **Profile**: Black compatibility
- **First-party**: `prism` package imports grouped separately
- **Must pass**: `isort --check-only .` (no changes needed)

### 3. Linting (Flake8)
- **Max line length**: 88 characters (matches Black)
- **Ignored**: E203 (whitespace before ':' - conflicts with Black)
- **Must pass**: Zero errors and warnings

### 4. Type Checking (MyPy)
- **Mode**: `--strict` (highest strictness level)
- **Requirements**: 
  - All functions must have type hints
  - All variables must be properly typed
  - No `Any` types without explicit annotation
  - No missing imports
- **Must pass**: Zero type errors

## CI/CD Integration
GitHub Actions (`.github/workflows/linting.yml`) enforces:

```yaml
- name: Check for formatting/linting errors
  run: |
    isort --check-only .
    black --check .
    flake8 --count --statistics .
```

Type checking runs in testing workflow with `mypy --strict .`

## Pre-commit Hook Configuration
File: `.pre-commit-config.yaml`

### External Hooks:
- `check-yaml`: YAML syntax validation
- `end-of-file-fixer`: Ensures files end with newline
- `check-merge-conflict`: Prevents committing merge conflicts
- `check-added-large-files`: Prevents large file commits

### Code Quality Hooks:
- `black`: Auto-formats Python code
- `isort`: Sorts imports
- `flake8`: Linting
- `mypy`: Type checking (local hook using venv)
- `coverage`: Test coverage (run and report)

## Fixing Quality Issues

### Common Black Issues:
```bash
# Fix automatically
black .
```

### Common isort Issues:
```bash
# Fix automatically
isort .
```

### Common Flake8 Issues:
- **Line too long**: Break into multiple lines or use Black
- **Unused imports**: Remove unused imports
- **Undefined names**: Fix import statements or typos

### Common MyPy Issues:
- **Missing type hints**: Add type annotations to functions
- **Any types**: Replace with specific types
- **Import errors**: Install stub packages or add `# type: ignore`

## Code Style Guidelines

### Type Hints (REQUIRED)
```python
# Good
def process_player(player_data: dict[str, Any]) -> PlayerStats:
    return PlayerStats(player_data)

# Bad - missing type hints
def process_player(player_data):
    return PlayerStats(player_data)
```

### Import Organization
```python
# Standard library imports
import logging
import sys
from pathlib import Path

# Third-party imports
import requests
import tkinter as tk

# Local imports
from prism.overlay.controller import Controller
from prism.stats import calculate_stats
```

### Docstrings (Recommended)
```python
def calculate_fkdr(kills: int, deaths: int) -> float:
    """Calculate final kill/death ratio.
    
    Args:
        kills: Number of final kills
        deaths: Number of deaths
        
    Returns:
        FKDR value, or kills if deaths is 0
    """
    return kills / deaths if deaths > 0 else float(kills)
```

## Quality Check Performance
- **Black**: ~1-2 seconds for full codebase
- **isort**: ~1-2 seconds for full codebase  
- **Flake8**: ~3-5 seconds for full codebase
- **MyPy**: ~10-15 seconds for full codebase (first run slower)

## Integration with Development Workflow
1. **Before coding**: Ensure pre-commit hooks installed
2. **During coding**: Run formatters as needed (`black .`, `isort .`)
3. **Before committing**: Either rely on pre-commit hooks OR manually run all checks
4. **CI verification**: All checks run automatically in GitHub Actions

## Troubleshooting
- **MyPy cache issues**: Remove `.mypy_cache/` directory
- **Import path issues**: Ensure `pip install --no-deps -e .` was run
- **Pre-commit not running**: Check `pre-commit install` was executed
- **Tool conflicts**: Tools are configured to work together; don't override settings