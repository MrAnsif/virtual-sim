"""
=============================================================
  HUD OVERLAY  —  DWM Layered Window (always-on-top)
  Pure Win32 + OpenCV/NumPy.
  No Pygame display initialization, no event loop hijacking.
  Fully click-through, stays above DirectX fullscreen windows.
=============================================================
"""

import ctypes
import ctypes.wintypes as wt
import sys
import numpy as np
import cv2

# ── Window geometry
HUD_W = 460
HUD_H = 38
HUD_X = 0       # distance from left edge of screen
HUD_Y = 0       # distance from top of screen

# ── Colors (B, G, R, A) — OpenCV uses BGRA order
C_BG        = (15,  15,  15,  210)
C_ACCEL     = (0,   210, 0,   255)
C_BRAKE     = (255, 100, 0,   255)  # Swap Red & Blue for BGR
C_CLUTCH    = (210, 210, 0,   255)  # Swap Red & Blue
C_STEER_L   = (255, 165, 0,   255)
C_STEER_R   = (0,   200, 255, 255)
C_BTN_ON    = (80,  80,  255, 255)
C_BTN_OFF   = (50,  50,  50,  200)
C_TEXT      = (220, 220, 220, 255)
C_BORDER    = (80,  80,  80,  255)
C_TRACK     = (40,  40,  40,  255)

# ── Win32 constants
GWL_EXSTYLE       = -20
WS_EX_LAYERED     = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST     = 0x00000008
WS_EX_TOOLWINDOW  = 0x00000080
WS_EX_NOACTIVATE  = 0x08000000
ULW_ALPHA         = 0x00000002
AC_SRC_OVER       = 0x00
AC_SRC_ALPHA      = 0x01

# ── Win32 structures
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp",             ctypes.c_byte),
        ("BlendFlags",          ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat",         ctypes.c_byte),
    ]

user32  = ctypes.windll.user32
gdi32   = ctypes.windll.gdi32
kernel32= ctypes.windll.kernel32

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_int64, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM)

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
        ("hIconSm", wt.HICON),
    ]

# Setup Windows API signatures for 64-bit safety
user32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_int64

def wnd_proc(hwnd, msg, wparam, lparam):
    if msg == 2:  # WM_DESTROY
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HINSTANCE

user32.LoadCursorW.argtypes = [wt.HINSTANCE, wt.LPCWSTR]
user32.LoadCursorW.restype = wt.HANDLE

user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wt.ATOM

user32.UnregisterClassW.argtypes = [wt.LPCWSTR, wt.HINSTANCE]
user32.UnregisterClassW.restype = wt.BOOL

user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID
]
user32.CreateWindowExW.restype = wt.HWND

user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.ShowWindow.restype = wt.BOOL

user32.UpdateWindow.argtypes = [wt.HWND]
user32.UpdateWindow.restype = wt.BOOL

user32.DestroyWindow.argtypes = [wt.HWND]
user32.DestroyWindow.restype = wt.BOOL

user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.SetWindowPos.restype = wt.BOOL

user32.GetDC.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC

user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.ReleaseDC.restype = ctypes.c_int

gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC

gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.DeleteDC.restype = wt.BOOL

gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ

gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteObject.restype = wt.BOOL

gdi32.CreateDIBSection.argtypes = [
    wt.HDC, ctypes.c_void_p, ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD
]
gdi32.CreateDIBSection.restype = wt.HBITMAP

user32.UpdateLayeredWindow.argtypes = [
    wt.HWND, wt.HDC, ctypes.POINTER(POINT), ctypes.POINTER(SIZE),
    wt.HDC, ctypes.POINTER(POINT), wt.DWORD, ctypes.POINTER(BLENDFUNCTION), wt.DWORD
]
user32.UpdateLayeredWindow.restype = wt.BOOL

user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
user32.PeekMessageW.restype = wt.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.TranslateMessage.restype = wt.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = ctypes.c_int64


