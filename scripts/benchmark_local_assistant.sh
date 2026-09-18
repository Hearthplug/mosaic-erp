#!/usr/bin/env bash
set -euo pipefail
arch=${1:?architecture}; test "$(uname -m)" = "$(test "$arch" = amd64 && echo x86_64 || echo aarch64)"
model_url='https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/9217f5db79a29953eb74d5343926648285ec7e67/qwen2.5-0.5b-instruct-q4_k_m.gguf'
expected_size=491400032
curl --fail --location --retry 3 --output model.gguf "$model_url"
test "$(stat -c %s model.gguf)" = "$expected_size"
# Selection remains blocked until the expected digest is independently frozen in source.
echo '74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db  model.gguf' | sha256sum -c -
build=10702
case $arch in amd64) asset_arch=x64; runtime_sha=20d3a2fad25914a9049100fb644053b4e10b1c4dcf4370f527afc73ea179da89;; arm64) asset_arch=arm64; runtime_sha=057884c748e8d085eea71db0409d68e15873ff5062749d98fb29cde6aeae2db9;; *) exit 2;; esac
curl --fail --location --output llama-server.tar.gz "https://github.com/ggml-org/llama.cpp/releases/download/b${build}/llama-b${build}-bin-ubuntu-${asset_arch}.tar.gz"
echo "$runtime_sha  llama-server.tar.gz" | sha256sum -c -
tar -xf llama-server.tar.gz
server=$(find . -type f -name llama-server -print -quit); test -n "$server"; chmod +x "$server"
started=$(date +%s.%N)
/usr/bin/time -v "$server" -m model.gguf --host 127.0.0.1 --port 18080 -c 2048 -np 1 >server.log 2>metrics.log & pid=$!
trap 'kill ${sampler:-} $pid 2>/dev/null || true' EXIT
: > resource-samples.txt
(while kill -0 "$pid" 2>/dev/null; do ps -o rss=,%cpu= -p "$pid" >> resource-samples.txt || true; sleep 0.1; done) & sampler=$!
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
