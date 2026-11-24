#!/usr/bin/env bash
# Run the overlay's --test-tabcap mode on one fixture, so a model or native
# library missing from the bundle fails the build.
#
# Usage: tests/tabcap_integration.sh <command that runs the overlay...>
set -euo pipefail

cmd=("$@")
# Synthetic: no real names
fixture="synthetic-win-forge-optifine-vanilla-gs3-1440p-game-start-15rows-01"

png="$(uv run python -c "
from tests.tabcap_fixtures import ensure, load_manifest
m = load_manifest()
print(ensure(m, [m.fixtures['$fixture']]) / '$fixture.png')
" | tail -n 1 | tr -d '\r')"

mkdir -p tabcap-test
# Don't open the settings prompt
echo 'autowho = true' > tabcap-test/settings.toml
touch tabcap-test/latest.log

out="$("${cmd[@]}" --test-tabcap="$png" --settings=tabcap-test/settings.toml --logfile=tabcap-test/latest.log)"
echo "$out"
if ! grep -q "^Tabcap OK: " <<< "$out"; then
	echo "::error::--test-tabcap did not read the tab list"
	exit 1
fi
