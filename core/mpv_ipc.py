import json
import subprocess

def _mpv_ipc(cmd: dict, timeout: float = 0.3):
    """
    Send a JSON IPC command to mpv and return parsed response.
    Returns None on failure.
    """
    if not SOCKET.exists():
        return None

    try:
        proc = subprocess.run(
            ["socat", "-", str(SOCKET)],
            input=(json.dumps(cmd) + "\n").encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        if not proc.stdout:
            return None
        return json.loads(proc.stdout.decode())
    except Exception:
        return None
