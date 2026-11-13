"""Win32 calls shared by services and engines, independent of Qt."""
import ctypes

user32 = ctypes.windll.user32


def activate_window(hwnd):
    """Bring a window to the foreground, restoring it when minimized."""
    if not hwnd:
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    fg = user32.GetForegroundWindow()
    cur = ctypes.windll.kernel32.GetCurrentThreadId()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    attached = fg_thread and fg_thread != cur and user32.AttachThreadInput(cur, fg_thread, True)
    user32.BringWindowToTop(hwnd)
    ok = bool(user32.SetForegroundWindow(hwnd))
    if attached:
        user32.AttachThreadInput(cur, fg_thread, False)
    return ok
