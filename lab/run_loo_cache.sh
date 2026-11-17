#!/bin/sh
# Build the tab-list read cache with the leave-own-font-out CRNN models
export TL_MODEL=loo
export TL_CACHE=_loo
exec uv --directory /home/amund/git/overlay/tabcap-tablist/lab run python tl_cache.py -j 4
