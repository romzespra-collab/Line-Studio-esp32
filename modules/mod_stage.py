"""mod_stage.py  v0.1.0 — холст редактора (плата с экраном из движка) и карта экранов.

Журнал:
v0.1.0: первая версия. Stage: превью из движка платы, выбор блока щелчком, перенос и ручки размера,
        прилипание к центру и краям экрана (с направляющими), стрелки (Shift — ×10), колесо — масштаб,
        средняя кнопка / пробел — сдвиг; «Проба» — мышь вместо пальца. MapView: все экраны сразу, связи
        линиями (нажатие — сплошная, свайп — пунктир), перетаскивание карточек, двойной щелчок — открыть экран.

Окно (line_studio_qt.MainWindow) даёт: project, board, cur_screen, sel, rects, engine, begin_change(),
changed(what), select(wid), open_screen(sid), mode.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import mod_project as mp

HANDLE = 7
SNAP = 6


def rgb565_image(data, w, h):
    return QImage(data, w, h, w * 2, QImage.Format_RGB16).copy()


class Stage(QWidget):
    zoomChanged = Signal(float)

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.img = None
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.fit_on_resize = True
        self._drag = None        # {"mode": move/resize/pan/touch, ...}
        self._hover = None
        self._guides = []
        self._space = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    # ---------- геометрия ----------
    def board_size(self):
        b = self.host.board
        return (b["w"], b["h"]) if b else (480, 480)

    def origin(self):
        W, H = self.board_size()
        return QPointF(self.width() / 2 - W * self.zoom / 2 + self.pan.x(),
                       self.height() / 2 - H * self.zoom / 2 + self.pan.y())

    def to_board(self, pos):
        o = self.origin()
        return (pos.x() - o.x()) / self.zoom, (pos.y() - o.y()) / self.zoom

    def to_view(self, x, y):
        o = self.origin()
        return QPointF(o.x() + x * self.zoom, o.y() + y * self.zoom)

    def fit(self):
        W, H = self.board_size()
        z = min((self.width() - 80) / W, (self.height() - 80) / H)
        self.set_zoom(max(0.1, min(4.0, z)), keep_pan=False)
        self.fit_on_resize = True

    def set_zoom(self, z, keep_pan=True, at=None):
        z = max(0.1, min(6.0, z))
        if at is not None and keep_pan:
            bx, by = self.to_board(at)
            self.zoom = z
            v = self.to_view(bx, by)
            self.pan += at - v
        else:
            self.zoom = z
            if not keep_pan:
                self.pan = QPointF(0, 0)
        self.zoomChanged.emit(self.zoom)
        self.update()

    def resizeEvent(self, ev):                         # noqa: N802 (Qt)
        if self.fit_on_resize:
            self.fit()
        super().resizeEvent(ev)

    def set_image(self, img):
        self.img = img
        self.update()

    # ---------- рисование ----------
    def paintEvent(self, ev):                          # noqa: N802 (Qt)
        from app import theme
        P = theme.P
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(P["canvas"]))
        p.setRenderHint(QPainter.Antialiasing)
        # точки
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(P["dots"]))
        step = 22
        ox = int(self.pan.x()) % step
        oy = int(self.pan.y()) % step
        for x in range(ox, self.width(), step):
            for y in range(oy, self.height(), step):
                p.drawRect(QRectF(x, y, 1.6, 1.6))
        W, H = self.board_size()
        o = self.origin()
        sr = QRectF(o.x(), o.y(), W * self.zoom, H * self.zoom)
        round_ = (self.host.board or {}).get("shape") == "round"
        # корпус платы
        bez = max(10.0, 18 * self.zoom)
        body = sr.adjusted(-bez, -bez, bez, bez)
        p.setBrush(QColor("#0b0c0f"))
        p.setPen(QPen(QColor(P["line"]), 1.2))
        if round_:
            p.drawEllipse(body)
        else:
            p.drawRoundedRect(body, bez * 1.1, bez * 1.1)
        # экран
        if self.img is not None:
            p.save()
            if round_:
                path = QPainterPath()
                path.addEllipse(sr)
                p.setClipPath(path)
            p.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom < 1.0)
            p.drawImage(sr, self.img)
            p.restore()
        if self.host.mode != "edit":
            return
        # рамки блоков
        rects = self.host.rects
        if self._hover and self._hover in rects and self._hover != self.host.sel:
            x, y, w, h = rects[self._hover]
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(P["accent"]), 1, Qt.DashLine))
            p.drawRect(QRectF(self.to_view(x, y), self.to_view(x + w, y + h)))
        if self.host.sel and self.host.sel in rects:
            x, y, w, h = rects[self.host.sel]
            r = QRectF(self.to_view(x, y), self.to_view(x + w, y + h))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(P["accent"]), 1.5))
            p.drawRect(r)
            p.setBrush(QColor("#ffffff"))
            p.setPen(QPen(QColor(P["accent"]), 1.5))
            for hx, hy, _ in self._handles(r):
                p.drawRect(QRectF(hx - HANDLE / 2, hy - HANDLE / 2, HANDLE, HANDLE))
            # размер
            _, wd = mp.find_widget(self.host.project, self.host.sel)
            if wd:
                f = QFont(self.font())
                f.setPointSizeF(8)
                p.setFont(f)
                p.setPen(QColor(P["muted"]))
                p.drawText(QRectF(r.left(), r.bottom() + 4, 220, 16), Qt.AlignLeft,
                           f"{wd['x']}, {wd['y']}   {w}×{h}")
        for g in self._guides:
            p.setPen(QPen(QColor("#ff4fa3"), 1, Qt.DashLine))
            if g[0] == "v":
                v = self.to_view(g[1], 0).x()
                p.drawLine(QPointF(v, sr.top() - 20), QPointF(v, sr.bottom() + 20))
            else:
                v = self.to_view(0, g[1]).y()
                p.drawLine(QPointF(sr.left() - 20, v), QPointF(sr.right() + 20, v))

    def _handles(self, r):
        """Ручки: (x, y, код) — код: 'l','r','t','b' и углы."""
        _, wd = mp.find_widget(self.host.project, self.host.sel)
        auto_h = wd is not None and wd.get("h", 0) == 0
        hs = [(r.left(), r.center().y(), "l"), (r.right(), r.center().y(), "r")]
        if not auto_h:
            hs += [(r.center().x(), r.top(), "t"), (r.center().x(), r.bottom(), "b"),
                   (r.left(), r.top(), "tl"), (r.right(), r.top(), "tr"),
                   (r.left(), r.bottom(), "bl"), (r.right(), r.bottom(), "br")]
        return hs

    # ---------- мышь ----------
    def hit(self, pos):
        bx, by = self.to_board(pos)
        scr = mp.find_screen(self.host.project, self.host.cur_screen)
        if not scr:
            return None
        for w in reversed(scr["widgets"]):
            r = self.host.rects.get(w["id"])
            if not r or w.get("hidden"):
                continue
            x, y, ww, hh = r
            if x <= bx <= x + ww and y <= by <= y + hh:
                return w["id"]
        return None

    def _handle_at(self, pos):
        if not self.host.sel or self.host.sel not in self.host.rects:
            return None
        x, y, w, h = self.host.rects[self.host.sel]
        r = QRectF(self.to_view(x, y), self.to_view(x + w, y + h))
        for hx, hy, code in self._handles(r):
            if abs(pos.x() - hx) <= HANDLE and abs(pos.y() - hy) <= HANDLE:
                return code
        return None

    def mousePressEvent(self, ev):                     # noqa: N802 (Qt)
        self.setFocus()
        pos = ev.position()
        if ev.button() == Qt.MiddleButton or (ev.button() == Qt.LeftButton and self._space):
            self._drag = {"mode": "pan", "start": pos, "pan": QPointF(self.pan)}
            self.setCursor(Qt.ClosedHandCursor)
            return
        if ev.button() != Qt.LeftButton:
            return
        if self.host.mode == "try":
            bx, by = self.to_board(pos)
            self.host.engine_touch(bx, by, True)
            self._drag = {"mode": "touch"}
            return
        code = self._handle_at(pos)
        if code:
            _, wd = mp.find_widget(self.host.project, self.host.sel)
            self.host.begin_change()
            x, y, w, h = self.host.rects[self.host.sel]
            self._drag = {"mode": "resize", "code": code, "start": pos, "geo": (wd["x"], wd["y"], w, h), "w": wd}
            return
        wid = self.hit(pos)
        self.host.select(wid)
        if wid:
            _, wd = mp.find_widget(self.host.project, wid)
            self._drag = {"mode": "move", "start": pos, "geo": (wd["x"], wd["y"]), "w": wd, "moved": False,
                          "rect": self.host.rects.get(wid)}

    def mouseMoveEvent(self, ev):                      # noqa: N802 (Qt)
        pos = ev.position()
        d = self._drag
        if not d:
            if self.host.mode == "edit":
                h = self.hit(pos)
                code = self._handle_at(pos)
                self.setCursor(Qt.SizeAllCursor if code else Qt.PointingHandCursor if h else Qt.ArrowCursor)
                if h != self._hover:
                    self._hover = h
                    self.update()
            elif self.host.mode == "try":
                self.setCursor(Qt.PointingHandCursor)
            return
        if d["mode"] == "pan":
            self.pan = d["pan"] + (pos - d["start"])
            self.fit_on_resize = False
            self.update()
            return
        if d["mode"] == "touch":
            bx, by = self.to_board(pos)
            self.host.engine_touch(bx, by, True)
            return
        dx = (pos.x() - d["start"].x()) / self.zoom
        dy = (pos.y() - d["start"].y()) / self.zoom
        w = d["w"]
        W, H = self.board_size()
        self._guides = []
        if d["mode"] == "move":
            if not d["moved"]:
                if abs(dx) * self.zoom < 3 and abs(dy) * self.zoom < 3:
                    return
                self.host.begin_change()
                d["moved"] = True
            if ev.modifiers() & Qt.ShiftModifier:
                if abs(dx) > abs(dy):
                    dy = 0
                else:
                    dx = 0
            nx, ny = d["geo"][0] + dx, d["geo"][1] + dy
            r = d["rect"] or (w["x"], w["y"], w["w"], w["h"])
            rw, rh = r[2], r[3]
            if not (ev.modifiers() & Qt.AltModifier):
                th = SNAP / self.zoom
                for target, kind in ((W / 2, "c"), (0, "s"), (W, "e")):
                    edge = nx + rw / 2 if kind == "c" else nx if kind == "s" else nx + rw
                    if abs(edge - target) < th:
                        nx += target - edge
                        self._guides.append(("v", target))
                        break
                for target, kind in ((H / 2, "c"), (0, "s"), (H, "e")):
                    edge = ny + rh / 2 if kind == "c" else ny if kind == "s" else ny + rh
                    if abs(edge - target) < th:
                        ny += target - edge
                        self._guides.append(("h", target))
                        break
            w["x"], w["y"] = int(round(nx)), int(round(ny))
        else:
            x0, y0, w0, h0 = d["geo"]
            c = d["code"]
            x, y, ww, hh = x0, y0, w0, h0
            if "l" in c:
                x, ww = x0 + dx, w0 - dx
            if "r" in c:
                ww = w0 + dx
            if "t" in c:
                y, hh = y0 + dy, h0 - dy
            if "b" in c:
                hh = h0 + dy
            ww, hh = max(4, ww), max(4, hh)
            if mp.CATALOG.get(w["type"], {}).get("square") or ev.modifiers() & Qt.ShiftModifier:
                if w.get("h", 0):
                    s = max(ww, hh)
                    ww = hh = s
            w["x"], w["y"], w["w"] = int(round(x)), int(round(y)), int(round(ww))
            if w.get("h", 0):
                w["h"] = int(round(hh))
        self.host.changed("geom")

    def mouseReleaseEvent(self, ev):                   # noqa: N802 (Qt)
        d = self._drag
        self._drag = None
        self._guides = []
        self.setCursor(Qt.ArrowCursor)
        if d and d["mode"] == "touch":
            bx, by = self.to_board(ev.position())
            self.host.engine_touch(bx, by, False)
        elif d and d["mode"] in ("move", "resize") and (d["mode"] == "resize" or d.get("moved")):
            self.host.changed("geom-done")
        self.update()

    def mouseDoubleClickEvent(self, ev):               # noqa: N802 (Qt)
        if self.host.mode == "edit" and self.host.sel:
            self.host.focus_prop("text")

    def wheelEvent(self, ev):                          # noqa: N802 (Qt)
        k = 1.12 if ev.angleDelta().y() > 0 else 1 / 1.12
        self.fit_on_resize = False
        self.set_zoom(self.zoom * k, at=ev.position())

    def keyPressEvent(self, ev):                       # noqa: N802 (Qt)
        if ev.key() == Qt.Key_Space and not ev.isAutoRepeat():
            self._space = True
            self.setCursor(Qt.OpenHandCursor)
            return
        if self.host.mode == "edit" and self.host.sel and ev.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up,
                                                                       Qt.Key_Down):
            n = 10 if ev.modifiers() & Qt.ShiftModifier else 1
            dx = {Qt.Key_Left: -n, Qt.Key_Right: n}.get(ev.key(), 0)
            dy = {Qt.Key_Up: -n, Qt.Key_Down: n}.get(ev.key(), 0)
            _, w = mp.find_widget(self.host.project, self.host.sel)
            if w:
                self.host.begin_change()
                w["x"] += dx
                w["y"] += dy
                self.host.changed("geom-done")
            return
        if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.host.mode == "edit":
            self.host.delete_selected()
            return
        super().keyPressEvent(ev)

    def keyReleaseEvent(self, ev):                     # noqa: N802 (Qt)
        if ev.key() == Qt.Key_Space and not ev.isAutoRepeat():
            self._space = False
            self.setCursor(Qt.ArrowCursor)
            return
        super().keyReleaseEvent(ev)

    def leaveEvent(self, ev):                          # noqa: N802 (Qt)
        self._hover = None
        self.update()


class MapView(QWidget):
    """Карта: все экраны сразу, связи линиями."""

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.thumbs = {}         # sid → QImage
        self.zoom = 1.0
        self.pan = QPointF(40, 40)
        self._drag = None
        self.setMouseTracking(True)
        self.setMinimumSize(320, 240)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self._fit_done = False

    def card_size(self):
        W, H = (self.host.board["w"], self.host.board["h"]) if self.host.board else (480, 480)
        k = 170.0 / max(W, H)
        return W * k, H * k, k

    def positions(self):
        """Где карточки (в координатах карты): сохранённые в project['map'] или раскладка по глубине от главного."""
        p = self.host.project
        cw, ch, _ = self.card_size()
        gx, gy = cw + 110, ch + 70
        saved = p.get("map") or {}
        ids = [s["id"] for s in p["screens"]]
        depth = {p.get("home", ids[0]): 0}
        order = [p.get("home", ids[0])]
        edges = {}
        for a, _, b, _ in mp.links(p):
            edges.setdefault(a, []).append(b)
        i = 0
        while i < len(order):
            for b in edges.get(order[i], []):
                if b not in depth:
                    depth[b] = depth[order[i]] + 1
                    order.append(b)
            i += 1
        maxd = max(depth.values()) if depth else 0
        for s in ids:
            if s not in depth:
                maxd += 0
                depth[s] = maxd + 1
                order.append(s)
        rows = {}
        pos = {}
        for s in order:
            d = depth[s]
            r = rows.get(d, 0)
            rows[d] = r + 1
            pos[s] = QPointF(d * gx, r * gy)
        for s, xy in saved.items():
            if s in pos and isinstance(xy, (list, tuple)) and len(xy) == 2:
                pos[s] = QPointF(xy[0], xy[1])
        return pos

    def to_view(self, pt):
        return QPointF(self.pan.x() + pt.x() * self.zoom, self.pan.y() + pt.y() * self.zoom)

    def to_map(self, pos):
        return QPointF((pos.x() - self.pan.x()) / self.zoom, (pos.y() - self.pan.y()) / self.zoom)

    def fit(self):
        pos = self.positions()
        if not pos:
            return
        cw, ch, _ = self.card_size()
        xs = [p.x() for p in pos.values()]
        ys = [p.y() for p in pos.values()]
        w = max(xs) - min(xs) + cw + 80
        h = max(ys) - min(ys) + ch + 100
        self.zoom = max(0.2, min(1.6, min(self.width() / w, self.height() / h)))
        self.pan = QPointF(-min(xs) * self.zoom + (self.width() - (w - 80) * self.zoom) / 2,
                           -min(ys) * self.zoom + (self.height() - (h - 100) * self.zoom) / 2 + 20)
        self.update()

    def card_at(self, pos):
        cw, ch, _ = self.card_size()
        m = self.to_map(pos)
        for sid, pt in reversed(list(self.positions().items())):
            if QRectF(pt.x(), pt.y(), cw, ch).contains(m):
                return sid
        return None

    def paintEvent(self, ev):                          # noqa: N802 (Qt)
        from app import theme
        P = theme.P
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(P["canvas"]))
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if not self._fit_done and self.width() > 100:
            self._fit_done = True
            self.fit()
        pos = self.positions()
        cw, ch, k = self.card_size()
        round_ = (self.host.board or {}).get("shape") == "round"
        z = self.zoom

        def rect_of(sid):
            pt = self.to_view(pos[sid])
            return QRectF(pt.x(), pt.y(), cw * z, ch * z)
        # связи
        for a, wid, b, kind in mp.links(self.host.project):
            if a not in pos or b not in pos:
                continue
            ra, rb = rect_of(a), rect_of(b)
            if wid and wid in self.host.all_rects.get(a, {}):
                x, y, w, h = self.host.all_rects[a][wid]
                start = QPointF(ra.left() + (x + w / 2) * k * z, ra.top() + (y + h / 2) * k * z)
            else:
                start = QPointF(ra.right(), ra.center().y()) if rb.center().x() >= ra.center().x() else \
                    QPointF(ra.left(), ra.center().y())
            end = QPointF(rb.left(), rb.center().y()) if rb.center().x() >= start.x() else QPointF(rb.right(), rb.center().y())
            if abs(rb.center().x() - ra.center().x()) < cw * z * 0.5:
                end = QPointF(rb.center().x(), rb.top() if rb.center().y() > ra.center().y() else rb.bottom())
            col = QColor(P["accent"]) if kind == "tap" else QColor(P["muted"])
            pen = QPen(col, 1.8 if kind == "tap" else 1.4, Qt.SolidLine if kind == "tap" else Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            dxm = max(40.0, abs(end.x() - start.x()) / 2)
            path = QPainterPath(start)
            sgn = 1 if end.x() >= start.x() else -1
            path.cubicTo(QPointF(start.x() + dxm * sgn, start.y()), QPointF(end.x() - dxm * sgn, end.y()), end)
            p.drawPath(path)
            p.setBrush(col)
            p.setPen(Qt.NoPen)
            p.drawEllipse(start, 3.2, 3.2)
            ang = math.atan2(end.y() - path.pointAtPercent(0.97).y(), end.x() - path.pointAtPercent(0.97).x())
            tri = QPainterPath(end)
            tri.lineTo(end - QPointF(9 * math.cos(ang - 0.45), 9 * math.sin(ang - 0.45)))
            tri.lineTo(end - QPointF(9 * math.cos(ang + 0.45), 9 * math.sin(ang + 0.45)))
            tri.closeSubpath()
            p.drawPath(tri)
            if kind != "tap":
                mid = path.pointAtPercent(0.5)
                p.setPen(QColor(P["muted"]))
                f = QFont(self.font())
                f.setPointSizeF(7.5)
                p.setFont(f)
                arrow = {"swipe-left": "свайп ←", "swipe-right": "свайп →", "swipe-up": "свайп ↑",
                         "swipe-down": "свайп ↓"}.get(kind, kind)
                p.drawText(QRectF(mid.x() - 40, mid.y() - 16, 80, 14), Qt.AlignCenter, arrow)
        # карточки
        f = QFont(self.font())
        f.setPointSizeF(9)
        f.setBold(True)
        for s in self.host.project["screens"]:
            sid = s["id"]
            r = rect_of(sid)
            p.setFont(f)
            p.setPen(QColor(P["text"]))
            title = ("⌂ " if sid == self.host.project.get("home") else "") + s["name"]
            p.drawText(QRectF(r.left(), r.top() - 22, max(r.width(), 200), 18), Qt.AlignLeft | Qt.AlignVCenter, title)
            p.setPen(QPen(QColor(P["accent"]) if sid == self.host.cur_screen else QColor(P["line"]),
                          2.2 if sid == self.host.cur_screen else 1))
            p.setBrush(QColor("#000000"))
            img = self.thumbs.get(sid)
            if round_:
                p.drawEllipse(r.adjusted(-3, -3, 3, 3))
            else:
                p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 6, 6)
            if img is not None:
                p.save()
                if round_:
                    clip = QPainterPath()
                    clip.addEllipse(r)
                    p.setClipPath(clip)
                p.drawImage(r, img)
                p.restore()

    def mousePressEvent(self, ev):                     # noqa: N802 (Qt)
        pos = ev.position()
        sid = self.card_at(pos) if ev.button() == Qt.LeftButton else None
        if sid:
            self.host.open_screen(sid, switch=False)
            pt = self.positions()[sid]
            self._drag = {"mode": "card", "sid": sid, "start": pos, "pt": QPointF(pt), "moved": False}
        elif ev.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._drag = {"mode": "pan", "start": pos, "pan": QPointF(self.pan)}
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, ev):                      # noqa: N802 (Qt)
        d = self._drag
        pos = ev.position()
        if not d:
            self.setCursor(Qt.PointingHandCursor if self.card_at(pos) else Qt.ArrowCursor)
            return
        if d["mode"] == "pan":
            self.pan = d["pan"] + (pos - d["start"])
        else:
            delta = (pos - d["start"]) / self.zoom
            if not d["moved"] and abs(delta.x()) + abs(delta.y()) < 4:
                return
            if not d["moved"]:
                self.host.begin_change()
                d["moved"] = True
                pos_all = self.positions()
                self.host.project["map"] = {k: [round(v.x()), round(v.y())] for k, v in pos_all.items()}
            np_ = d["pt"] + delta
            self.host.project["map"][d["sid"]] = [round(np_.x()), round(np_.y())]
        self.update()

    def mouseReleaseEvent(self, ev):                   # noqa: N802 (Qt)
        d = self._drag
        self._drag = None
        self.setCursor(Qt.ArrowCursor)
        if d and d["mode"] == "card" and d["moved"]:
            self.host.changed("map")

    def mouseDoubleClickEvent(self, ev):               # noqa: N802 (Qt)
        sid = self.card_at(ev.position())
        if sid:
            self.host.open_screen(sid, switch=True)

    def wheelEvent(self, ev):                          # noqa: N802 (Qt)
        k = 1.12 if ev.angleDelta().y() > 0 else 1 / 1.12
        at = ev.position()
        m = self.to_map(at)
        self.zoom = max(0.15, min(3.0, self.zoom * k))
        self.pan = QPointF(at.x() - m.x() * self.zoom, at.y() - m.y() * self.zoom)
        self.update()


_ = QTimer  # (импорт для окна)
