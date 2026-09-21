#!/bin/bash
# 静かなマシンで直列に測る。負荷が高ければ止まる。
# 使い方: ./measure.sh
set -u
cd "$(dirname "$0")"

LA=$(uptime | sed 's/.*load averages*: *//' | awk '{print $1}')
if (( $(python3 -c "print(1 if $LA > 2.0 else 0)") )); then
  echo "!! load average $LA -- 他のプロセスが動いている。計測を中止" >&2
  ps aux | awk '$3 > 40 {print "   busy:", $3"%", $11, $12, $13}' >&2
  exit 1
fi
echo "load average $LA -- 計測開始"
echo

best() {
  local b=999 s
  for i in 1 2 3; do
    s=$(python3 -c 'import time,subprocess,sys
t=time.perf_counter(); subprocess.run(sys.argv[1:],stdout=subprocess.DEVNULL); print(f"{time.perf_counter()-t:.3f}")' "$@")
    b=$(python3 -c "print(min($b,$s))")
  done
  echo "$b"
}

hdr() {
  echo "$1"
  printf "%-34s %-10s %-10s %-10s %-10s\n" "" "C(1core)" "SEQ" "PAR(10)" "GPU"
}

# row <label> <c-binary...> -- <bend-binary>
row() {
  local label="$1"; shift
  local cb=() ; while [ "$1" != "--" ]; do cb+=("$1"); shift; done; shift
  local bb="$1"
  printf "%-34s %-10s %-10s %-10s %-10s\n" "$label" \
    "$(best "${cb[@]}")s" \
    "$(best "$bb" --threads 1 --gpu off)s" \
    "$(best "$bb" --gpu off)s" \
    "$(best "$bb")s"
}

# GPU が本当に動いたか: user 時間がほぼ 0 なら GPU
gpucheck() {
  printf "  %-30s " "$1"
  { /usr/bin/time -p "$2" >/dev/null; } 2>&1 | awk '{printf "%s=%s ", $1, $2} END{print ""}'
}

# ---------------------------------------------------------------- p3
hdr "## 共有木への並列ランダムアクセス (gather 2^24 回)"
printf "%-34s %-10s %-10s %-10s %-10s\n" "木 2^14 葉 (キャッシュ常駐)" \
  "$(best ./p3/bin/gc_d14)s" \
  "$(best ./p3/bin/g_d14 --threads 1 --gpu off)s" \
  "$(best ./p3/bin/g_d14 --gpu off)s" \
  "$(best ./p3/bin/g_d14)s"
printf "%-34s %-10s %-10s %-10s %-10s\n" "木 2^22 葉 (キャッシュ外)" \
  "$(best ./p3/bin/gc_d22)s" \
  "$(best ./p3/bin/g_d22 --threads 1 --gpu off)s" \
  "$(best ./p3/bin/g_d22 --gpu off)s" \
  "$(best ./p3/bin/g_d22)s"
echo
echo "  C ポインタ木 (同形の対照, 1core):"
printf "    2^14 葉: %ss   2^22 葉: %ss\n" "$(best ./p3/bin/gt_d14)" "$(best ./p3/bin/gt_d22)"
echo
echo "## GPU 実行確認 (user が 0 なら GPU が計算している)"
gpucheck "gather 2^22 --gpu on"  "./p3/bin/g_d22"
