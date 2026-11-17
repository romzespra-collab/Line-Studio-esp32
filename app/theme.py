"""theme.py  v0.1.0 — тема LineStudio: общая палитра (тёмная / светлая), QSS, QPalette, полоса диалогов Windows.

Журнал:
v0.1.0: первая версия — палитра из правил (общая для новых программ Видов 1, 2, 4), QSS на всё приложение
        (диалоги не белые), палитра Qt с нуля для Active/Inactive/Disabled, тёмная полоса системных диалогов
        Windows (DwmSetWindowAttribute 20/19, на Win11 — цвет 35/36), значок программы QPainter-ом.

Модули из SmartMon (window_frame, gh_update_qt) берут отсюда TEXT, TEXT_DIM, BORDER, ACCENT, BG_PANEL.
"""
import sys

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap

THEMES = {
    "dark": {"bg": "#1b1d23", "side": "#16181d", "panel": "#23262e", "panel2": "#2a2e38", "line": "#343946",
             "text": "#e6e8ee", "muted": "#8a91a3", "log_bg": "#111318", "log_fg": "#d5d8e0", "accent": "#4f8cff",
             "canvas": "#14161b", "dots": "#262a33"},
    "light": {"bg": "#f3f4f7", "side": "#e9ebf0", "panel": "#ffffff", "panel2": "#f1f3f7", "line": "#dde1e8",
              "text": "#1c2230", "muted": "#6b7385", "log_bg": "#fbfbfd", "log_fg": "#1c2230", "accent": "#2f6fe4",
              "canvas": "#e8eaef", "dots": "#d3d7df"},
}
OK, ERR, WARN = "#3ecf8e", "#ff5d6c", "#f5b545"

NAME = "dark"
P = dict(THEMES["dark"])
TEXT = P["text"]
TEXT_DIM = P["muted"]
BORDER = P["line"]
ACCENT = P["accent"]
BG_PANEL = P["panel"]


