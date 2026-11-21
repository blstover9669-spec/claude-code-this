"""Hand-off between the boot steps, the loading screen and the chat.

The starter system and ai-sysinit report how far loading has got with write_progress();
the loading screen (aios.loader_ui) shows it with read_progress() and closes itself when
`done` is true. The chat calls finish_loading() once it can draw: that sets `done` and
waits until the loading screen has let go of the screen.

Everything lives in /run/aios (override with AIOS_RUN), as small JSON files written atomically.
"""
import json, os, time

RUN = os.environ.get("AIOS_RUN", "/run/aios")
PROGRESS = os.path.join(RUN, "progress.json")
LOADER_PID = os.path.join(RUN, "loader-ui.pid")


def write_progress(fraction, stage, detail="", done=False, error=None):
    """Report loading progress. fraction 0..1, stage e.g. 'Reading AI OS from the disc',
    detail e.g. '104 of 168 MB'. error: a message to show instead of progress (loading stopped)."""
    os.makedirs(RUN, exist_ok=True)
    tmp = PROGRESS + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({"fraction": max(0.0, min(1.0, float(fraction))), "stage": stage, "detail": detail,
                   "done": bool(done), "error": error, "time": time.time()}, fh)
    os.replace(tmp, PROGRESS)


def read_progress():
    """The latest progress dict, or None when nothing has been reported."""
    try:
        with open(PROGRESS) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def loader_running():
    """Is the loading screen still running (and therefore drawing on the screen)?"""
    try:
        pid = int(open(LOADER_PID).read().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def finish_loading(timeout=6.0):
    """Tell the loading screen that AI OS is ready, then wait for it to close (it shows
    'Ready' for about a second first). Returns True when the screen is free."""
    p = read_progress() or {}
    write_progress(1.0, "AI OS is ready", p.get("detail", ""), done=True)
    end = time.time() + timeout
    while loader_running() and time.time() < end:
        time.sleep(0.05)
    return not loader_running()
