"""icons.py  v0.1.0 — значки LineStudio, нарисованные QPainter-ом (без эмодзи и файлов).

Журнал:
v0.1.0: первая версия — блоки (часы, дата, стрелки, текст, плашка, кнопка, дуга, ползунок), режимы
        (правка, проба, карта), действия (отмена, повтор, молния, ⋯, солнце/луна, плюс, корзина, дом, экран, плата).
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _pen(c, w):
    p = QPen(QColor(c), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    return p


def draw(p, kind, r, color):
    """Нарисовать значок kind в прямоугольнике r (QRectF)."""
    s = min(r.width(), r.height())
    x0, y0 = r.center().x() - s / 2, r.center().y() - s / 2
    k = s / 24.0
    W = max(1.4, 1.8 * k)

    def P(x, y):
        return QPointF(x0 + x * k, y0 + y * k)

    def R(x, y, w, h):
        return QRectF(x0 + x * k, y0 + y * k, w * k, h * k)
    p.setPen(_pen(color, W))
    p.setBrush(Qt.NoBrush)
    if kind == "clock":
        p.setFont(p.font())
        f = p.font()
        f.setPixelSize(int(11 * k))
        f.setBold(True)
        p.setFont(f)
        p.drawRoundedRect(R(2, 5, 20, 14), 3 * k, 3 * k)
        p.drawText(R(2, 5, 20, 14), Qt.AlignCenter, "12:00")
    elif kind == "date":
        p.drawRoundedRect(R(3, 5, 18, 16), 3 * k, 3 * k)
        p.drawLine(P(3, 10), P(21, 10))
        p.drawLine(P(8, 3), P(8, 7))
        p.drawLine(P(16, 3), P(16, 7))
        p.setBrush(QColor(color))
        p.drawEllipse(P(9, 15), 1.2 * k, 1.2 * k)
    elif kind == "analog":
        p.drawEllipse(P(12, 12), 9 * k, 9 * k)
        p.drawLine(P(12, 12), P(12, 6.5))
        p.drawLine(P(12, 12), P(16, 14))
    elif kind == "text":
        p.drawLine(P(5, 6), P(19, 6))
        p.drawLine(P(12, 6), P(12, 19))
    elif kind == "rect":
        p.drawRoundedRect(R(3, 6, 18, 12), 4 * k, 4 * k)
    elif kind == "button":
        p.drawRoundedRect(R(2, 7, 20, 10), 5 * k, 5 * k)
        p.drawLine(P(8, 12), P(16, 12))
    elif kind == "arc":
        p.drawArc(R(3, 3, 18, 18), 90 * 16, -270 * 16)
        p.setPen(_pen(QColor(color).darker(160), W))
        p.drawArc(R(3, 3, 18, 18), 90 * 16, 90 * 16)
    elif kind == "slider":
        p.drawLine(P(3, 12), P(21, 12))
        p.setBrush(QColor(color))
        p.drawEllipse(P(14, 12), 3 * k, 3 * k)
    elif kind == "edit":
        path = QPainterPath(P(4, 20))
        path.lineTo(P(5, 15))
        path.lineTo(P(16, 4))
        path.lineTo(P(20, 8))
        path.lineTo(P(9, 19))
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "try":
        path = QPainterPath(P(8, 5))
        path.lineTo(P(19, 12))
        path.lineTo(P(8, 19))
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "map":
        for (x, y) in ((3, 4), (14, 4), (14, 15)):
            p.drawRoundedRect(R(x, y, 7, 5), 1.5 * k, 1.5 * k)
        p.drawLine(P(10, 6.5), P(14, 6.5))
        p.drawLine(P(17.5, 9), P(17.5, 15))
    elif kind == "live":
        p.drawEllipse(P(12, 12), 3 * k, 3 * k)
        p.drawArc(R(5, 5, 14, 14), -45 * 16, 90 * 16)
        p.drawArc(R(5, 5, 14, 14), 135 * 16, 90 * 16)
        p.drawArc(R(1, 1, 22, 22), -40 * 16, 80 * 16)
        p.drawArc(R(1, 1, 22, 22), 140 * 16, 80 * 16)
    elif kind in ("undo", "redo"):
        sgn = 1 if kind == "redo" else -1
        cx = 12
        path = QPainterPath(P(cx - 7 * sgn, 17))
        path.cubicTo(P(cx - 7 * sgn, 9), P(cx + 6 * sgn, 7), P(cx + 7 * sgn, 11))
        p.drawPath(path)
        p.drawLine(P(cx + 7 * sgn, 11), P(cx + 7 * sgn - 0.5 * sgn, 6))
        p.drawLine(P(cx + 7 * sgn, 11), P(cx + 2 * sgn, 11.5))
    elif kind == "bolt":
        path = QPainterPath(P(13, 2))
        path.lineTo(P(5, 13))
        path.lineTo(P(11, 13))
        path.lineTo(P(10, 22))
        path.lineTo(P(19, 10))
        path.lineTo(P(13, 10))
        path.closeSubpath()
        p.setBrush(QColor(color))
        p.drawPath(path)
    elif kind == "more":
        p.setBrush(QColor(color))
        for x in (6, 12, 18):
            p.drawEllipse(P(x, 12), 1.4 * k, 1.4 * k)
    elif kind == "sun":
        p.drawEllipse(P(12, 12), 4 * k, 4 * k)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(P(12 + 7 * math.cos(a), 12 + 7 * math.sin(a)), P(12 + 9.5 * math.cos(a), 12 + 9.5 * math.sin(a)))
    elif kind == "moon":
        path = QPainterPath()
        path.addEllipse(P(12, 12), 8 * k, 8 * k)
        cut = QPainterPath()
        cut.addEllipse(P(16, 9), 7 * k, 7 * k)
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawPath(path.subtracted(cut))
    elif kind == "plus":
        p.drawLine(P(12, 5), P(12, 19))
        p.drawLine(P(5, 12), P(19, 12))
    elif kind == "trash":
        p.drawLine(P(4, 7), P(20, 7))
        p.drawRoundedRect(R(6, 7, 12, 14), 2 * k, 2 * k)
        p.drawLine(P(10, 4), P(14, 4))
    elif kind == "home":
        path = QPainterPath(P(4, 11))
        path.lineTo(P(12, 4))
        path.lineTo(P(20, 11))
        p.drawPath(path)
        p.drawRect(R(7, 11, 10, 9))
    elif kind == "screen":
        p.drawRoundedRect(R(3, 5, 18, 14), 2.5 * k, 2.5 * k)
    elif kind == "board":
        p.drawRoundedRect(R(4, 4, 16, 16), 2.5 * k, 2.5 * k)
        for i in (8, 12, 16):
            p.drawLine(P(i, 1.5), P(i, 4))
            p.drawLine(P(i, 20), P(i, 22.5))
    elif kind == "fit":
        for (a, b, c, d) in ((4, 9, 4, 4), (15, 4, 20, 4), (20, 15, 20, 20), (9, 20, 4, 20)):
            p.drawLine(P(a, b), P(c, d))
        p.drawLine(P(4, 4), P(9, 4))
        p.drawLine(P(20, 4), P(20, 9))
        p.drawLine(P(20, 20), P(15, 20))
        p.drawLine(P(4, 20), P(4, 15))
    elif kind == "save":
        p.drawRoundedRect(R(4, 4, 16, 16), 2 * k, 2 * k)
        p.drawRect(R(8, 4, 8, 5))
        p.drawRect(R(7, 13, 10, 7))


def icon(kind, color, size=24):
    ic = QIcon()
    for sz in (size, size * 2):
        pm = QPixmap(sz, sz)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        draw(p, kind, QRectF(1, 1, sz - 2, sz - 2), color)
        p.end()
        ic.addPixmap(pm)
    return ic