class HUDOverlay:

    def __init__(self):
        if not sys.platform == "win32":
            raise RuntimeError("HUDOverlay requires Windows (DWM layered window).")

        self._wnd_proc_ref = WNDPROC(wnd_proc)

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._wnd_proc_ref
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = "PedalTrackerHUDClass"
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_wchar_p(32512))  # IDC_ARROW

        user32.RegisterClassExW(ctypes.byref(wc))

        self._hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            "PedalTrackerHUDClass",
            "__pedalhud__",
            0x80000000,  # WS_POPUP (borderless)
            HUD_X, HUD_Y, HUD_W, HUD_H,
            None, None, wc.hInstance, None
        )

        if not self._hwnd:
            raise RuntimeError("Could not create Win32 HUD window.")

        # Ensure it stays on top and show it
        user32.SetWindowPos(
            self._hwnd, -1,  # HWND_TOPMOST
            HUD_X, HUD_Y, HUD_W, HUD_H,
            0x0010 | 0x0040  # SWP_NOACTIVATE | SWP_SHOWWINDOW
        )
        user32.UpdateWindow(self._hwnd)

        self._last = {}
        # Force first draw
        self._draw_and_push({
            "accel": 0, "brake": 0, "clutch": 0, "steering": 0,
            "downshift": False, "upshift": False,
            "handbrake": False, "horn": False
        })

    def update(self, state: dict):
        # Pump Win32 messages for this window
        msg = wt.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), self._hwnd, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        keys = ("accel", "brake", "clutch", "steering",
                "downshift", "upshift", "handbrake", "horn")
        cur = {k: state[k] for k in keys if k in state}
        if cur == self._last:
            return
        self._last = cur.copy()
        self._draw_and_push(cur)

    def _draw_and_push(self, s):
        # Create transparent BGRA surface
        img = np.zeros((HUD_H, HUD_W, 4), dtype=np.uint8)
        img[:] = C_BG

        x = 6
        bh = 22
        by = (HUD_H - bh) // 2

        # Draw vertically centered left-aligned text
        def draw_text_vc(text, x, color, scale=0.32, thickness=1):
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
            ty = by + (bh + th) // 2 - 1
            cv2.putText(img, text, (x, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)
            return tw

        # ── Steering bar (bi-directional)
        steer_pct = s.get("steering", 0) / 32767.0
        sw = 50

        tw = draw_text_vc("ST", x, C_TEXT)
        x += tw + 3

        # Track
        cv2.rectangle(img, (x, by), (x + sw, by + bh), C_TRACK, -1)

        cx = x + sw // 2
        fl = int((sw // 2) * abs(steer_pct))
        col = C_STEER_L if steer_pct < 0 else C_STEER_R
        if steer_pct < 0:
            cv2.rectangle(img, (cx - fl, by), (cx, by + bh), col, -1)
        else:
            cv2.rectangle(img, (cx, by), (cx + fl, by + bh), col, -1)

        # Center line & Border
        cv2.line(img, (cx, by), (cx, by + bh - 1), C_TEXT, 1)
        cv2.rectangle(img, (x, by), (x + sw, by + bh), C_BORDER, 1)

        x += sw + 5

        # Helper to draw vertical bars
        def draw_bar(label, pct, color, bw):
            nonlocal x
            tw = draw_text_vc(label, x, C_TEXT)
            x += tw + 3

            # Track
            cv2.rectangle(img, (x, by), (x + bw, by + bh), C_TRACK, -1)

            # Fill
            fill = int(bw * max(0.0, min(1.0, pct)))
            if fill > 0:
                cv2.rectangle(img, (x, by), (x + fill, by + bh), color, -1)

            # Border
            cv2.rectangle(img, (x, by), (x + bw, by + bh), C_BORDER, 1)

            # Value label
            val_str = f"{int(pct*100):3d}%"
            val_tw = draw_text_vc(val_str, x + bw + 3, color, scale=0.35, thickness=1)

            x += bw + val_tw + 6

        draw_bar("AC", s.get("accel",  0) / 255.0, C_ACCEL,  38)
        draw_bar("BR", s.get("brake",  0) / 255.0, C_BRAKE,  38)
        draw_bar("CL", s.get("clutch", 0) / 255.0, C_CLUTCH, 38)

        # Helper to draw button indicators
        def draw_btn(label, active):
            nonlocal x
            col = C_BTN_ON if active else C_BTN_OFF

            # Button Box
            cv2.rectangle(img, (x, by), (x + 28, by + bh), col, -1)
            cv2.rectangle(img, (x, by), (x + 28, by + bh), C_BORDER, 1)

            # Label (perfectly centered)
            tc = (0, 0, 0, 255) if active else C_TEXT
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.32, 1)
            tx = x + (28 - tw) // 2
            ty = by + (bh + th) // 2 - 1
            cv2.putText(img, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.32, tc, 1, cv2.LINE_AA)

            x += 30

        draw_btn("DN", s.get("downshift", False))
        draw_btn("UP", s.get("upshift",   False))
        draw_btn("HB", s.get("handbrake", False))
        draw_btn("HR", s.get("horn",      False))

        # Premultiply alpha (mandatory for GDI layered window compositing)
        alpha = img[:, :, 3:4] / 255.0
        img[:, :, 0:3] = (img[:, :, 0:3] * alpha).astype(np.uint8)

        # Flip vertically because positive biHeight DIBs are bottom-up
        img_flipped = np.ascontiguousarray(np.flipud(img))
        bgra_bytes = img_flipped.tobytes()

        # Push pixels via GDI UpdateLayeredWindow
        screen_dc = user32.GetDC(None)
        mem_dc    = gdi32.CreateCompatibleDC(screen_dc)

        bmi_size  = ctypes.c_uint32(40)
        bmi = (ctypes.c_byte * 40)(
            *bmi_size.value.to_bytes(4, 'little'),
            *HUD_W.to_bytes(4, 'little'),
            *HUD_H.to_bytes(4, 'little'),
            *b'\x01\x00',
            *b'\x20\x00',
            *b'\x00'*24
        )

        ppv_bits  = ctypes.c_void_p()
        hbm = gdi32.CreateDIBSection(
            screen_dc, bmi, 0,
            ctypes.byref(ppv_bits), None, 0
        )

        if hbm:
            ctypes.memmove(ppv_bits, bgra_bytes, len(bgra_bytes))
            old_bm = gdi32.SelectObject(mem_dc, hbm)

            blend        = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
            src_pt       = POINT(0, 0)
            wnd_size     = SIZE(HUD_W, HUD_H)
            wnd_pt       = POINT(HUD_X, HUD_Y)

            user32.UpdateLayeredWindow(
                self._hwnd, screen_dc,
                ctypes.byref(wnd_pt),
                ctypes.byref(wnd_size),
                mem_dc,
                ctypes.byref(src_pt),
                0,
                ctypes.byref(blend),
                ULW_ALPHA
            )

            gdi32.SelectObject(mem_dc, old_bm)
            gdi32.DeleteObject(hbm)

        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)

    def close(self):
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)
            self._hwnd = None
        user32.UnregisterClassW("PedalTrackerHUDClass", kernel32.GetModuleHandleW(None))