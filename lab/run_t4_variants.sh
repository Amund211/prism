#!/bin/sh
# T4 ablations: fix only, verify only, both with loo
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
T4_VERIFY=0 uv run python tbench.py t4_selffont -j 4 2>&1 | grep '^t4' | sed 's/^/fix-only /'
T4_FIX=0 uv run python tbench.py t4_selffont -j 4 2>&1 | grep '^t4' | sed 's/^/verify-only /'
T4_FIX=0 T4_MAX_D=0.55 uv run python tbench.py t4_selffont -j 4 2>&1 | grep '^t4' | sed 's/^/verify-0.55 /'
T4_FIX=0 T4_VERIFY=0 uv run python tbench.py t4_selffont -j 4 2>&1 | grep '^t4' | sed 's/^/neither /'
