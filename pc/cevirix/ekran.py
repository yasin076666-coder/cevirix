"""Windows'a özgü işler: pencere bulma, ekran yakalama, tıklama geçiren katman, kısayol tuşları."""
import ctypes
import os
import sys
import threading

WIN = sys.platform == "win32"

if WIN:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                    wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    _ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x11
HWND_TOPMOST = -1


def dpi_farkinda():
    if not WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def _exe_adi(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def istemci_alani(hwnd):
    """Pencerenin iç alanı ekran koordinatında: (x, y, g, y)."""
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    p = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(p))
    w, h = r.right - r.left, r.bottom - r.top
    if w < 200 or h < 150:
        return None
    return (p.x, p.y, w, h)


def pencere_bul(exe_adlari=("chiaki.exe", "chiaki-ng.exe"), pid=None):
    """chiaki-ng'nin görünen en büyük penceresini bulur."""
    if not WIN:
        return None
    adaylar = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if (pid and p.value == pid) or _exe_adi(p.value) in exe_adlari:
            alan = istemci_alani(hwnd)
            if alan:
                adaylar.append((alan[2] * alan[3], hwnd))
        return True

    user32.EnumWindows(_ENUMPROC(cb), 0)
    if not adaylar:
        return None
    adaylar.sort(reverse=True)
    return adaylar[0][1]


def birincil_ekran():
    if not WIN:
        return (0, 0, 1920, 1080)
    return (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def tk_hwnd(widget):
    if not WIN:
        return None
    return user32.GetAncestor(widget.winfo_id(), 2)  # GA_ROOT


def katman_yap(hwnd):
    """Tıklamayı alttaki oyuna geçirir, odak almaz, ekran yakalamaya girmez."""
    if not WIN or not hwnd:
        return
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
    try:
        user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
    except Exception:
        pass


def yakalamadan_gizle(hwnd):
    if WIN and hwnd:
        try:
            user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        except Exception:
            pass


def en_ustte(hwnd):
    if WIN and hwnd:
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)


if WIN:
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2


def pencere_goruntusu(hwnd):
    """Pencerenin iç alanını, önünde başka pencere olsa bile alır (BGR numpy dizisi).

    Simge durumundaki pencerede çalışmaz. Başarısızsa None döner.
    """
    if not WIN or not hwnd:
        return None
    import numpy as np
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    w, h = r.right - r.left, r.bottom - r.top
    if w < 50 or h < 50:
        return None
    hdc = user32.GetDC(hwnd)
    if not hdc:
        return None
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    eski = gdi32.SelectObject(mdc, bmp)
    try:
        if not user32.PrintWindow(hwnd, mdc, PW_CLIENTONLY | PW_RENDERFULLCONTENT):
            return None
        bi = _BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bi.biWidth, bi.biHeight = w, -h          # eksi: satırlar yukarıdan aşağı
        bi.biPlanes, bi.biBitCount = 1, 32
        buf = np.empty((h, w, 4), dtype=np.uint8)
        satir = gdi32.GetDIBits(mdc, bmp, 0, h, buf.ctypes.data, ctypes.byref(bi), 0)
        if satir != h:
            return None
        return buf[:, :, :3]
    finally:
        gdi32.SelectObject(mdc, eski)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(hwnd, hdc)


def islem_calisiyor(adlar=("chiaki.exe", "chiaki-ng.exe")):
    """Bu adlardan biriyle çalışan bir program var mı (penceresi simge durumunda olsa bile)."""
    if not WIN:
        return False

    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == wintypes.HANDLE(-1).value:
        return False
    try:
        pe = PE32()
        pe.dwSize = ctypes.sizeof(PE32)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            if pe.szExeFile.lower() in adlar:
                return True
            ok = kernel32.Process32NextW(snap, ctypes.byref(pe))
        return False
    finally:
        kernel32.CloseHandle(snap)


def on_planda(hwnd):
    return WIN and hwnd and user32.GetForegroundWindow() == hwnd


def one_getir(hwnd):
    """Pencereyi öne alır (simge durumundaysa geri açar)."""
    if not WIN or not hwnd:
        return
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)


class Yakalayici:
    """mss ile ekranın bir bölgesini alır (her iş parçacığı kendi örneğini kullanmalı)."""

    def __init__(self):
        import mss
        self._mss = mss.mss()

    def al(self, x, y, w, h):
        import numpy as np
        shot = self._mss.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
        img = np.asarray(shot)  # BGRA
        return img[:, :, :3]


class KisayolTuslari:
    """F8: çeviriyi başlat/durdur, F9: altyazıyı göster/gizle (oyun açıkken de çalışır)."""

    TUSLAR = {1: 0x77, 2: 0x78}  # VK_F8, VK_F9

    def __init__(self, geri_cagir):
        self.geri_cagir = geri_cagir
        if WIN:
            threading.Thread(target=self._dongu, daemon=True).start()

    def _dongu(self):
        for kid, vk in self.TUSLAR.items():
            user32.RegisterHotKey(None, kid, 0x4000, vk)  # MOD_NOREPEAT
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                try:
                    self.geri_cagir(int(msg.wParam))
                except Exception:
                    pass
