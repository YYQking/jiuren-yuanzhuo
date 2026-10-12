"""Windows launch regression: an error dialog is not a successful startup."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import time


def app_windows(pid):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    windows = []

    @callback_type
    def visit(handle, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value == pid:
            title = ctypes.create_unicode_buffer(1024)
            class_name = ctypes.create_unicode_buffer(256)
            rect = wintypes.RECT()
            user32.GetWindowTextW(handle, title, len(title))
            user32.GetClassNameW(handle, class_name, len(class_name))
            user32.GetWindowRect(handle, ctypes.byref(rect))
            windows.append({"handle": int(handle), "title": title.value,
                            "class": class_name.value,
                            "visible": bool(user32.IsWindowVisible(handle)),
                            "rect": [rect.left, rect.top, rect.right, rect.bottom]})
        return True

    user32.EnumWindows(visit, 0)
    return windows


def main():
    # Match GetWindowRect coordinates to ImageGrab's physical pixels on scaled
    # Windows displays; DPI virtualization otherwise crops the screenshot.
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
    user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    user32.SetProcessDpiAwarenessContext(wintypes.HANDLE(-4))
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--keep-open", action="store_true")
    args = parser.parse_args()
    executable = args.executable.resolve()
    env = dict(os.environ)
    env.pop("QT_QPA_PLATFORM", None)
    env.pop("QT_DEBUG_PLUGINS", None)
    process = subprocess.Popen([str(executable)], cwd=executable.parent, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    success = False
    windows = []
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(f"Application exited during startup: {process.returncode}")
            windows = app_windows(process.pid)
            errors = [w for w in windows if w["class"] == "#32770" and w["visible"]]
            if errors:
                raise AssertionError(f"Startup error dialog: {errors}")
            main_windows = [w for w in windows if w["title"] == "九人圆桌"
                            and w["class"].startswith("Qt") and w["visible"]
                            and w["rect"][2] - w["rect"][0] >= 600
                            and w["rect"][3] - w["rect"][1] >= 400]
            if main_windows:
                user32.SetForegroundWindow(wintypes.HWND(main_windows[0]["handle"]))
                time.sleep(2)
                assert process.poll() is None, f"Application exited after opening its main window: {process.returncode}"
                window = main_windows[0]
                if args.screenshot:
                    from PIL import ImageGrab
                    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    ImageGrab.grab(bbox=tuple(window["rect"]), all_screens=True).save(args.screenshot)
                print(json.dumps({"status": "PASS", "pid": process.pid, "main_window": window,
                                  "screenshot": str(args.screenshot) if args.screenshot else None},
                                 ensure_ascii=False), flush=True)
                success = True
                return
            time.sleep(0.2)
        raise AssertionError(f"No visible Qt main window within 20 seconds: {windows}")
    finally:
        if not (success and args.keep_open):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
