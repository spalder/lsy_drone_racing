#!/bin/bash
# Usage: sweep.sh N_EPISODES SEED "args1" "args2" ...  (runs configs in parallel)
n=$1; seed=$2; shift 2
i=0
for args in "$@"; do
  ( out=$(python .mpcc_dev/run.py --n $n --seed $seed $args 2>&1 | grep -E "^ep|^success" | grep -E "FAIL|success")
    echo "== $args"; echo "$out" ) &
  i=$((i+1))
done
wait
