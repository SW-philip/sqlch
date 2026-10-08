import subprocess
import threading


def notify(title: str, body: str):
    try:
        proc = subprocess.Popen(['notify-send', title, body])
    except Exception:
        return
    # the daemon never waits on it, so an unreaped child lingers as a zombie
    threading.Thread(target=proc.wait, daemon=True).start()
