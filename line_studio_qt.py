"""line_studio_qt.py  v0.1.0 — окно LineStudio (Вид 2 «Пульт», холст в центре — как PinFlow_esp32).

Журнал:
v0.1.0: первая версия — своя рамка, шапка (значок, проект, чип, Правка/Проба/Карта, Live, отмена/повтор,
        масштаб, плата, ☀/☾, ⋯, «Залить»), плитки-счётчики, слева «Добавить» / экраны / слои, в центре холст или
        карта, справа свойства, внизу журнал и прогресс. F5 — перерисовать, Esc — «Стоп», Ctrl+S, Ctrl+T,
        Ctrl+Z/Y, Ctrl+D, Delete. Настройки и проект сохраняются сами (раз в 10 с и при закрытии).
"""
import copy
import json
import os
import subprocess
import sys
import threading
import time

from PySide6.QtCore import QByteArray, QEvent, QObject, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QFont, QKeySequence, QPainter, QShortcut,
                           QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSplitter,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

import line_studio as core
from app import icons, theme
from app.int_field import IntField
from app.window_frame import WindowFrame
from modules import mod_build as mb
from modules import mod_link as ml
from modules import mod_project as mp
from modules.mod_engine import Engine
from modules.mod_stage import MapView, Stage, rgb565_image

log = core.log


# ---------- мелкие виджеты ----------
def card(title=None):
    f = QFrame()
    f.setObjectName("card")
    v = QVBoxLayout(f)
    v.setContentsMargins(12, 10, 12, 12)
    v.setSpacing(8)
    head = None
    if title:
        head = QHBoxLayout()
        head.setSpacing(6)
        lb = QLabel(title.upper())
        lb.setObjectName("cardTitle")
        head.addWidget(lb)
        head.addStretch(1)
        v.addLayout(head)
        f.title_label = lb
    f.head = head
    f.body = v
    return f


def lab(text, name=None):
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    return lb


class Dot(QLabel):
    COLORS = {"none": "#5c6372", "green": theme.OK, "blue": "#4f8cff", "yellow": theme.WARN, "red": theme.ERR}

    def __init__(self):
        super().__init__("●")
        self.set("none")

    def set(self, state, tip=""):
        self.setStyleSheet(f"color: {self.COLORS.get(state, '#5c6372')}; font-size: 12pt; background: transparent;")
        if tip:
            self.setToolTip(tip)


class ColorButton(QPushButton):
    def __init__(self, value, on_change, allow_empty=False):
        super().__init__()
        self.value = value or ""
        self.on_change = on_change
        self.allow_empty = allow_empty
        self.setMinimumWidth(90)
        self.clicked.connect(self.pick)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menu)
        self._paint()

    def _paint(self):
        v = self.value
        self.setText(v.upper() if v else "нет")
        if v:
            fg = "#000000" if QColor(v).lightness() > 140 else "#ffffff"
            self.setStyleSheet(f"QPushButton {{ background: {v}; color: {fg}; border: 1px solid {theme.P['line']}; }}")
        else:
            self.setStyleSheet("")

    def pick(self):
        c = QColorDialog.getColor(QColor(self.value or "#ffffff"), self, "Цвет")
        if c.isValid():
            self.value = c.name().upper()
            self._paint()
            self.on_change(self.value)

    def menu(self, pos):
        m = QMenu(self)
        m.addAction("Выбрать цвет…", self.pick)
        m.addAction("Копировать", lambda: QApplication.clipboard().setText(self.value))
        if QColor(QApplication.clipboard().text().strip()).isValid():
            m.addAction("Вставить", lambda: self.set_value(QColor(QApplication.clipboard().text().strip()).name().upper()))
        if self.allow_empty:
            m.addAction("Убрать", lambda: self.set_value(""))
        m.exec(self.mapToGlobal(pos))

    def set_value(self, v):
        self.value = v
        self._paint()
        self.on_change(v)


class Segmented(QWidget):
    def __init__(self, items, on_change):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.btns = {}
        self.on_change = on_change
        for i, (key, text, ic) in enumerate(items):
            b = QToolButton()
            b.setText(text)
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setObjectName("segFirst" if i == 0 else "segLast" if i == len(items) - 1 else "seg")
            b.setProperty("ic", ic)
            b.clicked.connect(lambda _=False, k=key: self.set(k, True))
            h.addWidget(b)
            self.btns[key] = b
        self.key = None

    def set(self, key, emit=False):
        self.key = key
        for k, b in self.btns.items():
            b.setChecked(k == key)
        if emit:
            self.on_change(key)

    def recolor(self):
        for b in self.btns.values():
            b.setIcon(icons.icon(b.property("ic"), theme.P["text"], 16))


