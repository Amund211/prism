---
applyTo: "**"
---

# Critical Development Notes and Workarounds for Prism

## ALWAYS DO FIRST (Critical Setup for Coding Agents)

**No setup required** - the prism package and all dependencies are already installed in your environment.

**Verify setup works** (optional):
```bash
python -c "from prism import VERSION_STRING; print(f'Setup OK: {VERSION_STRING}')"
```

**IMPORTANT**: Coding agents must NOT use virtual environments. Dependencies and package are pre-installed in your global environment.

### Requirements Files (Platform-Specific)
- **Coding Agents**: Use Linux requirements only
- **Linux**: `requirements/linux.txt` + `requirements/linux-dev.txt`

### Import Path Issues
Package and dependencies are pre-installed. If imports still fail (rare):
```bash
# Only if package is missing (should not happen)
pip install --no-deps -e .

# Or use PYTHONPATH for testing:
PYTHONPATH=src python3 script.py
```

## Testing Workarounds

### Coverage Must Be 100%
```bash
# Check current coverage
coverage report

# Files excluded from coverage (in setup.cfg):
# - src/prism/stats.py (external data)
# - src/prism/overlay/platform/windows.py (platform-specific)
# - src/prism/discordrp/__init__.py (optional feature)
```

### MyPy Strict Mode (Common Failures)
```bash
# Clear cache if mypy behaves oddly
rm -rf .mypy_cache/

# Common fixes for mypy errors:
# - Add type hints to ALL functions
# - Replace 'Any' with specific types
# - Add return type annotations
# - Import stub packages for third-party libs
```

### Test Data Location
- Player data: `tests/data/*.json`
- SSL tests: `tests/system_certs/`
- Mock utilities: `tests/mock_utils.py`

## Build System Workarounds

### PyInstaller Issues
```bash
# MUST generate versioned icon first
python add_version_to_icon.py

# Creates: pyinstaller/who_with_version.ico

# If build fails, check hook files exist:
ls pyinstaller/hook-*.py
```

### Version Management
- Version defined in: `src/prism/__init__.py`
- Format: `VERSION_STRING = "v1.9.1-dev"`
- Used by: icon generation, builds, application

### Dependency Management
```bash
# Update pinned requirements (when adding dependencies)
uv pip compile setup.cfg --output-file requirements/linux.txt --generate-hashes
uv pip compile requirements/dev.in --output-file requirements/linux-dev.txt --generate-hashes

# IMPORTANT: Do this for ALL platforms when dependencies change
```

## Code Quality Workarounds

### Manual Quality Checks
```bash
# Run quality checks manually (coding agents don't use pre-commit hooks):
isort . && black . && flake8 . && mypy --strict .
```

### Tool Configuration Conflicts
- **NEVER** override tool configs in pyproject.toml or setup.cfg
- Tools are configured to work together
- Black + isort + flake8 settings are coordinated

## Application-Specific Notes

### GUI Dependencies
- **tkinter**: Built into Python (usually), but may need system packages on Linux
- **Platform-specific**: Windows needs pywin32, Linux needs X11 libs

### SSL Certificate Handling
- **Dual mode**: Can use system certs OR included certs
- **Setting**: `use_included_certs` in settings
- **Testing**: `--test-ssl` flag validates SSL functionality

### Log File Requirements
- **REQUIRED**: Application needs a log file path to function
- **For testing**: Create dummy file: `touch latest.log`
- **Command**: `python prism_overlay.py --logfile=latest.log`

## Directory Structure Critical Points

### Source Layout
```
src/prism/               # ONLY source code here
├── __init__.py         # Version info (CRITICAL)
├── overlay/            # Main application
│   ├── __main__.py    # Entry point
│   └── ...
└── ...
```

### Configuration Files (DO NOT MODIFY)
- `setup.cfg`: Package config, tool settings
- `pyproject.toml`: Black, isort, mypy config  
- `.pre-commit-config.yaml`: Hook definitions

## Network and External Dependencies

### API Dependencies
- **Hypixel API**: For player stats
- **Mojang API**: For username/UUID resolution
- **Antisniper API**: Optional winstreak data

### SSL/TLS Handling
- **truststore**: System certificate store integration
- **requests**: HTTP client with SSL verification
- **System vs Included**: Configurable certificate source

## Performance Considerations

### Build Times
- **PyInstaller**: 3-8 minutes depending on platform
- **Tests**: ~30 seconds for full suite
- **Type checking**: ~10-15 seconds (first run slower)

### Memory Usage
- **Development**: Minimal (normal Python app)
- **Built executable**: Single-file, ~50-100MB depending on platform

## Emergency Fixes

### Clean State
```bash
# Nuclear option - clean everything (package should not need reinstalling)
rm -rf .mypy_cache/ __pycache__/ build/ dist/ *.egg-info/
find . -name "*.pyc" -delete
# Package should already be installed; only reinstall if truly necessary:
# pip uninstall prism-amund211 -y
# pip install --no-deps -e .
```

### Import Errors
```bash
# Package should already be installed; if "No module named 'prism'" errors persist:
# pip install --no-deps -e .

# Alternative approach:
PYTHONPATH=src python3 your_script.py
```

### CI/CD Debug
- **GitHub Actions logs**: Check exact commands used in workflows
- **Local reproduction**: Use exact Python 3.13 and dependencies
- **Platform differences**: Requirements files differ significantly

## Files to NEVER Modify
- `requirements/*.txt` (auto-generated by uv)
- `.github/workflows/*.yml` (CI/CD definitions)
- `src/prism_amund211.egg-info/` (auto-generated)

## Files Safe to Modify
- `src/prism/**/*.py` (source code)
- `tests/**/*.py` (test code)
- `README.md` (documentation)
- `setup.cfg` (dependencies in [options] section only)

## When Network Access Fails
- **Requirements**: Dependencies may fail to install
- **Workaround**: Use cached wheels or offline installation
- **Testing**: Some tests require internet (SSL tests)
- **Development**: Basic functionality works offline