import subprocess

def notify(title: str, body: str):
    try:
        subprocess.Popen(["notify-send", title, body])
    except Exception:
        pass

send = notify