# ---------- окно ----------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = core.load_config()
        self.secrets = core.load_secrets()
        self.boards = mb.load_boards()
        self.engine = None
        self.project = None
        self.pid = ""
        self.board = None
        self.cur_screen = None
        self.sel = None
        self.rects = {}
        self.all_rects = {}
        self.mode = "edit"
        self.hist = mp.History()
        self._last_change = (None, 0.0)
        self._dirty_save = False
        self._dirty_engine = True
        self._dirty_thumbs = True
        self.busy = None              # имя работы
        self.cancel = False
        self.worker = None
        self.link = None              # Live
        self.port_state = {}          # порт → {"hello":…, "boards":[…]}
        self.ports = []
        self.last_build = ""
        self._live_due = 0.0
        self._scanning = False
        self.setObjectName("root")
        self.setWindowTitle(f"{core.APP_NAME} — v{core.VERSION} · Qt6")
        self.setWindowIcon(theme.app_icon())
        self.resize(1440, 900)
        self._build_ui()
        self.frame = WindowFrame(self, self.title_bar, self.title_buttons)
        self._apply_theme(self.cfg.get("theme", "dark"))
        self._init_engine()
        self._open_last_project()
        self._restore_geometry()
        # таймеры
        self.t_log = QTimer(self, interval=150, timeout=self._drain)
        self.t_log.start()
        self.t_render = QTimer(self, singleShot=True, interval=30, timeout=self.render)
        self.t_clock = QTimer(self, interval=1000, timeout=self._clock_tick)
        self.t_clock.start()
        self.t_try = QTimer(self, interval=33, timeout=self._try_tick)
        self.t_save = QTimer(self, interval=10000, timeout=self._autosave)
        self.t_save.start()
        self.t_ports = QTimer(self, interval=2000, timeout=self._scan_ports)
        self.t_ports.start()
        self.t_live = QTimer(self, interval=120, timeout=self._live_tick)
        self.t_live.start()
        self._shortcuts()
        QTimer.singleShot(300, self._scan_ports)
        log.info(f"✓ {core.APP_NAME} v{core.VERSION}: движок превью {self.engine.version if self.engine else '—'}, "
                 f"плат: {len(self.boards)}")

    # ---------- интерфейс ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        # своя полоса заголовка
        self.title_bar = QFrame()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(32)
        tb = QHBoxLayout(self.title_bar)
        tb.setContentsMargins(10, 0, 0, 0)
        tb.setSpacing(8)
        self.title_icon = QLabel()
        self.title_icon.setPixmap(theme.icon_pixmap(18))
        self.title_icon.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.title_text = QLabel(f"{core.APP_NAME} — v{core.VERSION}")
        self.title_text.setObjectName("appTitle")
        self.title_text.setAttribute(Qt.WA_TransparentForMouseEvents)
        tb.addWidget(self.title_icon)
        tb.addWidget(self.title_text)
        tb.addStretch(1)
        self.title_buttons = tb
        root.addWidget(self.title_bar)

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(12, 10, 12, 8)
        bv.setSpacing(10)
        root.addWidget(body, 1)

        # шапка
        head = QFrame()
        head.setObjectName("header")
        hh = QHBoxLayout(head)
        hh.setContentsMargins(12, 8, 12, 8)
        hh.setSpacing(8)
        self.h_icon = QLabel()
        self.h_icon.setPixmap(theme.icon_pixmap(30))
        hh.addWidget(self.h_icon)
        tv = QVBoxLayout()
        tv.setSpacing(0)
        self.h_title = lab(core.APP_NAME, "big")
        self.h_proj = QPushButton("Проект")
        self.h_proj.setObjectName("chip")
        self.h_proj.setToolTip("Проект — щелчок: переименовать; правый щелчок: проекты")
        self.h_proj.clicked.connect(self.rename_project)
        self.h_proj.setContextMenuPolicy(Qt.CustomContextMenu)
        self.h_proj.customContextMenuRequested.connect(lambda p: self.projects_menu().exec(self.h_proj.mapToGlobal(p)))
        tv.addWidget(self.h_title)
        hh.addLayout(tv)
        hh.addWidget(self.h_proj)
        self.pill = lab("● готов", "pill")
        hh.addWidget(self.pill)
        hh.addSpacing(10)
        self.b_undo = self._tool("undo", "Отменить (Ctrl+Z)", self.undo)
        self.b_redo = self._tool("redo", "Повторить (Ctrl+Y)", self.redo)
        hh.addWidget(self.b_undo)
        hh.addWidget(self.b_redo)
        self.seg = Segmented([("edit", "Правка", "edit"), ("try", "Проба", "try"), ("map", "Карта", "map")],
                             self.set_mode)
        self.seg.setToolTip("Правка — двигать и красить; Проба — пользоваться экраном мышью; Карта — все экраны и связи")
        hh.addWidget(self.seg)
        self.b_live = QToolButton()
        self.b_live.setText("Live")
        self.b_live.setCheckable(True)
        self.b_live.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_live.setToolTip("Live: плата на USB — правки видны на ней сразу, без заливки")
        self.b_live.toggled.connect(self.toggle_live)
        hh.addWidget(self.b_live)
        hh.addSpacing(6)
        self.b_zout = self._tool(None, "Мельче", lambda: self.zoom_by(1 / 1.2), "−")
        self.l_zoom = QPushButton("100%")
        self.l_zoom.setObjectName("chip")
        self.l_zoom.setToolTip("Вписать в окно")
        self.l_zoom.clicked.connect(self.fit)
        self.b_zin = self._tool(None, "Крупнее", lambda: self.zoom_by(1.2), "+")
        for b in (self.b_zout, self.l_zoom, self.b_zin):
            hh.addWidget(b)
        hh.addStretch(1)
        self.dot = Dot()
        self.b_board = QToolButton()
        self.b_board.setObjectName("chip")
        self.b_board.setPopupMode(QToolButton.InstantPopup)
        self.b_board.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.b_board.setToolTip("Плата проекта и порт USB")
        self.b_board.setMenu(QMenu(self.b_board))
        self.b_board.menu().aboutToShow.connect(self._fill_board_menu)
        hh.addWidget(self.dot)
        hh.addWidget(self.b_board)
        self.b_theme = self._tool("sun", "Тема: светлая / тёмная (Ctrl+T)", self.toggle_theme)
        hh.addWidget(self.b_theme)
        self.b_more = self._tool("more", "Ещё", None)
        self.b_more.setPopupMode(QToolButton.InstantPopup)
        self.b_more.setMenu(QMenu(self.b_more))
        self.b_more.menu().aboutToShow.connect(lambda: self._fill_more_menu(self.b_more.menu()))
        hh.addWidget(self.b_more)
        self.b_load = QPushButton("  Залить")
        self.b_load.setObjectName("primary")
        self.b_load.setToolTip("Собрать прошивку из проекта и залить в плату по USB")
        self.b_load.clicked.connect(self.load_to_board)
        hh.addWidget(self.b_load)
        bv.addWidget(head)

        # плитки
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tiles = {}
        for key, cap in (("screens", "ЭКРАНЫ"), ("widgets", "БЛОКИ"), ("board", "ПЛАТА"), ("build", "ПРОШИВКА")):
            f = QFrame()
            f.setObjectName("tile")
            v = QVBoxLayout(f)
            v.setContentsMargins(12, 6, 12, 6)
            v.setSpacing(0)
            c = lab(cap, "tileCap")
            val = lab("—", "tileVal")
            v.addWidget(c)
            v.addWidget(val)
            tiles.addWidget(f, 1)
            self.tiles[key] = val
        bv.addLayout(tiles)

        # середина: слева — справа
        self.vsplit = QSplitter(Qt.Vertical)
        self.split = QSplitter(Qt.Horizontal)
        self.split.setChildrenCollapsible(False)
        left = self._build_left()
        self.center = QStackedWidget()
        self.stage = Stage(self)
        self.stage.zoomChanged.connect(lambda z: self.l_zoom.setText(f"{round(z * 100)}%"))
        self.stage.customContextMenuRequested.connect(self._stage_menu)
        self.mapv = MapView(self)
        self.mapv.customContextMenuRequested.connect(self._map_menu)
        cw = QFrame()
        cw.setObjectName("card")
        cl = QVBoxLayout(cw)
        cl.setContentsMargins(1, 1, 1, 1)
        self.center.addWidget(self.stage)
        self.center.addWidget(self.mapv)
        self.scr_bar = QHBoxLayout()
        self.scr_bar.setContentsMargins(10, 6, 10, 0)
        self.b_prev = self._tool(None, "Предыдущий экран", lambda: self.step_screen(-1), "‹")
        self.l_scr = lab("Экран", "muted")
        self.l_scr.setAlignment(Qt.AlignCenter)
        self.b_next = self._tool(None, "Следующий экран", lambda: self.step_screen(1), "›")
        self.scr_bar.addStretch(1)
        self.scr_bar.addWidget(self.b_prev)
        self.scr_bar.addWidget(self.l_scr)
        self.scr_bar.addWidget(self.b_next)
        self.scr_bar.addStretch(1)
        cl.addLayout(self.scr_bar)
        cl.addWidget(self.center, 1)
        right = self._build_right()
        self.split.addWidget(left)
        self.split.addWidget(cw)
        self.split.addWidget(right)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([300, 820, 330])
        self.vsplit.addWidget(self.split)
        # журнал
        lc = card("Журнал")
        self.logw = QPlainTextEdit()
        self.logw.setObjectName("log")
        self.logw.setReadOnly(True)
        self.logw.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.logw.setMaximumBlockCount(3000)
        self.logw.setContextMenuPolicy(Qt.CustomContextMenu)
        self.logw.customContextMenuRequested.connect(self._log_menu)
        lc.body.addWidget(self.logw)
        self.vsplit.addWidget(lc)
        self.vsplit.setSizes([700, 150])
        bv.addWidget(self.vsplit, 1)
        # строка состояния
        sb = QFrame()
        sb.setObjectName("statusbar")
        sb.setFixedHeight(30)
        sh = QHBoxLayout(sb)
        sh.setContentsMargins(12, 0, 12, 0)
        self.s_pill = lab("● готов", "muted")
        self.progress = QProgressBar()
        self.progress.setFixedWidth(260)
        self.progress.setRange(0, 100)
        self.progress.hide()
        self.b_stop = QPushButton("Стоп")
        self.b_stop.setObjectName("chip")
        self.b_stop.setToolTip("Остановить (Esc)")
        self.b_stop.clicked.connect(self.stop)
        self.b_stop.hide()
        self.s_text = lab("", "muted")
        sh.addWidget(self.s_pill)
        sh.addWidget(self.progress)
        sh.addWidget(self.b_stop)
        sh.addStretch(1)
        sh.addWidget(self.s_text)
        root.addWidget(sb)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda p: self._fill_more_menu(QMenu(self)).exec(self.mapToGlobal(p)))

    def _tool(self, ic, tip, slot, text=None):
        b = QToolButton()
        if text:
            b.setText(text)
        b.setProperty("ic", ic)
        b.setToolTip(tip)
        b.setIconSize(QSize(18, 18))
        if slot:
            b.clicked.connect(slot)
        return b

    def _build_left(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        # добавить
        add = card("Добавить")
        grid = QGridLayout()
        grid.setSpacing(6)
        self.add_btns = []
        i = 0
        for kind, c in mp.CATALOG.items():
            b = QToolButton()
            b.setObjectName("add")
            b.setText(c["name"])
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(22, 22))
            b.setProperty("ic", c["icon"])
            b.setToolTip(f"{c['name']} — {c['group']}. Добавить на экран")
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, k=kind: self.add_widget(k))
            grid.addWidget(b, i // 4, i % 4)
            self.add_btns.append(b)
            i += 1
        add.body.addLayout(grid)
        v.addWidget(add)
        # экраны
        sc = card("Экраны")
        b_new = QToolButton()
        b_new.setText("+ Новый")
        b_new.setObjectName("chip")
        b_new.setPopupMode(QToolButton.InstantPopup)
        mnew = QMenu(b_new)
        for key, name, _fn in mp.TEMPLATES:
            mnew.addAction(name, lambda k=key: self.add_screen(k))
        b_new.setMenu(mnew)
        sc.head.addWidget(b_new)
        self.l_screens = QListWidget()
        self.l_screens.setContextMenuPolicy(Qt.CustomContextMenu)
        self.l_screens.customContextMenuRequested.connect(self._screens_menu)
        self.l_screens.currentRowChanged.connect(self._screen_row)
        self.l_screens.itemDoubleClicked.connect(lambda it: self.rename_screen())
        self.l_screens.setMinimumHeight(110)
        sc.body.addWidget(self.l_screens)
        v.addWidget(sc, 2)
        # слои
        lc = card("Слои")
        self.layers_card = lc
        self.l_layers = QListWidget()
        self.l_layers.setDragDropMode(QAbstractItemView.InternalMove)
        self.l_layers.setContextMenuPolicy(Qt.CustomContextMenu)
        self.l_layers.customContextMenuRequested.connect(self._layers_menu)
        self.l_layers.currentRowChanged.connect(self._layer_row)
        self.l_layers.model().rowsMoved.connect(self._layers_moved)
        lc.body.addWidget(self.l_layers)
        v.addWidget(lc, 3)
        w.setMinimumWidth(270)
        return w

    def _build_right(self):
        c = card("Свойства")
        self.props_card = c
        self.props_scroll = QScrollArea()
        self.props_scroll.setWidgetResizable(True)
        self.props_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.props_host = QWidget()
        self.props_form = QVBoxLayout(self.props_host)
        self.props_form.setContentsMargins(0, 0, 4, 0)
        self.props_form.setSpacing(10)
        self.props_scroll.setWidget(self.props_host)
        c.body.addWidget(self.props_scroll)
        c.setMinimumWidth(300)
        return c

    def _shortcuts(self):
        for key, fn in (("F5", self.force_render), ("Esc", self.stop), ("Ctrl+S", self.save_now),
                        ("Ctrl+T", self.toggle_theme), ("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo),
                        ("Ctrl+Shift+Z", self.redo), ("Ctrl+D", self.duplicate_selected),
                        ("Ctrl+C", self.copy_selected), ("Ctrl+V", self.paste), ("Ctrl+0", self.fit),
                        ("Ctrl+1", lambda: self.set_mode("edit", True)), ("Ctrl+2", lambda: self.set_mode("try", True)),
                        ("Ctrl+3", lambda: self.set_mode("map", True))):
            s = QShortcut(QKeySequence(key), self)
            s.setContext(Qt.WindowShortcut)
            s.activated.connect(fn)

    # ---------- тема ----------
    def _apply_theme(self, name):
        theme.apply(QApplication.instance(), name)
        self.cfg["theme"] = theme.NAME
        col = theme.P["text"]
        for b in (self.b_undo, self.b_redo, self.b_more, self.b_board, self.b_prev, self.b_next):
            ic = b.property("ic")
            if ic:
                b.setIcon(icons.icon(ic, col, 18))
        self.b_theme.setIcon(icons.icon("moon" if theme.NAME == "dark" else "sun", col, 18))
        self.b_live.setIcon(icons.icon("live", col, 16))
        self.b_load.setIcon(icons.icon("bolt", "#ffffff", 16))
        self.b_board.setIcon(icons.icon("board", col, 16))
        for b in self.add_btns:
            b.setIcon(icons.icon(b.property("ic"), theme.P["accent"], 22))
        self.seg.recolor()
        self.title_icon.setPixmap(theme.icon_pixmap(18))
        for b in (self.frame.btn_min, self.frame.btn_max, self.frame.btn_close) if hasattr(self, "frame") else ():
            b.update()
        self.stage.update()
        self.mapv.update()

    def toggle_theme(self):
        self._apply_theme("light" if theme.NAME == "dark" else "dark")
        self._save_cfg()

    # ---------- движок и проект ----------
    def _init_engine(self):
        try:
            self.engine = Engine()
        except Exception as e:                         # noqa: BLE001
            self.engine = None
            log.info(f"✗ движок превью не загрузился: {e}")

    def _open_last_project(self):
        pid = self.cfg.get("project") or ""
        p = core.read_project(pid) if pid else None
        if not p:
            items = core.list_projects()
            if items:
                pid = items[0][0]
                p = core.read_project(pid)
        if not p:
            b = self.boards[0] if self.boards else {"id": "none", "w": 480, "h": 480}
            p = mp.new_project(b)
            pid = mp.slug("my-screen")
            core.save_project(pid, p)
        self.set_project(pid, p)

    def set_project(self, pid, p):
        self.pid = pid
        self.project = mp.clean(p)
        self.board = mb.board_by_id(self.boards, self.project.get("board"))
        if self.board and self.project.get("board") != self.board["id"]:
            self.project["board"] = self.board["id"]
        self.hist = mp.History()
        self.cur_screen = self.project.get("home")
        self.sel = None
        self.cfg["project"] = pid
        if self.engine and self.board:
            self.engine.init(self.board["w"], self.board["h"])
        self._dirty_engine = True
        self._dirty_thumbs = True
        self.stage.fit_on_resize = True
        self.stage.fit()
        self.mapv._fit_done = False
        self.refresh_all()

    def render(self):
        """Проект → движок → картинка; рамки блоков текущего экрана."""
        if not self.engine or not self.board:
            return
        if self._dirty_engine:
            r, err = self.engine.load(mp.runtime_json(self.project))
            if r:
                log.info(f"✗ превью: {err}")
            self._dirty_engine = False
            self._dirty_thumbs = True
        if self.mode != "try" and self.engine.screen() != self.cur_screen:
            self.engine.goto(self.cur_screen)
            self.engine.step(400)
        self.engine.redraw()
        self.stage.set_image(rgb565_image(self.engine.frame(), self.board["w"], self.board["h"]))
        self.rects = {}
        scr = mp.find_screen(self.project, self.cur_screen)
        for w in (scr or {}).get("widgets", []):
            r = self.engine.rect(w["id"])
            if r:
                self.rects[w["id"]] = r
        self.all_rects[self.cur_screen] = dict(self.rects)
        if self.mode == "map" and self._dirty_thumbs:
            self.render_thumbs()

    def render_thumbs(self):
        if not self.engine:
            return
        keep = self.engine.screen()
        for s in self.project["screens"]:
            self.engine.goto(s["id"])
            self.engine.step(400)
            self.engine.redraw()
            self.mapv.thumbs[s["id"]] = rgb565_image(self.engine.frame(), self.board["w"], self.board["h"])
            rr = {}
            for w in s["widgets"]:
                r = self.engine.rect(w["id"])
                if r:
                    rr[w["id"]] = r
            self.all_rects[s["id"]] = rr
        self.engine.goto(keep)
        self.engine.step(400)
        self._dirty_thumbs = False
        self.mapv.update()

    def force_render(self):
        self._dirty_engine = True
        self._dirty_thumbs = True
        self.render()
        log.info("✓ перерисовано")

    def _clock_tick(self):
        if self.mode == "edit" and self.engine and not self.stage._drag:
            self.engine.step(1000)
            self.render()

    def _try_tick(self):
        if not self.engine:
            return
        self.engine.step(33)
        self.stage.set_image(rgb565_image(self.engine.frame(), self.board["w"], self.board["h"]))
        sid = self.engine.screen()
        if sid and sid != self.cur_screen:
            self.cur_screen = sid
            self.sel = None
            self.refresh_screens()
            self.refresh_layers()
            self.refresh_props()
            self._screen_bar()

    def engine_touch(self, x, y, down):
        if self.engine:
            self.engine.touch(x, y, down)

    # ---------- изменения ----------
    def begin_change(self, key=None):
        now = time.time()
        if key and self._last_change[0] == key and now - self._last_change[1] < 1.5:
            self._last_change = (key, now)
            return
        self._last_change = (key, now)
        self.hist.push(self.project)

    def changed(self, what="prop"):
        self._dirty_engine = True
        self._dirty_thumbs = True
        self._dirty_save = True
        self._live_due = time.time() + (0.25 if what == "geom" else 0.05)
        if what == "geom":
            if not self.t_render.isActive():
                self.t_render.start()
            self._props_geom_sync()
            return
        self.render()
        if what in ("geom-done",):
            self._props_geom_sync()
            return
        if what in ("structure", "screens", "map", "undo"):
            self.refresh_all()
        elif what == "layers":
            self.refresh_layers()
        elif what == "screen-name":
            self.refresh_screens()
            self._screen_bar()
        elif what == "widget-name":
            self.refresh_layers()
        self._tiles()

    def undo(self):
        p = self.hist.back(self.project)
        if p is not None:
            self.project = mp.clean(p)
            if not mp.find_widget(self.project, self.sel)[1]:
                self.sel = None
            if not mp.find_screen(self.project, self.cur_screen):
                self.cur_screen = self.project["home"]
            self.changed("undo")

    def redo(self):
        p = self.hist.fwd(self.project)
        if p is not None:
            self.project = mp.clean(p)
            self.changed("undo")

    # ---------- обновление панелей ----------
    def refresh_all(self):
        self.h_proj.setText(self.project.get("name", "Проект"))
        self.refresh_screens()
        self.refresh_layers()
        self.refresh_props()
        self._board_chip()
        self._screen_bar()
        self._tiles()
        self.render()

    def _tiles(self):
        n_w = sum(len(s["widgets"]) for s in self.project["screens"])
        n_l = len(mp.links(self.project))
        self.tiles["screens"].setText(f"{len(self.project['screens'])}  ·  связей {n_l}")
        self.tiles["widgets"].setText(str(n_w))
        st = self._board_state()
        self.tiles["board"].setText(st[1])
        self.tiles["build"].setText(self.last_build or f"rev {self.project.get('rev', 0)}")

    def _screen_bar(self):
        s = mp.find_screen(self.project, self.cur_screen)
        if s:
            home = " ⌂" if s["id"] == self.project.get("home") else ""
            self.l_scr.setText(f"{s['name']}{home}")

    def refresh_screens(self):
        self.l_screens.blockSignals(True)
        self.l_screens.clear()
        for s in self.project["screens"]:
            it = QListWidgetItem(("⌂  " if s["id"] == self.project.get("home") else "      ") + s["name"])
            it.setData(Qt.UserRole, s["id"])
            self.l_screens.addItem(it)
            if s["id"] == self.cur_screen:
                self.l_screens.setCurrentItem(it)
        self.l_screens.blockSignals(False)

    def refresh_layers(self):
        s = mp.find_screen(self.project, self.cur_screen)
        self.layers_card.title_label.setText(f"СЛОИ · {s['name'].upper() if s else ''}")
        self.l_layers.blockSignals(True)
        self.l_layers.clear()
        for w in reversed((s or {}).get("widgets", [])):
            c = mp.CATALOG.get(w["type"], {})
            mark = "  ⇢" if w.get("link") else ""
            hid = "  (скрыт)" if w.get("hidden") else ""
            it = QListWidgetItem(icons.icon(c.get("icon", "rect"), theme.P["muted"], 16), w.get("name", w["type"]) + mark + hid)
            it.setData(Qt.UserRole, w["id"])
            self.l_layers.addItem(it)
            if w["id"] == self.sel:
                self.l_layers.setCurrentItem(it)
        self.l_layers.blockSignals(False)

    def _screen_row(self, row):
        if row < 0:
            return
        sid = self.l_screens.item(row).data(Qt.UserRole)
        self.open_screen(sid, switch=False)

    def _layer_row(self, row):
        if row < 0:
            return
        self.select(self.l_layers.item(row).data(Qt.UserRole), from_list=True)

    def _layers_moved(self, *a):
        s = mp.find_screen(self.project, self.cur_screen)
        ids = [self.l_layers.item(i).data(Qt.UserRole) for i in range(self.l_layers.count())]
        by = {w["id"]: w for w in s["widgets"]}
        self.begin_change()
        s["widgets"] = [by[i] for i in reversed(ids) if i in by]
        self.changed("prop")

    def open_screen(self, sid, switch=False):
        if not mp.find_screen(self.project, sid):
            return
        if sid != self.cur_screen:
            self.cur_screen = sid
            self.sel = None
            if self.engine:
                self.engine.goto(sid)
                self.engine.step(400)
            self.refresh_screens()
            self.refresh_layers()
            self.refresh_props()
            self._screen_bar()
            self.render()
            self.mapv.update()
        if switch:
            self.set_mode("edit", True)

    def step_screen(self, d):
        ids = [s["id"] for s in self.project["screens"]]
        if self.cur_screen in ids:
            self.open_screen(ids[(ids.index(self.cur_screen) + d) % len(ids)])

    def select(self, wid, from_list=False):
        if wid == self.sel:
            return
        self.sel = wid
        if not from_list:
            self.refresh_layers()
        self.refresh_props()
        self.stage.update()

    # ---------- режимы ----------
    def set_mode(self, mode, update_seg=False):
        if update_seg:
            self.seg.set(mode)
        self.mode = mode
        self.t_try.stop()
        if mode == "map":
            self.center.setCurrentWidget(self.mapv)
            self.render_thumbs()
            self.mapv.fit()
        else:
            self.center.setCurrentWidget(self.stage)
        if mode == "try":
            self.sel = None
            self.refresh_props()
            if self.engine:
                self.engine.goto(self.cur_screen)
            self.t_try.start()
            self._status("Проба: мышь вместо пальца, свайпы — протянуть мышью")
        elif mode == "edit":
            self._status("Правка: щёлкнуть блок — выбрать, тянуть — двигать, ручки — размер")
            self.render()
        else:
            self._status("Карта: двойной щелчок — открыть экран, карточки можно двигать")
        self.stage.update()

    def zoom_by(self, k):
        if self.mode == "map":
            self.mapv.zoom = max(0.15, min(3.0, self.mapv.zoom * k))
            self.mapv.update()
            return
        self.stage.fit_on_resize = False
        self.stage.set_zoom(self.stage.zoom * k)

    def fit(self):
        if self.mode == "map":
            self.mapv.fit()
        else:
            self.stage.fit()

    # ---------- блоки ----------
    def add_widget(self, kind):
        if self.mode != "edit":
            self.set_mode("edit", True)
        s = mp.find_screen(self.project, self.cur_screen)
        c = mp.CATALOG[kind]
        W, H = self.board["w"], self.board["h"]
        w = mp.widget(kind)
        if w["w"] > W:
            w["w"] = W
        if kind in ("clock", "date", "label"):
            w["w"] = min(W, max(w["w"], W * 2 // 3))
        w["x"] = (W - w["w"]) // 2
        w["y"] = (H - (w["h"] or c["defaults"].get("size", 40))) // 2
        self.begin_change()
        s["widgets"].append(w)
        self.sel = w["id"]
        self.changed("structure")
        log.info(f"✓ добавлено: {c['name']} на «{s['name']}»")

    def delete_selected(self):
        s, w = mp.find_widget(self.project, self.sel)
        if not w:
            return
        self.begin_change()
        s["widgets"].remove(w)
        self.sel = None
        self.changed("structure")

    def duplicate_selected(self):
        s, w = mp.find_widget(self.project, self.sel)
        if not w:
            return
        self.begin_change()
        n = copy.deepcopy(w)
        n["id"] = mp.new_id()
        n["x"] += 16
        n["y"] += 16
        s["widgets"].insert(s["widgets"].index(w) + 1, n)
        self.sel = n["id"]
        self.changed("structure")

    def copy_selected(self):
        _, w = mp.find_widget(self.project, self.sel)
        if w and self.focusWidget() in (self.stage, self.l_layers):
            QApplication.clipboard().setText(json.dumps({"linestudio": w}, ensure_ascii=False))

    def paste(self):
        if self.focusWidget() not in (self.stage, self.l_layers):
            return
        try:
            w = json.loads(QApplication.clipboard().text())["linestudio"]
        except Exception:                              # noqa: BLE001
            return
        s = mp.find_screen(self.project, self.cur_screen)
        self.begin_change()
        w["id"] = mp.new_id()
        w.pop("link", None) if (w.get("link") or {}).get("to") not in [x["id"] for x in self.project["screens"]] + ["@back"] else None
        s["widgets"].append(w)
        self.sel = w["id"]
        self.changed("structure")

    def move_layer(self, d):
        s, w = mp.find_widget(self.project, self.sel)
        if not w:
            return
        i = s["widgets"].index(w)
        j = max(0, min(len(s["widgets"]) - 1, i + d))
        if i == j:
            return
        self.begin_change()
        s["widgets"].insert(j, s["widgets"].pop(i))
        self.changed("layers")

    def toggle_hidden(self):
        _, w = mp.find_widget(self.project, self.sel)
        if w:
            self.begin_change()
            w["hidden"] = not w.get("hidden")
            self.changed("layers")

    # ---------- экраны ----------
    def add_screen(self, tpl):
        fn = dict((k, f) for k, _, f in mp.TEMPLATES)[tpl]
        s = fn(self.board["w"], self.board["h"])
        names = {x["name"] for x in self.project["screens"]}
        base, n = s["name"], 2
        while s["name"] in names:
            s["name"] = f"{base} {n}"
            n += 1
        self.begin_change()
        self.project["screens"].append(s)
        self.cur_screen = s["id"]
        self.sel = None
        self.changed("structure")
        log.info(f"✓ новый экран «{s['name']}»")

    def rename_screen(self):
        s = mp.find_screen(self.project, self.cur_screen)
        t, ok = QInputDialog.getText(self, "Экран", "Название экрана:", text=s["name"])
        if ok and t.strip():
            self.begin_change()
            s["name"] = t.strip()
            self.changed("screen-name")

    def duplicate_screen(self):
        s = mp.find_screen(self.project, self.cur_screen)
        n = copy.deepcopy(s)
        n["id"] = mp.new_id("s")
        n["name"] = s["name"] + " (копия)"
        for w in n["widgets"]:
            w["id"] = mp.new_id()
        self.begin_change()
        self.project["screens"].insert(self.project["screens"].index(s) + 1, n)
        self.cur_screen = n["id"]
        self.changed("structure")

    def delete_screen(self):
        if len(self.project["screens"]) <= 1:
            QMessageBox.information(self, "Экран", "Последний экран удалить нельзя.")
            return
        s = mp.find_screen(self.project, self.cur_screen)
        if QMessageBox.question(self, "Удалить экран", f"Удалить экран «{s['name']}» со всеми блоками?") \
                != QMessageBox.Yes:
            return
        self.begin_change()
        self.project["screens"].remove(s)
        (self.project.get("map") or {}).pop(s["id"], None)
        mp.clean(self.project)
        self.cur_screen = self.project["home"]
        self.sel = None
        self.changed("structure")

    def make_home(self):
        self.begin_change()
        self.project["home"] = self.cur_screen
        self.changed("screens")

    # ---------- свойства ----------
    def _clear_props(self):
        """Новая подложка свойств целиком (старая удаляется вместе со всеми полями)."""
        self.props_host = QWidget()
        self.props_form = QVBoxLayout(self.props_host)
        self.props_form.setContentsMargins(0, 0, 4, 0)
        self.props_form.setSpacing(10)
        old = self.props_scroll.takeWidget()
        self.props_scroll.setWidget(self.props_host)
        if old is not None:
            old.hide()
            old.deleteLater()
        self.prop_widgets = {}

    def _clear_layout(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._clear_layout(it.layout())

    def _section(self, title):
        lb = lab(title.upper(), "cardTitle")
        self.props_form.addWidget(lb)
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        f.setHorizontalSpacing(10)
        f.setVerticalSpacing(7)
        self.props_form.addLayout(f)
        return f

    def _editor(self, obj, key, kind, extra, on_set, wkey):
        """Поле свойства. on_set(key, value) — записать и обновить."""
        val = obj.get(key, 100 if key == "opa" else None)
        if kind == "int":
            lo, hi = extra or (-9999, 9999)
            e = IntField()
            e.setRange(lo, hi)
            e.setValue(int(val or 0))
            e.valueChanged.connect(lambda v: on_set(key, int(v)))
        elif kind == "color":
            e = ColorButton(val or "", lambda v: on_set(key, v), allow_empty=key in ("grad", "face"))
        elif kind == "bool":
            e = QCheckBox()
            e.setChecked(bool(val))
            e.toggled.connect(lambda v: on_set(key, bool(v)))
        elif kind in ("choice", "font", "source"):
            items = mp.FONTS if kind == "font" else extra
            e = QComboBox()
            for k, t in items:
                e.addItem(t, k)
            i = e.findData(val)
            e.setCurrentIndex(max(0, i))
            e.currentIndexChanged.connect(lambda i, e=e: on_set(key, e.itemData(i)))
        elif kind == "format":
            e = QComboBox()
            e.setEditable(True)
            for f in extra:
                e.addItem(f)
            e.setCurrentText(val or "")
            e.setToolTip("{HH} {mm} {ss} часы; {H} без нуля; {hh} {h} 12-часовые, {AMPM}\n"
                         "{d} {dd} число; {M} {MM} месяц числом; {YYYY} {YY} год\n"
                         "{dddd} день недели, {ddd} кратко; {MMMM} месяц, {MMMMg} — «ноября», {MMM} кратко\n"
                         "{^…} — ЗАГЛАВНЫМИ: {^dddd}")
            e.currentTextChanged.connect(lambda t: on_set(key, t))
        else:
            e = QLineEdit(str(val or ""))
            e.textChanged.connect(lambda t: on_set(key, t))
        self.prop_widgets[key] = e
        return e

    def refresh_props(self):
        self._clear_props()
        s, w = mp.find_widget(self.project, self.sel)
        if w:
            self._props_widget(s, w)
        else:
            self._props_screen()
            self._props_project()
        self.props_form.addStretch(1)

    def _set_w(self, w, key, v, struct=False):
        if w.get(key) == v:
            return
        self.begin_change(f"{w['id']}:{key}")
        if v in ("", None) and key in ("grad",):
            w[key] = ""
        else:
            w[key] = v
        self.changed("widget-name" if key == "name" else "geom-done" if key in ("x", "y", "w", "h") else "prop")

    def _props_widget(self, s, w):
        c = mp.CATALOG.get(w["type"], {"name": w["type"], "props": []})
        self.props_card.title_label.setText(f"СВОЙСТВА · {c['name'].upper()}")
        top = QHBoxLayout()
        name = QLineEdit(w.get("name", ""))
        name.setPlaceholderText("Название слоя")
        name.textChanged.connect(lambda t: self._set_w(w, "name", t))
        top.addWidget(name, 1)
        bdel = QToolButton()
        bdel.setIcon(icons.icon("trash", theme.ERR, 16))
        bdel.setToolTip("Удалить блок (Delete)")
        bdel.clicked.connect(self.delete_selected)
        top.addWidget(bdel)
        self.props_form.addLayout(top)
        f = self._section("Нажатие")
        cb = QComboBox()
        cb.addItem("Ничего", "")
        cb.addItem("← Назад", "@back")
        for x in self.project["screens"]:
            if x["id"] != s["id"]:
                cb.addItem("→ " + x["name"], x["id"])
        cur = (w.get("link") or {}).get("to", "")
        cb.setCurrentIndex(max(0, cb.findData(cur)))
        an = QComboBox()
        for k, t in mp.ANIMS:
            an.addItem(t, k)
        an.setCurrentIndex(max(0, an.findData((w.get("link") or {}).get("anim", "fade"))))
        an.setEnabled(bool(cur))

        def set_link():
            to = cb.currentData()
            self.begin_change()
            if to:
                w["link"] = {"to": to, "anim": an.currentData()}
            else:
                w.pop("link", None)
            an.setEnabled(bool(to))
            self.changed("widget-name")
            self._dirty_thumbs = True
        cb.currentIndexChanged.connect(lambda _: set_link())
        an.currentIndexChanged.connect(lambda _: set_link())
        f.addRow("Открывает", cb)
        f.addRow("Переход", an)
        f = self._section("Место")
        for key, kind, title, extra in mp.COMMON:
            e = self._editor(w, key, kind, extra, lambda k, v: self._set_w(w, k, v), True)
            if key == "h" and w.get("h", 0) == 0 and w["type"] in ("clock", "date", "label"):
                e.setToolTip("0 — высота по тексту")
            f.addRow(title, e)
        f = self._section(c["name"])
        for prop in c["props"]:
            key, kind, title = prop[:3]
            extra = prop[3] if len(prop) > 3 else None
            f.addRow(title, self._editor(w, key, kind, extra, lambda k, v: self._set_w(w, k, v), True))
        f = self._section("Порядок")
        row = QHBoxLayout()
        for text, fn, tip in (("Выше", lambda: self.move_layer(1), "Слой выше"),
                              ("Ниже", lambda: self.move_layer(-1), "Слой ниже"),
                              ("Копия", self.duplicate_selected, "Копия блока (Ctrl+D)"),
                              ("Скрыть" if not w.get("hidden") else "Показать", self.toggle_hidden, "Скрыть/показать")):
            b = QPushButton(text)
            b.setObjectName("chip")
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        self.props_form.addLayout(row)

    def _props_geom_sync(self):
        _, w = mp.find_widget(self.project, self.sel)
        if not w or not getattr(self, "prop_widgets", None):
            return
        for k in ("x", "y", "w", "h"):
            e = self.prop_widgets.get(k)
            if e is not None and e.value() != w.get(k):
                e.blockSignals(True)
                e.setValue(w.get(k, 0))
                e.blockSignals(False)

    def _props_screen(self):
        s = mp.find_screen(self.project, self.cur_screen)
        self.props_card.title_label.setText("СВОЙСТВА · ЭКРАН")
        f = self._section("Экран")
        name = QLineEdit(s["name"])

        def set_name(t):
            self.begin_change("scrname")
            s["name"] = t
            self.changed("screen-name")
        name.textChanged.connect(set_name)
        f.addRow("Название", name)

        def set_bg(v):
            self.begin_change()
            s["bg"] = v or "#000000"
            self.changed("prop")
        f.addRow("Фон", ColorButton(s["bg"], set_bg))
        if s["id"] != self.project.get("home"):
            b = QPushButton("⌂ Сделать главным")
            b.setObjectName("chip")
            b.clicked.connect(self.make_home)
            f.addRow("", b)
        f = self._section("Свайпы")
        for d, title in (("left", "Влево ←"), ("right", "Вправо →"), ("up", "Вверх ↑"), ("down", "Вниз ↓")):
            cb = QComboBox()
            cb.addItem("—", "")
            cb.addItem("Назад", "@back")
            for x in self.project["screens"]:
                if x["id"] != s["id"]:
                    cb.addItem(x["name"], x["id"])
            cb.setCurrentIndex(max(0, cb.findData((s.get("swipe") or {}).get(d, ""))))

            def set_sw(_, d=d, cb=cb):
                self.begin_change()
                v = cb.currentData()
                if v:
                    s.setdefault("swipe", {})[d] = v
                else:
                    s.setdefault("swipe", {}).pop(d, None)
                self.changed("map")
            cb.currentIndexChanged.connect(set_sw)
            f.addRow(title, cb)
        back = QCheckBox("Вправо без цели — назад")
        back.setChecked(bool(s.get("back", True)))

        def set_back(v):
            self.begin_change()
            s["back"] = bool(v)
            self.changed("prop")
        back.toggled.connect(set_back)
        f.addRow("", back)

    def _props_project(self):
        st = self.project["settings"]
        f = self._section("Проект")
        name = QLineEdit(self.project.get("name", ""))

        def set_name(t):
            self.begin_change("pname")
            self.project["name"] = t
            self.h_proj.setText(t)
            self._dirty_save = True
        name.textChanged.connect(set_name)
        f.addRow("Название", name)
        f.addRow("Плата", lab(self.board["name"] if self.board else "—", "muted"))
        lang = QComboBox()
        for k, t in mp.LANGS:
            lang.addItem(t, k)
        lang.setCurrentIndex(max(0, lang.findData(st.get("lang", "ru"))))

        def set_lang(i):
            self.begin_change()
            st["lang"] = lang.itemData(i)
            self.changed("prop")
        lang.currentIndexChanged.connect(set_lang)
        f.addRow("Язык даты", lang)
        zone = QComboBox()
        for k in mp.ZONES:
            zone.addItem(k, k)
        zone.setCurrentIndex(max(0, zone.findData(st.get("zone", "Киев"))))

        def set_zone(i):
            self.begin_change()
            st["zone"] = zone.itemData(i)
            st["tz"] = mp.ZONES[st["zone"]]
            self._dirty_save = True
        zone.currentIndexChanged.connect(set_zone)
        f.addRow("Часовой пояс", zone)
        br = IntField()
        br.setRange(1, 100)
        br.setSuffix(" %")
        br.setValue(int(st.get("brightness", 80)))

        def set_br(v):
            self.begin_change("bright")
            st["brightness"] = int(v)
            self._dirty_save = True
        br.valueChanged.connect(set_br)
        f.addRow("Яркость", br)
        wifi = QCheckBox("Время по Wi-Fi (NTP)")
        wifi.setChecked(bool(st.get("wifi")))

        def set_wifi(v):
            self.begin_change()
            st["wifi"] = bool(v)
            self._dirty_save = True
            if v and not self.secrets.get("wifi", {}).get("ssid"):
                self.wifi_dialog()
        wifi.toggled.connect(set_wifi)
        f.addRow("Wi-Fi", wifi)
        bw = QPushButton("Сеть Wi-Fi…")
        bw.setObjectName("chip")
        bw.clicked.connect(self.wifi_dialog)
        f.addRow("", bw)
        wifi.setToolTip("Без Wi-Fi время ставит редактор при заливке и при Live")

    def focus_prop(self, key):
        e = getattr(self, "prop_widgets", {}).get(key)
        if e:
            e.setFocus()
            if isinstance(e, QLineEdit):
                e.selectAll()

    # ---------- меню ----------
    def _stage_menu(self, pos):
        if self.mode != "edit":
            return
        wid = self.stage.hit(self.stage.mapFrom(self.stage, pos))
        if wid:
            self.select(wid)
        m = QMenu(self)
        if self.sel:
            m.addAction("Копия (Ctrl+D)", self.duplicate_selected)
            m.addAction("Выше", lambda: self.move_layer(1))
            m.addAction("Ниже", lambda: self.move_layer(-1))
            m.addAction("Скрыть / показать", self.toggle_hidden)
            m.addAction("Копировать (Ctrl+C)", self.copy_selected)
            m.addSeparator()
            m.addAction("Удалить (Delete)", self.delete_selected)
            m.addSeparator()
        add = m.addMenu("Добавить")
        for kind, c in mp.CATALOG.items():
            add.addAction(icons.icon(c["icon"], theme.P["text"], 16), c["name"], lambda k=kind: self.add_widget(k))
        m.addAction("Вставить (Ctrl+V)", self.paste)
        m.addSeparator()
        m.addAction("Вписать (Ctrl+0)", self.fit)
        m.addAction("Перерисовать (F5)", self.force_render)
        m.exec(self.stage.mapToGlobal(pos))

    def _map_menu(self, pos):
        sid = self.mapv.card_at(pos)
        m = QMenu(self)
        if sid:
            self.open_screen(sid)
            m.addAction("Открыть", lambda: self.open_screen(sid, switch=True))
            m.addAction("Переименовать…", self.rename_screen)
            m.addAction("Копия", self.duplicate_screen)
            m.addAction("Сделать главным", self.make_home)
            m.addAction("Удалить…", self.delete_screen)
            m.addSeparator()
        new = m.addMenu("Новый экран")
        for key, name, _fn in mp.TEMPLATES:
            new.addAction(name, lambda k=key: self.add_screen(k))
        m.addAction("Разложить заново", self._map_reset)
        m.addAction("Вписать", self.mapv.fit)
        m.exec(self.mapv.mapToGlobal(pos))

    def _map_reset(self):
        self.begin_change()
        self.project.pop("map", None)
        self.changed("map")
        self.mapv.fit()

    def _screens_menu(self, pos):
        it = self.l_screens.itemAt(pos)
        m = QMenu(self)
        if it:
            self.open_screen(it.data(Qt.UserRole))
            m.addAction("Переименовать…", self.rename_screen)
            m.addAction("Копия", self.duplicate_screen)
            m.addAction("Сделать главным", self.make_home)
            m.addAction("Удалить…", self.delete_screen)
            m.addSeparator()
        new = m.addMenu("Новый экран")
        for key, name, _fn in mp.TEMPLATES:
            new.addAction(name, lambda k=key: self.add_screen(k))
        m.exec(self.l_screens.mapToGlobal(pos))

    def _layers_menu(self, pos):
        it = self.l_layers.itemAt(pos)
        m = QMenu(self)
        if it:
            self.select(it.data(Qt.UserRole), from_list=True)
            m.addAction("Копия (Ctrl+D)", self.duplicate_selected)
            m.addAction("Выше", lambda: self.move_layer(1))
            m.addAction("Ниже", lambda: self.move_layer(-1))
            m.addAction("Скрыть / показать", self.toggle_hidden)
            m.addSeparator()
            m.addAction("Удалить", self.delete_selected)
        add = m.addMenu("Добавить")
        for kind, c in mp.CATALOG.items():
            add.addAction(c["name"], lambda k=kind: self.add_widget(k))
        m.exec(self.l_layers.mapToGlobal(pos))

    def _log_menu(self, pos):
        m = self.logw.createStandardContextMenu()
        m.clear()
        m.addAction("Копировать", self.logw.copy)
        m.addAction("Копировать всё", lambda: QApplication.clipboard().setText(self.logw.toPlainText()))
        m.addAction("Выделить всё", self.logw.selectAll)
        m.addAction("Сохранить в файл…", self._save_log)
        m.addSeparator()
        m.addAction("Очистить", self.logw.clear)
        m.exec(self.logw.mapToGlobal(pos))

    def _save_log(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Журнал", os.path.join(core.APP_ROOT, "журнал.txt"), "Текст (*.txt)")
        if fn:
            open(fn, "w", encoding="utf-8").write(self.logw.toPlainText())

    def projects_menu(self):
        m = QMenu(self)
        m.addAction("Новый проект…", self.new_project_dialog)
        m.addAction("Открыть проект…", self.open_project_dialog)
        m.addAction("Сохранить (Ctrl+S)", self.save_now)
        m.addAction("Сохранить как…", self.save_as)
        m.addSeparator()
        m.addAction("Экспорт в файл…", self.export_project)
        m.addAction("Импорт из файла…", self.import_project)
        m.addAction("Переименовать…", self.rename_project)
        return m

    def _fill_more_menu(self, m):
        m.clear()
        m.addMenu(self.projects_menu()).setText("Проекты")
        m.addSeparator()
        m.addAction("Перерисовать (F5)", self.force_render)
        m.addAction("Тема светлая / тёмная (Ctrl+T)", self.toggle_theme)
        m.addSeparator()
        m.addAction("Проверить плату", self.check_board)
        m.addAction("Сохранить прошивку платы…", self.backup_board)
        m.addAction("Сеть Wi-Fi платы…", self.wifi_dialog)
        m.addAction("Забыть Live на плате (вернуть залитый проект)", lambda: self._send("forget"))
        m.addSeparator()
        m.addAction("Обновление с GitHub…", self.update_dialog)
        m.addAction("Папка программы", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(core.APP_ROOT)))
        m.addAction("Перезапуск", self.restart)
        a = m.addAction("Стоп (Esc)", self.stop)
        a.setEnabled(bool(self.busy))
        return m

    # ---------- плата ----------
    def _board_state(self):
        """(цвет точки, текст плитки, порт)"""
        bid = self.board["id"] if self.board else ""
        for port, st in self.port_state.items():
            if bid not in st.get("boards", []):
                continue
            h = st.get("hello")
            if h and h.get("board") == bid:
                if h.get("project") == self.pid and str(h.get("rev")) == str(self.project.get("rev", 0)):
                    return "green", f"{port} · этот проект", port
                return "blue", f"{port} · LineStudio", port
            if h and "error" in h:
                return "yellow", f"{port} · занят", port
            return "yellow", f"{port} · чужая прошивка", port
        return "none", "не подключена", None

    def _board_chip(self):
        c, text, port = self._board_state()
        self.dot.set(c, {"green": "На плате этот проект", "blue": "Прошивка LineStudio (другой проект или версия)",
                         "yellow": "На плате чужая прошивка — или порт занят", "none": "Плата не подключена"}[c])
        self.b_board.setText(f" {self.board['short'] if self.board else '—'}" + (f" · {port}" if port else ""))
        self.tiles["board"].setText(text)

    def _fill_board_menu(self):
        m = self.b_board.menu()
        m.clear()
        m.addSection("Плата проекта")
        for b in self.boards:
            a = m.addAction(f"{b['name']} — {b['screen']}", lambda b=b: self.change_board(b))
            a.setCheckable(True)
            a.setChecked(self.board is not None and b["id"] == self.board["id"])
        m.addSection("Порт USB")
        if not self.ports:
            m.addAction("(портов нет — подключите плату кабелем с данными)").setEnabled(False)
        for p in self.ports:
            fits = ", ".join(p["boards"]) or "не плата из списка"
            a = m.addAction(f"{p['port']} — {p['desc']} [{p['vid_pid']}] ({fits})",
                            lambda pp=p["port"]: self._set_port(pp))
            a.setCheckable(True)
            a.setChecked(self.cfg.get("port") == p["port"])
        a = m.addAction("Сам (по паспорту платы)", lambda: self._set_port(""))
        a.setCheckable(True)
        a.setChecked(not self.cfg.get("port"))
        if self.board and self.board.get("chip_variants"):
            m.addSection("Ревизия чипа")
            cur = self.cfg.get("chip_variant", {}).get(self.board["id"], "")
            for name, val in self.board["chip_variants"].items():
                a = m.addAction(name, lambda v=val: self._set_variant(v))
                a.setCheckable(True)
                a.setChecked(cur == val or (not cur and val in self.board["fqbn"]))
        m.addSeparator()
        m.addAction("Проверить плату", self.check_board)
        m.addAction("Сохранить прошивку платы…", self.backup_board)

    def _set_port(self, p):
        self.cfg["port"] = p
        self._save_cfg()
        self._board_chip()

    def _set_variant(self, v):
        self.cfg.setdefault("chip_variant", {})[self.board["id"]] = v
        self._save_cfg()
        log.info(f"✓ ревизия чипа: {v}")

    def change_board(self, b):
        if self.board and b["id"] == self.board["id"]:
            return
        if QMessageBox.question(self, "Плата", f"Перевести проект на {b['name']} ({b['w']}×{b['h']})?\n"
                                "Блоки останутся на своих местах — экраны другого размера, проверьте раскладку.") \
                != QMessageBox.Yes:
            return
        self.begin_change()
        old = self.board
        self.project["board"] = b["id"]
        kx = b["w"] / old["w"] if old else 1
        ky = b["h"] / old["h"] if old else 1
        k = min(kx, ky)
        oW, oH = (old["w"], old["h"]) if old else (b["w"], b["h"])
        for s in self.project["screens"]:
            for w in s["widgets"]:
                cx = abs(w["x"] + w["w"] / 2 - oW / 2) < 3          # стоял по центру — останется по центру
                cy = w["h"] and abs(w["y"] + w["h"] / 2 - oH / 2) < 3
                full = w["w"] >= oW - 2                           # был во всю ширину — во всю ширину
                w["x"], w["y"] = int(w["x"] * kx), int(w["y"] * ky)
                w["w"], w["h"] = (b["w"] if full else int(w["w"] * k)), int(w["h"] * k)
                if full:
                    w["x"] = 0
                elif cx:
                    w["x"] = (b["w"] - w["w"]) // 2
                if cy:
                    w["y"] = (b["h"] - w["h"]) // 2
                if "size" in w:
                    w["size"] = max(6, int(w["size"] * k))
        self.set_project(self.pid, self.project)
        self._dirty_save = True

    def _port_for_board(self):
        if self.cfg.get("port"):
            return self.cfg["port"]
        st = self._board_state()
        if st[2]:
            return st[2]
        for p in self.ports:
            if self.board["id"] in p["boards"]:
                return p["port"]
        return None

    def _scan_ports(self):
        if self._scanning or self.busy:
            return
        self._scanning = True
        boards = self.boards
        live_port = self.link.port if self.link else None

        def job():
            try:
                ps = ml.ports(boards)
                states = {}
                for p in ps:
                    old = self.port_state.get(p["port"])
                    if p["port"] == live_port and old:
                        states[p["port"]] = old
                        continue
                    if old and old.get("asked"):
                        states[p["port"]] = old
                        continue
                    h = ml.hello(p["port"]) if p["boards"] else None
                    states[p["port"]] = {"boards": p["boards"], "hello": h, "asked": True}
                core.log_q.put(lambda: self._ports_done(ps, states))
            finally:
                self._scanning = False
        threading.Thread(target=job, daemon=True).start()

    def _ports_done(self, ps, states):
        before = set(self.port_state)
        self.ports = ps
        self.port_state = states
        for p in set(states) - before:
            h = states[p].get("hello")
            if states[p]["boards"]:
                if h and "board" in h:
                    log.info(f"✓ плата на {p}: {h.get('board')}, прошивка LineStudio {h.get('fw')}, проект {h.get('project')} rev {h.get('rev')}")
                else:
                    log.info(f"⚠ на {p} подходящая плата, но не ответила: чужая прошивка (или занят порт)")
        for p in before - set(states):
            log.info(f"⚠ порт {p} пропал")
            if self.link and self.link.port == p:
                self.b_live.setChecked(False)
        self._board_chip()

    def check_board(self):
        port = self._port_for_board()
        if not port:
            log.info("⚠ плата не подключена")
            return
        self.port_state.pop(port, None)
        if self.link and self.link.port == port:
            self._send("hello")
        else:
            self._scan_ports()

    def _send(self, cmd):
        if self.link and self.link.alive:
            self.link.send(cmd)
            return
        port = self._port_for_board()
        if not port:
            log.info("⚠ плата не подключена")
            return
        try:
            lk = ml.Link(port, lambda s: core.log_q.put(lambda s=s: self._board_line(s)))
            lk.send(cmd)
            time.sleep(0.3)
            lk.close()
        except Exception as e:                         # noqa: BLE001
            log.info(f"✗ {port}: {e}")

    # ---------- Live ----------
    def toggle_live(self, on):
        if on:
            port = self._port_for_board()
            if not port:
                log.info("⚠ Live: плата не подключена")
                self.b_live.setChecked(False)
                return
            try:
                self.link = ml.Link(port, lambda s: core.log_q.put(lambda s=s: self._board_line(s)))
                self.link.set_time(self.project["settings"].get("tz", "UTC0"))
                self.link.send("hello")
                self._live_due = time.time()
                log.info(f"✓ Live: {port} — правки идут на плату сразу (на плате нужна прошивка LineStudio)")
            except Exception as e:                     # noqa: BLE001
                log.info(f"✗ Live: {port}: {e}")
                self.link = None
                self.b_live.setChecked(False)
        else:
            if self.link:
                self.link.close()
                self.link = None
                log.info("Live выключен")

    def _live_tick(self):
        if not self.link:
            return
        if not self.link.alive:
            self.b_live.setChecked(False)
            return
        if self._live_due and time.time() >= self._live_due:
            self._live_due = 0
            try:
                self.link.live(mp.runtime_json(self.project))
                if self.link.last_hello is None:
                    pass
            except Exception as e:                     # noqa: BLE001
                log.info(f"✗ Live: {e}")
                self.b_live.setChecked(False)

    def _board_line(self, s):
        if s.startswith("LS log "):
            log.info("плата: " + s[7:])
        elif s.startswith("LS err"):
            log.info("✗ плата: " + s[7:])
        elif s.startswith("LS hello"):
            h = ml.parse_hello(s)
            port = self.link.port if self.link else None
            if port:
                self.port_state.setdefault(port, {"boards": [h.get("board")]})["hello"] = h
            self._board_chip()
            log.info(f"✓ плата: {h.get('board')} fw {h.get('fw')}, проект {h.get('project')} rev {h.get('rev')}, экран {h.get('screen')}")
        elif s.startswith("LS ok live"):
            pass
        elif s.startswith("LS ok"):
            log.info("✓ плата: " + s[6:])

    # ---------- работы в потоке ----------
    def _run(self, name, fn):
        if self.busy:
            log.info(f"⚠ уже идёт: {self.busy}")
            return
        self.busy = name
        self.cancel = False
        self._busy_ui(True, name)

        def wrap():
            try:
                fn()
            except mb.BuildError as e:
                for ln in str(e).splitlines()[-12:]:
                    log.info("✗ " + ln)
                log.info(f"✗ {name}: не вышло")
            except Exception as e:                     # noqa: BLE001
                log.info(f"✗ {name}: {e}")
            finally:
                core.log_q.put(core.DONE)
        self.worker = threading.Thread(target=wrap, name=name)
        self.worker.start()

    def _busy_ui(self, on, name=""):
        self.b_load.setEnabled(not on)
        self.progress.setVisible(on)
        self.b_stop.setVisible(on)
        self.progress.setValue(0)
        txt = f"● {name}…" if on else "● готов"
        self.pill.setText(txt)
        self.s_pill.setText(txt)
        col = theme.WARN if on else theme.OK
        self.pill.setStyleSheet(f"color: {col};")
        self.s_pill.setStyleSheet(f"color: {col};")

    def _progress(self, v):
        core.log_q.put(lambda: self.progress.setValue(int(v)))

    def stop(self):
        if self.busy:
            if QMessageBox.question(self, "Стоп", f"Остановить «{self.busy}»?") == QMessageBox.Yes:
                self.cancel = True
                log.info("⚠ останавливаю…")
        elif self.mode == "try":
            self.set_mode("edit", True)

    def load_to_board(self):
        if self.busy:
            return
        self.save_now()
        for prob in mp.problems(self.project, self.board):
            log.info(prob)
        port = self._port_for_board()
        st = self._board_state()
        do_backup = False
        if port and st[0] == "yellow":
            os.makedirs(mb.BACKUPS, exist_ok=True)
            have = [f for f in os.listdir(mb.BACKUPS) if f.startswith(self.board["id"]) and f.endswith(".bin")]
            if not have:
                r = QMessageBox.question(self, "Чужая прошивка",
                                         "На плате не прошивка LineStudio.\nСохранить её копию перед первой заливкой?\n"
                                         "(чтение всей памяти — 3–5 минут; копия — в папке backups/)",
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                if r == QMessageBox.Cancel:
                    return
                do_backup = r == QMessageBox.Yes
        if self.link:
            self.b_live.setChecked(False)
        board = self.board
        variant = self.cfg.get("chip_variant", {}).get(board["id"])
        self.project["rev"] = int(self.project.get("rev", 0)) + 1
        proj = copy.deepcopy(self.project)
        pid = self.pid
        core.save_project(pid, self.project)
        secrets = self.secrets.get("wifi") or {}

        def job():
            tools = mb.Tools(log.info)
            tools.ensure(board.get("core", "3.3.7"), progress=self._progress, cancel=lambda: self.cancel)
            p = port or self._port_for_board()
            if do_backup and p:
                log.info("⏳ копия прошивки платы…")
                mb.backup(tools, board, p, log.info, self._progress, lambda: self.cancel)
            log.info(f"⏳ сборка: {board['name']}, проект «{proj['name']}» rev {proj['rev']}")
            sk = mb.write_sketch(proj, board, {"pid": pid, "rev": proj["rev"]}, secrets, log.info)
            out = mb.compile_sketch(tools, board, sk, log.info, self._progress, lambda: self.cancel, variant)
            size = 0
            for fn in os.listdir(out):
                if fn.endswith(".ino.bin"):
                    size = os.path.getsize(os.path.join(out, fn))
            core.log_q.put(lambda: self._built(size))
            if not p:
                log.info("⚠ плата не подключена: прошивка собрана, заливки не было (подключите плату и «Залить» ещё раз)")
                return
            log.info(f"⏳ заливка в {p}…")
            self._progress(0)
            mb.upload(tools, board, p, out, log.info, self._progress, lambda: self.cancel, variant)
            time.sleep(2.5)
            h = None
            for _ in range(4):
                h = ml.hello(p, 2.0)
                if h and "board" in h:
                    break
                time.sleep(1)
            if h and "board" in h:
                lk = ml.Link(p)
                lk.set_time(proj["settings"].get("tz", "UTC0"))
                time.sleep(0.2)
                lk.close()
                log.info(f"✓ на плате: проект {h.get('project')} rev {h.get('rev')} — время поставлено")
            else:
                log.info("⚠ плата не ответила после заливки — если экран не загорелся, нажмите RST")
            core.log_q.put(lambda: (self.port_state.pop(p, None), self._scan_ports()))
        self._run("Заливка", job)

    def _built(self, size):
        self.last_build = f"{size // 1024} КБ · {time.strftime('%H:%M')}"
        self._tiles()

    def backup_board(self):
        port = self._port_for_board()
        if not port:
            log.info("⚠ плата не подключена")
            return
        if self.link:
            self.b_live.setChecked(False)
        board = self.board

        def job():
            tools = mb.Tools(log.info)
            tools.ensure(board.get("core", "3.3.7"), progress=self._progress, cancel=lambda: self.cancel)
            mb.backup(tools, board, port, log.info, self._progress, lambda: self.cancel)
        self._run("Копия прошивки", job)

    # ---------- проекты ----------
    def save_now(self):
        if self.project:
            core.save_project(self.pid, self.project)
            self._dirty_save = False
            self._save_cfg()
            self._status(f"Сохранено: {self.pid}.json")

    def _autosave(self):
        if self._dirty_save:
            self.save_now()

    def rename_project(self):
        t, ok = QInputDialog.getText(self, "Проект", "Название проекта:", text=self.project.get("name", ""))
        if ok and t.strip():
            self.begin_change()
            self.project["name"] = t.strip()
            self.h_proj.setText(t.strip())
            self._dirty_save = True
            self.refresh_props()

    def new_project_dialog(self):
        d = QDialog(self)
        d.setWindowTitle("Новый проект")
        f = QFormLayout(d)
        name = QLineEdit("Мой экран")
        bc = QComboBox()
        for b in self.boards:
            bc.addItem(f"{b['name']} — {b['screen']}", b["id"])
        if self.board:
            bc.setCurrentIndex(max(0, bc.findData(self.board["id"])))
        f.addRow("Название", name)
        f.addRow("Плата", bc)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        d.resize(520, 140)
        if d.exec() != QDialog.Accepted:
            return
        self.save_now()
        b = mb.board_by_id(self.boards, bc.currentData())
        p = mp.new_project(b, name.text().strip() or "Мой экран")
        pid = mp.slug(p["name"].encode("ascii", "ignore").decode() or "project")
        core.save_project(pid, p)
        self.set_project(pid, p)
        log.info(f"✓ новый проект «{p['name']}» для {b['name']}")

    def open_project_dialog(self):
        items = core.list_projects()
        if not items:
            return
        labels = [f"{name}   [{bid}]   ({pid})" for pid, name, bid in items]
        t, ok = QInputDialog.getItem(self, "Открыть проект", "Проект:", labels, 0, False)
        if ok:
            pid = items[labels.index(t)][0]
            self.save_now()
            p = core.read_project(pid)
            if p:
                self.set_project(pid, p)
                log.info(f"✓ открыт проект «{p.get('name')}»")

    def save_as(self):
        t, ok = QInputDialog.getText(self, "Сохранить как", "Название копии:", text=self.project["name"] + " копия")
        if ok and t.strip():
            p = copy.deepcopy(self.project)
            p["name"] = t.strip()
            p["rev"] = 0
            pid = mp.slug(p["name"].encode("ascii", "ignore").decode() or "project")
            core.save_project(pid, p)
            self.set_project(pid, p)

    def export_project(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Экспорт проекта", os.path.join(core.APP_ROOT, self.pid + ".json"),
                                            "Проект LineStudio (*.json)")
        if fn:
            core.write_json(fn, self.project)
            log.info(f"✓ экспорт: {fn}")

    def import_project(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Импорт проекта", core.APP_ROOT, "Проект LineStudio (*.json)")
        if not fn:
            return
        try:
            p = json.load(open(fn, encoding="utf-8"))
            assert isinstance(p, dict) and "screens" in p
        except Exception as e:                         # noqa: BLE001
            QMessageBox.warning(self, "Импорт", f"Это не проект LineStudio:\n{e}")
            return
        pid = mp.slug(os.path.splitext(os.path.basename(fn))[0].encode("ascii", "ignore").decode() or "project")
        core.save_project(pid, p)
        self.set_project(pid, p)

    def wifi_dialog(self):
        w = self.secrets.get("wifi", {})
        d = QDialog(self)
        d.setWindowTitle("Wi-Fi платы")
        f = QFormLayout(d)
        ssid = QLineEdit(w.get("ssid", ""))
        pw = QLineEdit(w.get("password", ""))
        pw.setEchoMode(QLineEdit.Password)
        show = QCheckBox("Показать пароль")
        show.toggled.connect(lambda v: pw.setEchoMode(QLineEdit.Normal if v else QLineEdit.Password))
        f.addRow("Сеть (SSID)", ssid)
        f.addRow("Пароль", pw)
        f.addRow("", show)
        hint = lab("Хранится только на этом ПК (secrets.json) и попадает лишь в собранную прошивку.", "hint")
        hint.setWordWrap(True)
        f.addRow(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        d.resize(460, 160)
        if d.exec() == QDialog.Accepted:
            self.secrets["wifi"] = {"ssid": ssid.text().strip(), "password": pw.text()}
            core.save_secrets(self.secrets)
            log.info(f"✓ Wi-Fi платы: {ssid.text().strip()} (password=***)")

    def update_dialog(self):
        try:
            from app import gh_update, gh_update_qt
        except Exception as e:                         # noqa: BLE001
            log.info(f"✗ обновление: {e}")
            return
        t = gh_update.UpdateTarget(owner=core.REPO_OWNER, repo=core.REPO_NAME, name="line_studio",
                                   current=core.VERSION, app_dir=core.APP_ROOT, main_file="line_studio.pyw",
                                   changelog="CHANGELOG.md", where="⋯ → Обновление с GitHub")
        t.keep = tuple(t.keep) + ("projects/*", "secrets.json", "backups/*", "build/*", "tools/*")
        d = QDialog(self)
        d.setWindowTitle("Обновление с GitHub")
        v = QVBoxLayout(d)
        upd = self.cfg.setdefault("update", dict(core.DEFAULT_CONFIG["update"]))

        def cfg_set(x):
            upd.update(x)
            self._save_cfg()
        page = gh_update_qt.UpdatePage(t, lambda: dict(upd), cfg_set, on_quit=self.close, log=log.info,
                                       can_install=lambda: not self.busy)
        v.addWidget(page)
        d.resize(900, 520)
        d.exec()

    def restart(self):
        self.save_now()
        args = [sys.executable, os.path.join(core.APP_ROOT, "line_studio.pyw")]
        subprocess.Popen(args, cwd=core.APP_ROOT)
        self.close()

    # ---------- журнал ----------
    def _drain(self):
        n = 0
        while n < 300:
            try:
                item = core.log_q.get_nowait()
            except Exception:                          # noqa: BLE001
                break
            n += 1
            if item is core.DONE:
                self.busy = None
                self._busy_ui(False)
                self._tiles()
                continue
            if callable(item):
                try:
                    item()
                except Exception as e:                 # noqa: BLE001
                    self._append(f"✗ {e}")
                continue
            self._append(str(item))
        if self.engine:
            for ln in self.engine.log():
                if ln.startswith("ls: неизвестный"):
                    self._append("⚠ превью: " + ln[4:])

    def _append(self, text):
        sb = self.logw.verticalScrollBar()
        at_end = sb.value() >= sb.maximum() - 4
        fmt = QTextCharFormat()
        t = text.lstrip()
        if t.startswith(("✗", "⛔")):
            fmt.setForeground(QColor(theme.ERR))
        elif t.startswith("⚠"):
            fmt.setForeground(QColor(theme.WARN))
        elif t.startswith(("✓", "✅")):
            fmt.setForeground(QColor(theme.OK))
        else:
            fmt.setForeground(QColor(theme.P["log_fg"]))
        cur = QTextCursor(self.logw.document())
        cur.movePosition(QTextCursor.End)
        if not self.logw.document().isEmpty():
            cur.insertBlock()
        cur.insertText(time.strftime("%H:%M:%S  ") + text, fmt)
        if at_end:
            sb.setValue(sb.maximum())
        if t.startswith(("✓", "✗", "⚠", "⏳")):
            self._status(t[:120])

    def _status(self, text):
        self.s_text.setText(text)

    # ---------- настройки окна ----------
    def _save_cfg(self):
        try:
            self.cfg["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
            self.cfg["splitter"] = bytes(self.split.saveState().toBase64()).decode()
            self.cfg["vsplit"] = bytes(self.vsplit.saveState().toBase64()).decode()
            core.save_config(self.cfg)
        except Exception as e:                         # noqa: BLE001
            print("config:", e)

    def _restore_geometry(self):
        for key, w in (("splitter", self.split), ("vsplit", self.vsplit)):
            if self.cfg.get(key):
                w.restoreState(QByteArray.fromBase64(self.cfg[key].encode()))
        if self.cfg.get("geometry"):
            self.restoreGeometry(QByteArray.fromBase64(self.cfg["geometry"].encode()))

    def closeEvent(self, ev):                          # noqa: N802 (Qt)
        if self.busy:
            if QMessageBox.question(self, "Идёт работа", f"Идёт «{self.busy}». Остановить и закрыть?") != QMessageBox.Yes:
                ev.ignore()
                return
            self.cancel = True
            if self.worker:
                self.worker.join(timeout=15)
        if self.link:
            self.link.close()
        self.save_now()
        super().closeEvent(ev)


class _ContextMenus(QObject):
    """Правый клик — везде: русское меню для полей и текстов."""

    def eventFilter(self, obj, ev):                    # noqa: N802 (Qt)
        if ev.type() == QEvent.ContextMenu and isinstance(obj, (QLineEdit, QPlainTextEdit)) and \
                obj.objectName() != "log":
            m = QMenu(obj)
            ro = obj.isReadOnly()
            if isinstance(obj, QLineEdit):
                m.addAction("Отменить", obj.undo).setEnabled(not ro and obj.isUndoAvailable())
                m.addSeparator()
                m.addAction("Вырезать", obj.cut).setEnabled(not ro and obj.hasSelectedText())
                m.addAction("Копировать", obj.copy).setEnabled(obj.hasSelectedText())
                m.addAction("Вставить", obj.paste).setEnabled(not ro)
                m.addAction("Удалить", obj.del_).setEnabled(not ro and obj.hasSelectedText())
                m.addSeparator()
                m.addAction("Выделить всё", obj.selectAll)
            else:
                m.addAction("Копировать", obj.copy)
                m.addAction("Вставить", obj.paste).setEnabled(not ro)
                m.addAction("Выделить всё", obj.selectAll)
            m.exec(ev.globalPos())
            return True
        return False


def run():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LineStudio.App")
        except Exception:                              # noqa: BLE001
            pass
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    from PySide6.QtCore import QLibraryInfo, QTranslator
    app._tr = []
    for name in ("qtbase_ru", "qt_ru"):          # русские кнопки диалогов: «Да», «Нет», «Отмена»
        tr = QTranslator(app)
        if tr.load(name, QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
            app.installTranslator(tr)
            app._tr.append(tr)
    app.setWindowIcon(theme.app_icon())
    app._dlg = theme.DialogBar()
    app.installEventFilter(app._dlg)
    app._menus = _ContextMenus()
    app.installEventFilter(app._menus)
    w = MainWindow()
    w.show()
    w.seg.set("edit")
    return app.exec()


_ = (QAction, QFont, QPainter, QRectF)
