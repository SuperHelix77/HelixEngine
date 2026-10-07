#!/bin/zsh
# chained short training rounds (fresh process each) to avoid MPS allocator build-up
cd "$(dirname "$0")"
BASE=convaiinnovations/laya
for k in 0 1 2 3 4; do
  OUT=zs1_r$k
  [ -f $OUT/model.safetensors ] && { BASE=$OUT; continue; }
  ${HELIX_VENV:-../venv}/bin/python train_wrap.py --data zs1_shard$k.jsonl --out $OUT --base $BASE --epochs 1 --label-smoothing 0.05 --shuffle-options --device mps --micro-batch 2 --grad-accum 32 --max-len 320 > zs1_r$k.log 2>&1
  [ -f $OUT/model.safetensors ] || { echo "round $k failed" > zs1_FAILED; exit 1; }
  rm -rf $OUT/checkpoint_latest; BASE=$OUT
done
touch zs1_ROUNDS_DONE
