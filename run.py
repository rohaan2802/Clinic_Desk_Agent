"""Start ClinicDesk on a free port and open the browser."""
from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from app.config import settings

HOST = settings.host or '127.0.0.1'
PREFERRED = int(settings.port or 8000)


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _pids_on_port(port: int) -> list[int]:
    pids: list[int] = []
    try:
        result = subprocess.run(
            ['netstat', '-ano', '-p', 'tcp'],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return pids
    needle = f':{port}'
    for line in result.stdout.splitlines():
        if needle not in line or 'LISTENING' not in line.upper():
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            pids.append(int(parts[-1]))
        except ValueError:
            continue
    return list(dict.fromkeys(pid for pid in pids if pid > 0))


def _is_python_process(pid: int) -> bool:
    try:
        result = subprocess.run(
            ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return False
    name = result.stdout.lower()
    return 'python' in name or 'uvicorn' in name


def _free_port(port: int) -> None:
    for pid in _pids_on_port(port):
        if pid == 0 or not _is_python_process(pid):
            continue
        subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True, check=False)


def choose_port(host: str, preferred: int) -> int:
    if _port_free(host, preferred):
        return preferred
    _free_port(preferred)
    time.sleep(0.5)
    if _port_free(host, preferred):
        return preferred
    for port in range(preferred + 1, preferred + 40):
        if _port_free(host, port):
            return port
    raise RuntimeError('No free TCP port found in the ClinicDesk range')


def wait_until_ready(host: str, port: int, timeout: float = 45.0) -> bool:
    """Poll until the HTTP app answers — debugpy + import cold start can take several seconds."""
    deadline = time.time() + timeout
    health = f'http://{host}:{port}/health'
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                pass
        except OSError:
            time.sleep(0.25)
            continue
        try:
            from urllib.request import urlopen
            with urlopen(health, timeout=1.5) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def open_browser(url: str, host: str | None = None, port: int | None = None) -> None:
    target_host = host or HOST
    if port is None:
        try:
            port = int(url.rsplit(':', 1)[-1].rstrip('/').split('/', 1)[0])
        except ValueError:
            port = PREFERRED
    if wait_until_ready(target_host, port):
        webbrowser.open(url)
    else:
        print(f'ClinicDesk is slow to start. Open manually: {url}', flush=True)


if __name__ == '__main__':
    port = choose_port(HOST, PREFERRED)
    url = f'http://{HOST}:{port}/'
    print(f'ClinicDesk starting on {url}')
    threading.Thread(target=open_browser, args=(url, HOST, port), daemon=True).start()
    uvicorn.run(
        'app.main:app',
        host=HOST,
        port=port,
        workers=1,
        reload=False,
        app_dir=str(Path(__file__).resolve().parent),
    )
    sys.exit(0)
