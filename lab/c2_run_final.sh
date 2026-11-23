#!/bin/sh
# C2 final model to ship: the rk4_ recipe (round 11) on ALL real train rows (no fold held out).
# kf4 (v3c3_tf + kinds synth / composite) + 100k v3k_s1 + realk_all x8, 4 epochs.
# Its train-split scores are not fair (it saw every real row); judge it by rk4_ (folds).
cd /home/amund/git/overlay/tabcap-tablist/lab || exit 1
L=results/c2/logs
R=results/c2

[ -f $R/realk_all.pkl ] || uv run python c2_real.py kinds > $L/realk_all.log 2>&1
[ -f $R/rk4_all.onnx ] || uv run python c2_train.py rk4_all v3k_s1 -1 4 --tokens --kinds --threads 12 \
  --width 1.5 --depth 4 --tf 2 --init kf4 --lr 1e-3 --limit 100000 --extra realk_all:8 >> $L/rk4_all.log 2>&1
sha256sum $R/rk4_all.onnx > $R/rk4_all.onnx.sha256
echo done > $L/FINAL_DONE
