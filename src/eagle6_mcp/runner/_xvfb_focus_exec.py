"""Helper executed inside ``xvfb-run`` to launch EAGLE v6 and focus its editor window.

Engineering rationale:
    CadSoft EAGLE 6.6.0 (built on Qt4) defers execution of ``-C`` commands until
    its editor window (Schematic, Board, or Library) receives an X11 input focus
    / window-activation event. Because bare ``xvfb-run`` runs Xvfb without a
    window manager, newly mapped windows never receive focus and ``eagle -C``
    hangs indefinitely.

    This small helper runs under ``xvfb-run``, spawns EAGLE, polls X11 for the
    mapped editor window via ``xwininfo``, and calls ``libX11.so.6``
    (``XRaiseWindow`` + ``XSetInputFocus``) so EAGLE immediately executes its
    ``-C`` command and exits cleanly.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time


_EDITOR_MARKERS = ("Schematic -", "Board -", "Library -")


def _focus_eagle_editor(dpy: int, libx11: ctypes.CDLL) -> bool:
    """Locate a mapped EAGLE editor window on the root X11 tree and focus it."""
    try:
        out = subprocess.check_output(
            ["xwininfo", "-root", "-tree"], text=True, stderr=subprocess.DEVNULL
        )
    except (subprocess.SubprocessError, OSError):
        return False

    for line in out.splitlines():
        if any(marker in line for marker in _EDITOR_MARKERS):
            tokens = line.strip().split()
            if not tokens:
                continue
            try:
                wid = int(tokens[0], 16)
            except ValueError:
                continue
            # RevertToParent = 1, CurrentTime = 0
            libx11.XRaiseWindow(dpy, wid)
            libx11.XSetInputFocus(dpy, wid, 1, 0)
            libx11.XFlush(dpy)
            return True
    return False


def main(argv: list[str]) -> int:
    """Spawn EAGLE with the forwarded CLI arguments and focus its editor window."""
    if len(argv) < 2:
        sys.stderr.write("Usage: _xvfb_focus_exec.py <eagle_bin> [args...]\n")
        return 2

    display_name = os.environ.get("DISPLAY")
    if not display_name:
        sys.stderr.write("DISPLAY environment variable is not set.\n")
        return 2

    libx11 = ctypes.CDLL("libX11.so.6")
    libx11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    libx11.XOpenDisplay.restype = ctypes.c_void_p
    libx11.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    libx11.XSetInputFocus.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_ulong,
    ]
    libx11.XFlush.argtypes = [ctypes.c_void_p]
    libx11.XCloseDisplay.argtypes = [ctypes.c_void_p]

    dpy = libx11.XOpenDisplay(display_name.encode("utf-8"))
    if not dpy:
        sys.stderr.write(f"Failed to open X11 display '{display_name}'.\n")
        return 2

    proc = subprocess.Popen(argv[1:])
    try:
        while proc.poll() is None:
            _focus_eagle_editor(dpy, libx11)
            time.sleep(0.2)
        return proc.returncode if proc.returncode is not None else 1
    finally:
        libx11.XCloseDisplay(dpy)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
