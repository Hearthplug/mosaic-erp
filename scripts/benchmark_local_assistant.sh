#!/usr/bin/env bash
set -euo pipefail
arch=${1:?architecture}; test "$(uname -m)" = "$(test "$arch" = amd64 && echo x86_64 || echo aarch64)"
model_url='https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf'
expected_size=1117320736
adapter_url='https://github.com/Hearthplug/mosaic-erp/releases/download/assistant-model-exp5-c492/mosaic-exp5-c492-lora-bf16.gguf'
adapter_size=73886432
adapter_parts="00:980942078bf5528e03b18101185fbb2539dd5bd8b97e64fee13eccc342ce476e 01:5ab825c8edcb33bda411789ef5df035eb1235bcd3f511ee99dce7b972c61dc34 02:5953fa9d0e515bc524953b2f9fecf1b19cd20950b419bfc04638c4fbacebb32b 03:91f58156a55ec1e869c3441bcf106a51e114da7a01b38d633fdd553c4543a94d 04:e6f86ad3bdb33d68fc88b4430d7626782f8f01f7eeac2d59f51d249db61d8872 05:c13bd02cca6bba84241f4adbf6699186fadd6d7ba58f7c6e176ca3d8a2edcf01 06:f9ef9faf9330b9fa9c0fe2543241dcf85f405cfe63970ee8e9f70ceb89968602 07:360baf7439b30a0a686bb65e28bc2e6ac7f97289fd2f92a206d1f98645921b21 08:4ebbe9cc64e616f44bd8fef1b05e9903288792acfcab03b9a970fd5918166049"

curl --fail --location --retry 3 --output model.gguf "$model_url"
test "$(stat -c %s model.gguf)" = "$expected_size"
# Selection remains blocked until the expected digest is independently frozen in source.
echo '6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e  model.gguf' | sha256sum -c -
rm -f adapter.gguf
for part in $adapter_parts; do
  idx=${part%%:*}; sha=${part##*:}
  curl --fail --location --retry 3 --output "adapter.gguf.part-$idx" "$adapter_url.part-$idx"
  echo "$sha  adapter.gguf.part-$idx" | sha256sum -c -
  cat "adapter.gguf.part-$idx" >> adapter.gguf
  rm -f "adapter.gguf.part-$idx"
done
test "$(stat -c %s adapter.gguf)" = "$adapter_size"
echo '353fe1febb5b3adc03a3b8a0bf3aa4b86bea55a5d3dfce17b102d5a61c73cd55  adapter.gguf' | sha256sum -c -
build=11065
case $arch in amd64) asset_arch=x64; runtime_sha=f00971c1b044fae179230bfc6f8d9f8461b778fef9ffac2b450088081a8ecd43;; arm64) asset_arch=arm64; runtime_sha=6f2ae38a2948d983dcbd5ab1814aedb96a5e09eb2188c60e4b522fe1577ac3c1;; *) exit 2;; esac
curl --fail --location --output llama-server.tar.gz "https://github.com/ggml-org/llama.cpp/releases/download/b${build}/llama-b${build}-bin-ubuntu-${asset_arch}.tar.gz"
echo "$runtime_sha  llama-server.tar.gz" | sha256sum -c -
tar -xf llama-server.tar.gz
server=$(find . -type f -name llama-server -print -quit); test -n "$server"; chmod +x "$server"
started=$(date +%s.%N)
/usr/bin/time -v "$server" -m model.gguf --lora adapter.gguf --host 127.0.0.1 --port 18080 -c 2048 -np 1 >server.log 2>metrics.log & pid=$!
trap 'kill ${sampler:-} $pid 2>/dev/null || true' EXIT
: > resource-samples.txt
# Measure the actual llama-server process (child of /usr/bin/time), never the wrapper.
(for i in $(seq 1 100); do
  spid=$(pgrep -P "$pid" | head -1)
  test -n "$spid" && break
  sleep 0.2
done
spid=${spid:-$pid}
while kill -0 "$pid" 2>/dev/null; do ps -o rss=,%cpu= -p "$spid" >> resource-samples.txt || true; sleep 0.1; done) & sampler=$!
ready=0
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:18080/health >/dev/null; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1
startup_s=$(python3 -c 'import sys; print(float(sys.argv[1])-float(sys.argv[2]))' "$(date +%s.%N)" "$started")
python3 scripts/evaluate_local_assistant.py "$arch" resource-samples.txt "$startup_s" > "benchmark-${arch}.json"
test -s "benchmark-${arch}.json"
python3 -m json.tool "benchmark-${arch}.json" >/dev/null
sha256sum "benchmark-${arch}.json" > "benchmark-${arch}.json.sha256"
cat "benchmark-${arch}.json"
