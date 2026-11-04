#!/bin/bash
# Usage: sweep2.sh N_PER_SEED "args1" "args2" ...  (each config on seeds 11 and 12, all in parallel)
n=$1; shift; SEEDS=${SEEDS:-11 12}
dir=$(mktemp -d -p .mpcc_dev)
i=0
for args in "$@"; do
  for seed in $SEEDS; do
    python .mpcc_dev/run.py --n $n --seed $seed $args 2>&1 | grep -E "^ep " > $dir/$i.$seed &
  done
  i=$((i+1))
done
wait
i=0
for args in "$@"; do
  cat $dir/$i.* | python -c "
import sys, re
lines = sys.stdin.read().splitlines()
ok = [float(re.search(r't=([\d.]+)s', l).group(1)) for l in lines if ' OK ' in l]
fails = [re.search(r'gates=(\d)', l).group(1) for l in lines if 'FAIL' in l]
print(f'{len(ok)}/{len(lines)} ok, mean {sum(ok)/max(len(ok),1):.3f}s, best {min(ok, default=0):.2f}s, fail at gate idx {sorted(fails)} | $args')
"
  i=$((i+1))
done
rm -r $dir
