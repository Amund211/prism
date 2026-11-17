#!/bin/sh
# Tab-list read cache with LOO CRNN + RapidOCR reads of each name region
export TL_MODEL=loo
export TL_CACHE=_loo_ocr
export TL_OCR=1
exec uv --directory /home/amund/git/overlay/tabcap-tablist/lab run python tl_cache.py -j 4
