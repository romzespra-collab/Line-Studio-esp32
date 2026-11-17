"""mod_engine.py  v0.1.0 — превью: движок платы (engine/bin/line_engine.dll / .so) через ctypes.

Журнал:
v0.1.0: первая версия — кадр RGB565, касание мышью, время (живое / замороженное), рамки блоков.

Это не макет: внутри DLL тот же LVGL и тот же рантайм (runtime/ls_runtime.c), что в прошивке.
"""
import ctypes
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.path.join(ROOT, "fonts")
FONT_FILES = {"medium": "Montserrat-Medium.ttf", "bold": "Montserrat-Bold.ttf", "light": "Montserrat-Light.ttf"}


def lib_path():
    name = "line_engine.dll" if sys.platform == "win32" else "line_engine.so"
    return os.path.join(ROOT, "engine", "bin", name)


class Engine:
    def __init__(self, path=None):
        self.path = path or lib_path()
        if not os.path.exists(self.path):
            raise RuntimeError(f"нет движка превью: {self.path}")
        self.L = L = ctypes.CDLL(self.path)
        L.le_buffer.restype = ctypes.c_void_p
        for f in ("le_error", "le_log", "le_screen", "le_version"):
            getattr(L, f).restype = ctypes.c_char_p
        L.le_time.argtypes = (ctypes.c_longlong, ctypes.c_longlong)
        L.le_font.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int)
        L.le_rect.argtypes = (ctypes.c_char_p, ctypes.POINTER(ctypes.c_int))
        self.w = self.h = 0
        self._fonts = False
        self.version = L.le_version().decode()

    def init(self, w, h):
        if (w, h) == (self.w, self.h):
            return
        r = self.L.le_init(int(w), int(h))
        if r:
            raise RuntimeError(f"le_init {w}×{h}: {r}")
        self.w, self.h = w, h
        if not self._fonts:
            for name, fn in FONT_FILES.items():
                data = open(os.path.join(FONTS_DIR, fn), "rb").read()
                self.L.le_font(name.encode(), data, len(data))
            self._fonts = True

    def load(self, json_text):
        r = self.L.le_load(json_text.encode("utf-8"))
        return r, self.L.le_error().decode("utf-8", "replace")

    def log(self):
        s = self.L.le_log().decode("utf-8", "replace")
        self.L.le_log_clear()
        return [x for x in s.split("\n") if x]

    def step(self, ms):
        self.L.le_step(int(ms))

    def redraw(self):
        self.L.le_redraw()

    def frame(self):
        """Кадр: bytes длиной w*h*2 (RGB565)."""
        return ctypes.string_at(self.L.le_buffer(), self.w * self.h * 2)

    def touch(self, x, y, down):
        self.L.le_touch(int(x), int(y), 1 if down else 0)

    def set_time(self, fixed_local=0, offset=0):
        self.L.le_time(int(fixed_local), int(offset))

    def goto(self, sid):
        return self.L.le_goto(sid.encode())

    def back(self):
        return self.L.le_back()

    def screen(self):
        return self.L.le_screen().decode()

    def brightness(self):
        return self.L.le_brightness()

    def rect(self, wid):
        r = (ctypes.c_int * 4)()
        if self.L.le_rect(wid.encode(), r):
            return None
        return tuple(r)
