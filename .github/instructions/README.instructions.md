# Prism Development Instructions

## High-Level Repository Information

**Project Summary**: Prism is an open-source Python desktop application that provides a real-time stats overlay for Hypixel Bedwars players. It automatically detects players in lobbies and displays their statistics in a customizable overlay window.

**Repository Size**: ~61 Python source files, ~20 test files, medium-sized project (~500KB)
**Primary Language**: Python 3.14+
**Application Type**: Desktop GUI application (tkinter-based overlay)
**Target Platforms**: Windows, macOS, Linux with platform-specific builds
**Key Technologies**: tkinter (GUI), pynput (input handling), requests (HTTP), pyinstaller (packaging)

## Build Instructions and Development Setup

### Prerequisites for Coding Agents
- **Python Version**: Requires Python 3.14 or higher
- **Dependencies**: All required dependencies are already installed in your global environment
- **Package**: The prism package is already installed in development mode in your global environment
- **Virtual Environment**: **CRITICAL - DO NOT USE** virtual environments. Dependencies and package are pre-installed globally.
- **Platform**: Linux environment (coding agents run in Linux containers)

### Initial Setup

**No setup required** - the prism package and all dependencies are already installed in your environment.

**Verify setup works** (optional):
```bash
python -c "from prism import VERSION_STRING; print(f'Setup OK: {VERSION_STRING}')"
```

**Note for Standard Users**: While this repository's documentation may reference virtual environments, coding agents must NOT use them as dependencies and the package are pre-installed globally. If you ever need to install dependencies or the package manually (unlikely), use:
```bash
# Only if dependencies or package are missing (should not happen)
pip install -r requirements/linux.txt -r requirements/linux-dev.txt
pip install --no-deps -e .
```

### Core Development Commands

#### Testing (ALWAYS run before committing)
```bash
# Run full test suite with coverage (REQUIRED - must pass 100%)
coverage run
coverage report

# Type checking (REQUIRED - must pass with --strict)
mypy --strict .
```

#### Code Quality (REQUIRED before committing)
```bash
# Format code (REQUIRED - enforced by CI)
black .
isort .

# Lint code (REQUIRED - must pass)
flake8 .
```

#### Core Development Commands for Coding Agents

**Important**: This is a GUI desktop application. Do not attempt to run the application in a headless environment.



### Dependency Management
**IMPORTANT**: Dependencies are managed with uv and are platform-specific.

- **Base dependencies**: Defined in `pyproject.toml`
- **Development dependencies**: Defined in `pyproject.toml`
- **Compiled requirements**: Defined in `uv.lock`

### Common Issues and Workarounds

1. **Import Issues**: Package and dependencies are pre-installed; if imports fail, see troubleshooting section
2. **Platform Dependencies**: Use Linux requirements (`requirements/linux.txt` + `requirements/linux-dev.txt`)
3. **Coverage Requirement**: Tests must maintain 100% coverage (some files are excluded in setup.cfg)
4. **Network Issues**: Some dependencies require network access; use offline wheels if needed

### Building and Distribution

**Note**: As a coding agent, you typically don't need to build binaries. If tests and linting pass, the PyInstaller build will likely succeed. This saves significant time in the development cycle.

## Project Layout and Architecture

### Source Code Structure
```
src/prism/                      # Main source package
├── __init__.py                 # Version info and constants
├── overlay/                    # Main overlay application
│   ├── __main__.py            # Application entry point
│   ├── controller.py          # Main application controller
│   ├── settings.py            # User settings management
│   ├── state.py               # Application state
│   ├── output/                # GUI components
│   ├── platform/              # Platform-specific code
│   └── user_interaction/      # User interface dialogs
├── hypixel.py                 # Hypixel API client
├── mojang.py                  # Mojang API client
├── calc.py                    # Statistics calculations
├── requests.py                # HTTP utilities
└── discordrp/                 # Discord Rich Presence
```

### Configuration Files
- `setup.cfg`: Package metadata, tool configurations, dependencies
- `pyproject.toml`: Black, isort, mypy configurations
- `.pre-commit-config.yaml`: Pre-commit hook definitions
- `requirements/*.txt`: Platform-specific pinned dependencies

### Test Structure
```
tests/
├── prism/                     # Unit tests mirroring src structure
├── data/                      # Test data (JSON files)
├── system_certs/              # SSL certificate tests
└── conftest.py                # Pytest configuration
```

### Build and CI/CD
- **GitHub Actions**: `.github/workflows/` (linting.yml, testing.yml)
- **PyInstaller**: `pyinstaller/` directory with hooks and icons
- **Distribution**: Automated builds for Windows (.exe), macOS (.dmg), Linux (binary)

### Key Dependencies
- **GUI**: tkinter (built into Python)
- **Input Handling**: pynput (cross-platform keyboard/mouse)
- **HTTP Requests**: requests + truststore for SSL
- **Packaging**: pyinstaller for standalone executables
- **Development**: black, isort, flake8, mypy, pytest, coverage

### Application Entry Points
1. **Development**: `python3 prism_overlay.py` or `python3 -m prism.overlay`
2. **Production**: Standalone executable built with pyinstaller

### Critical Validation Steps
Before making any changes, ALWAYS:
1. Run `coverage run && coverage report` (must be 100%)
2. Run `mypy --strict .` (must pass)
3. Run `black . && isort . && flake8 .` (must pass)

### Performance Notes
- **Build time**: PyInstaller builds take 2-5 minutes
- **Test time**: Full test suite runs in ~30 seconds
- **Coverage requirement**: 100% (with exclusions defined in setup.cfg)

### Platform-Specific Notes
- **Windows**: Requires pywin32 dependency
- **Linux**: Requires evdev, python-xlib for input handling
- **macOS**: Requires universal2 builds for Apple Silicon compatibility

## Trust These Instructions
These instructions are comprehensive and tested. Only search for additional information if:
1. Commands fail unexpectedly
2. New dependencies are added
3. Platform-specific issues arise
4. Instructions are incomplete or outdated

Always refer to GitHub Actions workflows (`.github/workflows/`) for the definitive build and test procedures used in CI.
