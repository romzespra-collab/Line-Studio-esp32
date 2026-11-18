"""mod_images.py  v0.2.0 — картинки проекта: импорт файла, перевод в формат платы (RGB565 / RGB565A8).

Журнал:
v0.2.0: первая версия — PNG/JPG/BMP/GIF/WebP → копия в projects/<id>.assets/ (не больше 1024 px по стороне),
        под размер блока: заполнить / целиком / растянуть; прозрачность — отдельный слой альфы (RGB565A8).
"""
import os

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter

MAX_SIDE = 1024


def assets_dir(projects_dir, pid):
    return os.path.join(projects_dir, pid + ".assets")


def import_file(src, projects_dir, pid, aid):
    """Скопировать картинку в папку проекта (PNG). Вернуть (имя файла, w, h)."""
    img = QImage(src)
    if img.isNull():
        raise ValueError(f"не картинка или формат не знаком: {os.path.basename(src)}")
    if max(img.width(), img.height()) > MAX_SIDE:
        img = img.scaled(MAX_SIDE, MAX_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    d = assets_dir(projects_dir, pid)
    os.makedirs(d, exist_ok=True)
    fn = aid + ".png"
    tmp = os.path.join(d, fn + ".tmp.png")
    img.save(tmp, "PNG")
    os.replace(tmp, os.path.join(d, fn))
    return fn, img.width(), img.height()


def render(path, w, h, fit="cover"):
    """Картинка под блок w×h → (rgb565: bytes w*h*2, alpha: bytes w*h или None)."""
    src = QImage(path)
    if src.isNull() or w <= 0 or h <= 0:
        return None, None
    src = src.convertToFormat(QImage.Format_ARGB32)
    out = QImage(w, h, QImage.Format_ARGB32)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    if fit == "stretch":
        p.drawImage(QRect(0, 0, w, h), src)
    else:
        k = (max if fit == "cover" else min)(w / src.width(), h / src.height())
        sw, sh = round(src.width() * k), round(src.height() * k)
        p.drawImage(QRect((w - sw) // 2, (h - sh) // 2, sw, sh), src)
    p.end()
    has_alpha = _any_alpha(out)
    rgb = out.convertToFormat(QImage.Format_RGB16)
    data = _rows(rgb, w * 2)
    alpha = None
    if has_alpha:
        alpha = _rows(out.convertToFormat(QImage.Format_Alpha8), w)
    return data, alpha


def _rows(img, row_bytes):
    """Байты без выравнивания строк."""
    bpl = img.bytesPerLine()
    raw = bytes(img.constBits())[: bpl * img.height()]
    if bpl == row_bytes:
        return raw
    return b"".join(raw[y * bpl:y * bpl + row_bytes] for y in range(img.height()))


def _any_alpha(img):
    a = _rows(img.convertToFormat(QImage.Format_Alpha8), img.width())
    return a.count(255) != len(a)
