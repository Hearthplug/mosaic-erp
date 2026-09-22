"""Background provisioning of the local assistant Preview for desktop builds.

The desktop exe stays small; on first run it downloads the pinned base
model, the Mosaic adapter, and the pinned llama.cpp server into the
per-user data dir. Every byte is verified against the same sha256 pins
the Docker assistant-model-fetch flow uses. While provisioning runs,
the rest of Mosaic (including deterministic chat) works normally.
"""
import hashlib
import os
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

LLAMA_ZIP = (
    'https://github.com/ggml-org/llama.cpp/releases/download/b11065/llama-b11065-bin-win-cpu-x64.zip',
    18466663,
    '33f941a74b8db38e92690f5f151a770ef5a66481c07dabfe2e505b57e3546807',
)
MODEL_FILES = [
    ('https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf', 'model.gguf', 1117320736, '6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e'),
    ('https://github.com/Hearthplug/mosaic-erp/releases/download/assistant-model-exp5-c492/mosaic-exp5-c492-lora-bf16.gguf.part-00', 'adapter.gguf.part-00', 8388608, '980942078bf5528e03b18101185fbb2539dd5bd8b97e64fee13eccc342ce476e'),
    ('https://github.com/Hearthplug/mosaic-erp/releases/download/assistant-model-exp5-c492/mosaic-exp5-c492-lora-bf16.gguf.part-01', 'adapter.gguf.part-01', 8388608, '5ab825c8edcb33bda411789ef5df035eb1235bcd3f511ee99dce7b972c61dc34'),
    ('https://github.com/Hearthplug/mosaic-erp/releases/download/assistant-model-exp5-c492/mosaic-exp5-c492-lora-bf16.gguf.part-02', 'adapter.gguf.part-02', 8388608, '5953fa9d0e515bc524953b2f9fecf1b19cd20950b419bfc04638c4fbacebb32b'),
    ('https://github.com/Hearthplug/mosaic-erp/releases/download/assistant-model-exp5-c492/mosaic-exp5-c492-lora-bf16.gguf.part-03', 'adapter.gguf.part-03', 8388608, '91f58156a55ec1e869c3441bcf106a51e114da7a01b38d633fdd553c4543a94d'),
    ('https://github.com/Hearthplug/mosaic-erp/releases/download/assistant-model-exp5-c492/mosaic-exp5-c492-lora-bf16.gguf.part-04', 'adapter.gguf.part-04', 8388608, 'e6f86ad3bdb33d68fc88b4430d7626782f8f01f7eeac2d59f51d249db61d8872'),
    ('https://github.com/Hearthplug/mosaic-erp/releases/download/assistant-model-exp5-c492/mosaic-exp5-c492-lora-bf16.gguf.part-05', 'adapter.gguf.part-05', 8388608, 'c13bd02cca6bba84241f4adbf6699186fadd6d7ba58f7c6e176ca3d8a2edcf01'),
    ('https://github.com/Hearthplug/mosaic-erp/releases/download/assistant-model-exp5-c492/mosaic-exp5-c492-lora-bf16.gguf.part-06', 'adapter.gguf.part-06', 8388608, 'f9ef9faf9330b9fa9c0fe2543241dcf85f405cfe63970ee8e9f70ceb89968602'),
    ('https://github.com/Hearthplug/mosaic-erp/releases/download/assistant-model-exp5-c492/mosaic-exp5-c492-lora-bf16.gguf.part-07', 'adapter.gguf.part-07', 8388608, '360baf7439b30a0a686bb65e28bc2e6ac7f97289fd2f92a206d1f98645921b21'),
    ('https://github.com/Hearthplug/mosaic-erp/releases/download/assistant-model-exp5-c492/mosaic-exp5-c492-lora-bf16.gguf.part-08', 'adapter.gguf.part-08', 6777568, '4ebbe9cc64e616f44bd8fef1b05e9903288792acfcab03b9a970fd5918166049'),
    ('__concat__', 'adapter.gguf', 73886432, '353fe1febb5b3adc03a3b8a0bf3aa4b86bea55a5d3dfce17b102d5a61c73cd55'),
]
SERVER_PORT = 18080


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _download(url, target, size, sha, log):
    if target.exists() and target.stat().st_size == size and _sha256(target) == sha:
        return
    tmp = target.with_suffix(target.suffix + '.tmp')
    with urllib.request.urlopen(url) as r, tmp.open('wb') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    if tmp.stat().st_size != size or _sha256(tmp) != sha:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f'assistant download failed verification: {target.name}')
    tmp.replace(target)
    log(f'downloaded {target.name} ({size:,} bytes, verified)')


def _start_server(data, log):
    exe = data / 'llama' / 'llama-server.exe'
    model = data / 'models' / 'model.gguf'
    adapter = data / 'models' / 'adapter.gguf'
    server_log = open(data / 'assistant-server.log', 'ab', buffering=0)
    subprocess.Popen(
        [str(exe), '-m', str(model), '--lora', str(adapter),
         '--host', '127.0.0.1', '--port', str(SERVER_PORT), '-c', '2048', '-np', '1'],
        stdout=server_log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    log('local assistant server starting on 127.0.0.1:' + str(SERVER_PORT))


def _provision(data):
    status = data / 'assistant-status.txt'

    def log(msg):
        line = time.strftime('%H:%M:%S ') + msg
        print('[assistant]', msg, flush=True)
        try:
            status.write_text(msg + '\n')
        except OSError:
            pass

    try:
        ready = data / 'models' / '.ready'
        if not ready.exists():
            log('downloading the local assistant model (about 1.2 GB, one time only)')
            (data / 'models').mkdir(parents=True, exist_ok=True)
            (data / 'llama').mkdir(parents=True, exist_ok=True)
            url, size, sha = LLAMA_ZIP
            zip_path = data / 'llama' / 'llama-win.zip'
            _download(url, zip_path, size, sha, log)
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(data / 'llama')
            zip_path.unlink()
            for url, name, size, sha in MODEL_FILES:
                if url == '__concat__':
                    parts = [(data / 'models' / f'adapter.gguf.part-{i:02d}').read_bytes() for i in range(9)]
                    blob = b''.join(parts)
                    if len(blob) != size or hashlib.sha256(blob).hexdigest() != sha:
                        raise RuntimeError('assistant adapter failed verification')
                    (data / 'models' / 'adapter.gguf').write_bytes(blob)
                    for i in range(9):
                        (data / 'models' / f'adapter.gguf.part-{i:02d}').unlink(missing_ok=True)
                    log(f'verified {name} ({size:,} bytes)')
                    continue
                _download(url, data / 'models' / name, size, sha, log)
            ready.write_text('ok\n')
        if (data / 'llama' / 'llama-server.exe').exists():
            _start_server(data, log)
            log('local assistant Preview is ready')
    except Exception as exc:  # never take the ERP down with provisioning
        log('local assistant provisioning paused: ' + type(exc).__name__)
        print('[assistant] provisioning error:', exc, flush=True)


def start_background(data):
    """Kick off first-run provisioning. Frozen Windows builds only."""
    if os.environ.get('MOSAIC_SKIP_ASSISTANT_PROVISION'):
        return
    if os.name != 'nt':
        return
    threading.Thread(target=_provision, args=(Path(data),), daemon=True).start()
