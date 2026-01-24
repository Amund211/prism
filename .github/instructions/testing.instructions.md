---
applyTo: 
  - "tests/**"
  - "**/*test*.py"
  - "**/test_*.py"
---

# Testing Instructions for Prism

## Test Infrastructure Overview
Prism uses pytest with comprehensive test coverage requirements and strict type checking.

## Running Tests

### Full Test Suite (REQUIRED before committing)
```bash
# Run tests with coverage (MUST achieve 100% coverage)
coverage run
coverage report

# The above commands are equivalent to:
# coverage run -m pytest -r fEs
# coverage report --show-missing --skip-covered --fail-under=100
```

### Type Checking (REQUIRED)
```bash
# Must pass strict type checking
mypy --strict .
```

### Individual Test Commands
```bash
# Run specific test file
python -m pytest tests/prism/test_hypixel.py -v

# Run tests with specific pattern
python -m pytest -k "test_stats" -v

# Run tests with detailed output
python -m pytest -r fEs -v
```

## Test Structure
- **Unit Tests**: Located in `tests/prism/` mirroring `src/prism/` structure
- **Test Data**: JSON files in `tests/data/` (player stats samples)
- **System Tests**: SSL certificate tests in `tests/system_certs/`
- **Mock Utilities**: Helper functions in `tests/mock_utils.py`

## Coverage Requirements
- **Target**: 100% test coverage (enforced in CI)
- **Exclusions**: Defined in `setup.cfg` under `[coverage:report]`
  - `src/prism/stats.py` (external data)
  - `src/prism/overlay/platform/windows.py` (platform-specific)
  - `src/prism/discordrp/__init__.py` (optional feature)

## Test Configuration
- **Config File**: `tests/conftest.py` contains pytest fixtures
- **Coverage Config**: `setup.cfg` section `[coverage:run]` and `[coverage:report]`
- **Source Path**: Coverage runs on `src/prism` specifically

## Common Test Patterns
1. **API Mocking**: Tests mock HTTP requests to avoid network dependencies
2. **Fixture Usage**: Common test data loaded from `tests/data/`
3. **Platform Isolation**: Platform-specific code often mocked or excluded

## Test Execution in CI
GitHub Actions runs tests on:
- Ubuntu Latest (Linux)
- Windows Latest  
- macOS 13

With Python 3.14 across all platforms.

## Debugging Test Failures
```bash
# Run with maximum verbosity
python -m pytest -vvv --tb=long

# Run specific failing test
python -m pytest tests/prism/test_specific.py::test_function -vvv

# Check coverage report details
coverage report --show-missing
```

## Manual Test Execution
For coding agents, run tests manually:
```bash
coverage run
coverage report
mypy --strict .
```

## Writing New Tests
1. Mirror the source structure in `tests/prism/`
2. Use descriptive test names: `test_function_behavior_when_condition`
3. Mock external dependencies (HTTP, file system, etc.)
4. Ensure 100% coverage of new code
5. Follow existing patterns in the test suite

## Test Data Management
- Player data samples in `tests/data/*.json`
- Use existing samples when possible
- Add new test data sparingly and document its purpose