def qss(p):
    return f"""
* {{ font-family: "Segoe UI"; font-size: 10pt; color: {p['text']}; }}
QMainWindow, QWidget#root {{ background: {p['bg']}; }}
QDialog, QMessageBox, QFileDialog, QInputDialog, QColorDialog {{ background: {p['panel']}; color: {p['text']}; }}
QMessageBox QLabel, QDialog QLabel {{ color: {p['text']}; background: transparent; }}
QDialog QPushButton, QMessageBox QPushButton {{ min-width: 80px; }}
QToolTip {{ background: {p['panel2']}; color: {p['text']}; border: 1px solid {p['accent']}; padding: 4px; }}
QFrame#titleBar {{ background: {p['side']}; border-bottom: 1px solid {p['line']}; }}
QLabel#appTitle {{ font-weight: 600; }}
QToolButton#winBtn, QToolButton#winClose {{ background: transparent; border: none; border-radius: 0; }}
QToolButton#winBtn:hover {{ background: {p['panel2']}; }}
QToolButton#winClose:hover {{ background: #e81123; }}
QFrame#card, QFrame#header {{ background: {p['panel']}; border: 1px solid {p['line']}; border-radius: 10px; }}
QLabel#cardTitle {{ color: {p['muted']}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; background: transparent; }}
QLabel#hint, QLabel#muted {{ color: {p['muted']}; background: transparent; }}
QLabel#big {{ font-size: 15pt; font-weight: 600; background: transparent; }}
QLabel#tileVal {{ font-size: 15pt; font-weight: 600; background: transparent; }}
QLabel#tileCap {{ color: {p['muted']}; font-size: 8pt; background: transparent; }}
QFrame#tile {{ background: {p['panel']}; border: 1px solid {p['line']}; border-radius: 10px; }}
QLabel#pill {{ background: {p['panel2']}; border: 1px solid {p['line']}; border-radius: 10px; padding: 2px 10px; }}
QLabel {{ background: transparent; }}
QPushButton, QToolButton {{ background: {p['panel2']}; color: {p['text']}; border: 1px solid {p['line']};
    border-radius: 7px; padding: 5px 12px; }}
QPushButton:hover, QToolButton:hover {{ border-color: {p['accent']}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {p['line']}; }}
QPushButton:checked, QToolButton:checked {{ background: {p['accent']}; color: #ffffff; border-color: {p['accent']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {p['muted']}; }}
QPushButton#primary {{ background: {p['accent']}; color: #ffffff; font-weight: 600; border-color: {p['accent']}; }}
QPushButton#primary:hover {{ background: {QColor(p['accent']).lighter(115).name()}; }}
QPushButton#primary:disabled {{ background: {p['line']}; color: {p['muted']}; border-color: {p['line']}; }}
QPushButton#danger {{ background: transparent; color: {ERR}; border-color: {ERR}; }}
QPushButton#chip, QToolButton#chip {{ padding: 3px 8px; border-radius: 6px; }}
QToolButton#seg {{ border-radius: 0; border-left: none; padding: 5px 12px; }}
QToolButton#segFirst {{ border-top-right-radius: 0; border-bottom-right-radius: 0; padding: 5px 12px; }}
QToolButton#segLast {{ border-top-left-radius: 0; border-bottom-left-radius: 0; border-left: none; padding: 5px 12px; }}
QToolButton#add {{ font-size: 8.5pt; padding: 6px 2px; text-align: center; border-radius: 8px; }}
QPushButton#intStep {{ padding: 0; min-width: 0; }}
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox {{ background: {p['panel2']}; color: {p['text']};
    border: 1px solid {p['line']}; border-radius: 7px; padding: 4px 6px; selection-background-color: {p['accent']};
    selection-color: #ffffff; }}
QSpinBox {{ color: {p['text']}; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {p['accent']}; }}
QComboBox QAbstractItemView {{ background: {p['panel']}; color: {p['text']}; border: 1px solid {p['line']};
    selection-background-color: {p['accent']}; selection-color: #ffffff; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QPlainTextEdit#log {{ background: {p['log_bg']}; color: {p['log_fg']}; font-family: Consolas, monospace; font-size: 9pt; }}
QListWidget, QTreeWidget, QTableWidget {{ background: {p['panel']}; color: {p['text']}; border: none;
    outline: none; alternate-background-color: {p['panel2']}; }}
QListWidget::item, QTreeWidget::item {{ padding: 5px 6px; border-radius: 6px; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {QColor(p['accent']).darker(170).name() if NAME == 'dark' else QColor(p['accent']).lighter(175).name()};
    color: {p['text']}; border: 1px solid {p['accent']}; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {p['panel2']}; }}
QHeaderView::section {{ background: {p['panel2']}; color: {p['muted']}; border: none; padding: 4px; }}
QMenu {{ background: {p['panel']}; color: {p['text']}; border: 1px solid {p['line']}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {p['accent']}; color: #ffffff; }}
QMenu::item:disabled {{ color: {p['muted']}; }}
QMenu::separator {{ height: 1px; background: {p['line']}; margin: 4px 6px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: {p['line']}; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QProgressBar {{ background: {p['panel2']}; border: 1px solid {p['line']}; border-radius: 5px; height: 8px;
    text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 4px; }}
QCheckBox {{ background: transparent; spacing: 6px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {p['line']}; border-radius: 4px; background: {p['panel2']}; }}
QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent']}; image: none; }}
QTabWidget::pane {{ border: 1px solid {p['line']}; border-radius: 8px; background: {p['panel']}; }}
QTabBar::tab {{ background: {p['panel2']}; color: {p['muted']}; padding: 6px 12px; border-top-left-radius: 6px;
    border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {p['panel']}; color: {p['text']}; }}
QGroupBox {{ border: 1px solid {p['line']}; border-radius: 8px; margin-top: 14px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {p['muted']}; }}
QStatusBar, QFrame#statusbar {{ background: {p['side']}; border-top: 1px solid {p['line']}; }}
"""


