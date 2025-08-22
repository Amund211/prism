# Prism Development Instructions

## High-Level Repository Information

**Project Summary**: Prism is an open-source Python desktop application that provides a real-time stats overlay for Hypixel Bedwars players. It automatically detects players in lobbies and displays their statistics in a customizable overlay window.

**Repository Size**: ~61 Python source files, ~20 test files, medium-sized project (~500KB)
**Primary Language**: Python 3.12+ (currently using 3.13)
**Application Type**: Desktop GUI application (tkinter-based overlay)
**Target Platforms**: Windows, macOS, Linux with platform-specific builds
**Key Technologies**: tkinter (GUI), pynput (input handling), requests (HTTP), pyinstaller (packaging)

## Build Instructions and Development Setup

### Prerequisites
- **Python Version**: Requires Python 3.12 or higher (project currently uses 3.13)
- **Virtual Environment**: Always use a virtual environment to isolate dependencies
- **Platform**: Linux/macOS/Windows supported with platform-specific requirements

### Initial Setup (CRITICAL - Follow This Order)

1. **Create and activate virtual environment** (REQUIRED):
```bash
python3 -m venv venv

# Activation depends on your platform:
source venv/bin/activate              # Linux/macOS
# OR
venv\Scripts\activate.bat            # Windows cmd
# OR  
venv\Scripts\activate.ps1            # Windows PowerShell
```

2. **Install dependencies** (PLATFORM-SPECIFIC - pick ONE):
```bash
# For Linux development:
pip install -r requirements/linux.txt -r requirements/linux-dev.txt

# For Windows development:
pip install -r requirements/windows.txt -r requirements/windows-dev.txt

# For macOS development:
pip install -r requirements/mac.txt -r requirements/mac-dev.txt
```

3. **Install the package in development mode**:
```bash
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

#### Running the Application
```bash
# Run overlay from source (requires log file for testing)
python3 prism_overlay.py --help
python3 prism_overlay.py --logfile=latest.log
```

#### Building Binaries
```bash
# Create versioned icon (REQUIRED before pyinstaller)
python add_version_to_icon.py

# Build single-file executable
pyinstaller prism_overlay.py --noconfirm --onefile --icon=pyinstaller/who_with_version.ico --name "prism-v1.9.1-dev" --additional-hooks-dir=pyinstaller
```

### Pre-commit Hooks Setup (RECOMMENDED)
```bash
# Install pre-commit (if not already installed)
pip install pre-commit

# Install hooks (runs quality checks automatically)
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

### Dependency Management
**IMPORTANT**: Dependencies are managed with pip-compile and are platform-specific.

- **Base dependencies**: Defined in `setup.cfg`
- **Development dependencies**: Defined in `requirements/dev.in`
- **Compiled requirements**: Platform-specific `.txt` files in `requirements/`

To update dependencies:
```bash
# Install pip-tools first
pip install pip-tools

# Recompile requirements (updates pinned versions)
pip-compile --output-file requirements/linux.txt setup.cfg
pip-compile --output-file requirements/linux-dev.txt requirements/dev.in
```

### Common Issues and Workarounds

1. **Virtual Environment Issues**: ALWAYS activate the virtual environment before running any commands
2. **Platform Dependencies**: Use the correct requirements file for your platform
3. **Coverage Requirement**: Tests must maintain 100% coverage (some files are excluded in setup.cfg)
4. **Import Issues**: Run `pip install --no-deps -e .` after dependency changes
5. **Network Issues**: Some dependencies require network access; use offline wheels if needed

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
- **GitHub Actions**: `.github/workflows/` (linting.yml, testing.yml, pip-compile.yml)
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
1. Activate virtual environment
2. Install correct platform dependencies
3. Run `coverage run && coverage report` (must be 100%)
4. Run `mypy --strict .` (must pass)
5. Run `black . && isort . && flake8 .` (must pass)

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