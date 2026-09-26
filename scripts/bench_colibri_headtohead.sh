#!/usr/bin/env bash
# Colibri OLMoE side of the head-to-head bench. Builds the pinned colibri
# engine, converts OLMoE-1B-7B-0125-Instruct to its int8 merged format,
# serves it through colibri's OpenAI-compatible gateway, and runs the frozen
# 50-case suite through scripts/evaluate_colibri_olmoe.py.
# Writes benchmark-colibri-olmoe.json (+ .sha256) and colibri-olmoe-raw.jsonl.
set -euo pipefail
colibri_sha='ce370e87d7b623d7759b52ec2007d75fc5b0e87e'
work=${RUNNER_TEMP:-/tmp}/colibri-bench
rm -rf "$work"; mkdir -p "$work"; cd "$work"
git clone --quiet https://github.com/JustVugg/colibri.git colibri
cd colibri && git checkout --quiet "$colibri_sha" && cd ..
echo "colibri pinned at $colibri_sha"
make -C colibri/c olmoe
test -x colibri/c/olmoe
python3 -m pip install --quiet numpy safetensors huggingface_hub
python3 -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
python3 colibri/c/tools/convert_olmoe_merged.py --repo allenai/OLMoE-1B-7B-0125-Instruct --out olmoe_merged
du -sh olmoe_merged
du -sb olmoe_merged colibri/c/olmoe | awk '{s+=$1} END {print s}' > disk-bytes.txt
started=$(date +%s.%N)
python3 colibri/c/openai_server.py --model "$work/olmoe_merged" --arch olmoe --engine "$work/colibri/c/olmoe" --host 127.0.0.1 --port 18081 --max-tokens 260 >server.log 2>&1 & pid=$!
trap 'kill ${sampler:-} $pid 2>/dev/null || true' EXIT
: > resource-samples.txt
ready=0
for i in $(seq 1 900); do
  if curl -fsS http://127.0.0.1:18081/v1/models >/dev/null 2>&1; then ready=1; break; fi
  kill -0 "$pid" 2>/dev/null || { echo 'server exited before ready'; tail -30 server.log; exit 1; }
  sleep 1
done
test "$ready" = 1
startup_s=$(python3 -c "import time;print(f'{time.time()-$started:.1f}')")
(spid=''
while kill -0 "$pid" 2>/dev/null; do
  if test -z "$spid"; then spid=$(pgrep -x olmoe | head -1); fi
  if test -n "$spid"; then ps -o rss=,%cpu= -p "$spid" >> resource-samples.txt 2>/dev/null || true; fi
  sleep 0.5
done) & sampler=$!
cd "$GITHUB_WORKSPACE"
cp "$work/disk-bytes.txt" . 2>/dev/null || true
python3 scripts/evaluate_colibri_olmoe.py "$work/benchmark-colibri-olmoe.json" "$work/colibri-olmoe-raw.jsonl" "$work/resource-samples.txt" "$startup_s"
cp "$work/benchmark-colibri-olmoe.json" "$work/colibri-olmoe-raw.jsonl" "$work/server.log" .
(cd . && sha256sum benchmark-colibri-olmoe.json > benchmark-colibri-olmoe.json.sha256)