def palette(p):
    pal = QPalette(QColor(p["bg"]))
    roles = {QPalette.Window: p["bg"], QPalette.WindowText: p["text"], QPalette.Base: p["panel2"],
             QPalette.AlternateBase: p["panel"], QPalette.Text: p["text"], QPalette.Button: p["panel2"],
             QPalette.ButtonText: p["text"], QPalette.Highlight: p["accent"], QPalette.HighlightedText: "#ffffff",
             QPalette.PlaceholderText: p["muted"], QPalette.ToolTipBase: p["panel2"], QPalette.ToolTipText: p["text"],
             QPalette.BrightText: "#ffffff", QPalette.Link: p["accent"]}
    for grp in (QPalette.Active, QPalette.Inactive):
        for r, c in roles.items():
            pal.setColor(grp, r, QColor(c))
    for r, c in roles.items():
        pal.setColor(QPalette.Disabled, r, QColor(c))
    for r in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, r, QColor(p["muted"]))
    return pal


def apply(app, name):
    """Тема на всё приложение сразу: QSS, палитра, цвета для рамки окна."""
    global NAME, P, TEXT, TEXT_DIM, BORDER, ACCENT, BG_PANEL
    NAME = name if name in THEMES else "dark"
    P = dict(THEMES[NAME])
    TEXT, TEXT_DIM, BORDER, ACCENT, BG_PANEL = P["text"], P["muted"], P["line"], P["accent"], P["panel"]
    app.setPalette(palette(P))
    app.setStyleSheet(qss(P))
    for w in app.topLevelWidgets():
        w.update()
        _dwm(w)
    return P


# ---------- значок ----------
def icon_pixmap(size):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64.0
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#4f8cff"))
    p.drawRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s), 14 * s, 14 * s)
    p.setBrush(QColor("#0e1220"))
    p.drawRoundedRect(QRectF(10 * s, 12 * s, 44 * s, 40 * s), 7 * s, 7 * s)
    pen = QPen(QColor("#ffffff"), 4.2 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    path = QPainterPath(QPointF(16 * s, 40 * s))
    path.lineTo(QPointF(26 * s, 28 * s))
    path.lineTo(QPointF(34 * s, 36 * s))
    path.lineTo(QPointF(47 * s, 21 * s))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#3ecf8e"))
    p.drawEllipse(QPointF(47 * s, 21 * s), 3.6 * s, 3.6 * s)
    p.end()
    return pm


def app_icon():
    ic = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(icon_pixmap(sz))
    return ic


# ---------- системная полоса диалогов Windows ----------
def _dwm(w):
    if sys.platform != "win32":
        return
    try:
        if w.windowFlags() & Qt.FramelessWindowHint:
            return
        import ctypes
        hwnd = int(w.winId())
        dark = ctypes.c_int(1 if NAME == "dark" else 0)
        dw = ctypes.windll.dwmapi
        if dw.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4):
            dw.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark), 4)

        def bgr(h):
            c = QColor(h)
            return ctypes.c_int(c.red() | (c.green() << 8) | (c.blue() << 16))
        cap, txt = bgr(P["panel"]), bgr(P["text"])
        dw.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cap), 4)
        dw.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(txt), 4)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
    except Exception:                                  # noqa: BLE001
        pass


class DialogBar(QObject):
    """Фильтр на всё приложение: окна с системной рамкой (диалоги) — в цвета темы до показа."""

    def eventFilter(self, obj, ev):                    # noqa: N802 (Qt)
        if ev.type() == QEvent.Show and obj.isWidgetType() and obj.isWindow():
            if obj.windowType() in (Qt.Window, Qt.Dialog, Qt.Tool):
                _dwm(obj)
        return False
