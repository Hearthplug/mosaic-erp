"""Windows desktop entry point for Mosaic ERP.

Starts the same Mosaic server the source install runs, then opens the
default browser at the sign-in page. Data lives in the per-user
%LOCALAPPDATA%\\MosaicERP folder so the app never needs write access to
its own install directory. Close the console window to stop Mosaic.
"""
import os
import socket
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path


def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    if getattr(sys, 'frozen', False):
        data = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'MosaicERP'
    else:
        data = Path.cwd() / 'mosaic-desktop-data'
    data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('MOSAIC_DB_PATH', str(data / 'mosaic.db'))
    os.environ['MOSAIC_HOST'] = '127.0.0.1'
    if getattr(sys, 'frozen', False):
        # Local assistant Preview: loopback llama.cpp server, provisioned on
        # first run into the per-user data dir. The availability gate file is
        # the CI-produced verdict bundled into the exe at build time.
        os.environ.setdefault('MOSAIC_ASSISTANT_LOCAL_URL', 'http://127.0.0.1:18080')
        gate = Path(getattr(sys, '_MEIPASS', '.')) / 'local-assistant-availability.json'
        if gate.exists():
            os.environ.setdefault('MOSAIC_ASSISTANT_LOCAL_AVAILABILITY_FILE', str(gate))
        if os.getenv('MOSAIC_SKIP_ASSISTANT_PROVISION') != '1':
            try:
                from scripts.assistant_provision import start_background
                start_background(data)
            except Exception as exc:
                # The local assistant is a Preview add-on: a provisioning
                # failure must never stop the ERP itself from starting.
                print(f'Local assistant setup skipped: {exc}')
    port = int(os.getenv('PORT', '0')) or _free_port()
    os.environ['PORT'] = str(port)

    import app  # applies database migrations on import

    url = f'http://127.0.0.1:{port}/signin'
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f'Mosaic ERP is running at {url}')
    print(f'Your data is stored in: {data}')
    print('Keep this window open while you use Mosaic. Close it to stop.')
    try:
        ThreadingHTTPServer(('127.0.0.1', port), app.H).serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
