"""mod_project.py  v0.1.0 — проект LineStudio: экраны и слои, каталог блоков, заготовки, проверка.

Журнал:
v0.1.0: первая версия — формат 1 (docs/FORMAT.md), 8 видов блоков, 5 заготовок экранов, чистка и проверка
        ссылок, отмена/повтор (история снимков).

Проект — обычный dict, сохраняется как JSON (projects/<id>.json) и в таком же виде уходит в прошивку и в
движок превью. Всё, что знает рантайм на C (runtime/ls_runtime.c), описано здесь в CATALOG — редактор строит
по нему панель свойств.
"""
import copy
import json
import re
import time
import uuid

FORMAT = 1

# Свойство: (ключ, вид, подпись, доп.) — вид: text, int, color, choice, bool, font, format, source, screen
FONTS = (("medium", "Обычный"), ("bold", "Жирный"), ("light", "Тонкий"))
ALIGN = (("left", "Слева"), ("center", "По центру"), ("right", "Справа"))
SOURCES = (("static", "Число"), ("seconds", "Секунды"), ("minutes", "Минуты"), ("hours", "Часы (12)"),
           ("day", "Сутки"), ("brightness", "Яркость"))
ANIMS = (("fade", "Проявление"), ("left", "Влево"), ("right", "Вправо"), ("up", "Вверх"), ("down", "Вниз"),
         ("over", "Наплыв"), ("none", "Сразу"))
CLOCK_FORMATS = ("{HH}:{mm}", "{HH}:{mm}:{ss}", "{H}:{mm}", "{h}:{mm} {AMPM}", "{HH}{mm}")
DATE_FORMATS = ("{dddd}, {d} {MMMMg}", "{^dddd}, {d} {^MMMMg}", "{ddd} {d} {MMM}", "{dd}.{MM}.{YYYY}",
                "{d} {MMMMg} {YYYY}", "{^ddd} {d}")

_TEXT = [("font", "font", "Шрифт"), ("size", "int", "Размер", (6, 400)), ("color", "color", "Цвет"),
         ("align", "choice", "Выравнивание", ALIGN), ("spacing", "int", "Между буквами", (-20, 60))]

CATALOG = {
    "clock": {"name": "Часы", "icon": "clock", "group": "Время", "size": (300, 0),
              "props": [("format", "format", "Формат", CLOCK_FORMATS)] + _TEXT,
              "defaults": {"format": "{HH}:{mm}", "font": "bold", "size": 96, "color": "#FFFFFF", "align": "center",
                           "spacing": 0}},
    "date": {"name": "Дата", "icon": "date", "group": "Время", "size": (300, 0),
             "props": [("format", "format", "Формат", DATE_FORMATS)] + _TEXT,
             "defaults": {"format": "{dddd}, {d} {MMMMg}", "font": "medium", "size": 26, "color": "#9AA3B5",
                          "align": "center", "spacing": 0}},
    "analog": {"name": "Стрелки", "icon": "analog", "group": "Время", "size": (240, 240), "square": True,
               "props": [("face", "color", "Циферблат"), ("tick_color", "color", "Деления"),
                         ("hour_color", "color", "Часовая"), ("min_color", "color", "Минутная"),
                         ("sec_color", "color", "Секундная"), ("ticks", "bool", "Деления"),
                         ("seconds", "bool", "Секундная стрелка")],
               "defaults": {"face": "#14161B", "tick_color": "#C9CED8", "hour_color": "#FFFFFF",
                            "min_color": "#FFFFFF", "sec_color": "#FF5D6C", "ticks": True, "seconds": True}},
    "label": {"name": "Текст", "icon": "text", "group": "Основа", "size": (240, 0),
              "props": [("text", "text", "Текст")] + _TEXT + [("wrap", "bool", "Переносить строки")],
              "defaults": {"text": "Текст", "font": "medium", "size": 32, "color": "#FFFFFF", "align": "left",
                           "spacing": 0, "wrap": False}},
    "rect": {"name": "Плашка", "icon": "rect", "group": "Основа", "size": (200, 120),
             "props": [("color", "color", "Цвет"), ("grad", "color", "Градиент вниз"),
                       ("radius", "int", "Скругление", (0, 999)), ("border", "int", "Рамка", (0, 40)),
                       ("border_color", "color", "Цвет рамки")],
             "defaults": {"color": "#23262E", "grad": "", "radius": 18, "border": 0, "border_color": "#4F8CFF"}},
    "button": {"name": "Кнопка", "icon": "button", "group": "Основа", "size": (180, 60),
               "props": [("text", "text", "Текст"), ("font", "font", "Шрифт"), ("size", "int", "Размер", (6, 200)),
                         ("color", "color", "Цвет"), ("text_color", "color", "Цвет текста"),
                         ("radius", "int", "Скругление", (0, 999))],
               "defaults": {"text": "Кнопка", "font": "medium", "size": 24, "color": "#4F8CFF",
                            "text_color": "#FFFFFF", "radius": 16}},
    "arc": {"name": "Дуга", "icon": "arc", "group": "Приборы", "size": (240, 240), "square": True,
            "props": [("source", "source", "Показывает", SOURCES), ("value", "int", "Число, %", (0, 100)),
                      ("thick", "int", "Толщина", (1, 120)), ("color", "color", "Цвет"),
                      ("track", "color", "Дорожка"), ("rotation", "int", "Начало, °", (0, 359)),
                      ("sweep", "int", "Размах, °", (1, 360)), ("rounded", "bool", "Круглые концы")],
            "defaults": {"source": "seconds", "value": 60, "thick": 12, "color": "#4F8CFF", "track": "#1C2230",
                         "rotation": 270, "sweep": 360, "rounded": True}},
    "slider": {"name": "Ползунок", "icon": "slider", "group": "Приборы", "size": (300, 22),
               "props": [("source", "source", "Управляет", (("brightness", "Яркость"), ("static", "Ничем"))),
                         ("value", "int", "Начально, %", (0, 100)), ("color", "color", "Цвет"),
                         ("track", "color", "Дорожка"), ("knob", "color", "Ручка")],
               "defaults": {"source": "brightness", "value": 50, "color": "#4F8CFF", "track": "#2A2E38",
                            "knob": "#FFFFFF"}},
}
GROUPS = ("Время", "Основа", "Приборы")
COMMON = [("x", "int", "X", (-2000, 4000)), ("y", "int", "Y", (-2000, 4000)), ("w", "int", "Ширина", (0, 4000)),
          ("h", "int", "Высота", (0, 4000)), ("opa", "int", "Видимость, %", (0, 100))]

LANGS = (("ru", "Русский"), ("uk", "Українська"), ("en", "English"))
ZONES = {"Киев": "EET-2EEST,M3.5.0/3,M10.5.0/4", "Москва": "MSK-3", "Варшава": "CET-1CEST,M3.5.0,M10.5.0/3",
         "Лондон": "GMT0BST,M3.5.0/1,M10.5.0", "Нью-Йорк": "EST5EDT,M3.2.0,M11.1.0", "UTC": "UTC0"}


def new_id(prefix="w"):
    return f"{prefix}{uuid.uuid4().hex[:6]}"


def widget(kind, x=0, y=0, **over):
    c = CATALOG[kind]
    w = {"id": new_id(), "type": kind, "name": c["name"], "x": int(x), "y": int(y),
         "w": c["size"][0], "h": c["size"][1]}
    w.update(copy.deepcopy(c["defaults"]))
    w.update(over)
    return w


def screen(name="Экран", bg="#000000", widgets=None, sid=None):
    return {"id": sid or new_id("s"), "name": name, "bg": bg, "swipe": {}, "back": True,
            "widgets": widgets or []}


# ---------- заготовки экранов (под размер платы) ----------
def tpl_digital(W, H):
    s = min(W, H)
    return screen("Часы", "#05070C", [
        widget("clock", 0, H // 2 - s * 26 // 100, w=W, size=s * 30 // 100),
        widget("date", 0, H // 2 + s * 10 // 100, w=W, size=max(14, s * 6 // 100)),
    ])


def tpl_ring(W, H):
    s = min(W, H) - 40
    x0, y0 = (W - s) // 2, (H - s) // 2
    return screen("Кольцо", "#000000", [
        widget("arc", x0, y0, w=s, h=s, thick=max(6, s // 40)),
        widget("clock", 0, H // 2 - s * 22 // 100, w=W, size=s * 26 // 100),
        widget("date", 0, H // 2 + s * 9 // 100, w=W, size=max(14, s * 6 // 100), format="{^ddd} {d} {^MMM}",
               spacing=2),
    ])


def tpl_analog(W, H):
    s = min(W, H) - 40
    return screen("Стрелки", "#000000", [widget("analog", (W - s) // 2, (H - s) // 2, w=s, h=s)])


def tpl_settings(W, H):
    pad = max(20, W // 16)
    return screen("Яркость", "#0E1015", [
        widget("label", pad, pad, w=W - 2 * pad, text="Яркость", size=max(20, H // 14), font="bold"),
        widget("slider", pad, H // 2 - 14, w=W - 2 * pad, h=28),
        widget("button", (W - 180) // 2, H - pad - 60, w=180, h=60, text="Назад",
               color="#2A2E38", link={"to": "@back", "anim": "fade"}),
    ])


def tpl_blank(W, H):
    return screen("Пустой", "#000000", [])


TEMPLATES = (("digital", "Цифровые часы", tpl_digital), ("ring", "Кольцо секунд", tpl_ring),
             ("analog", "Стрелки", tpl_analog), ("settings", "Яркость", tpl_settings), ("blank", "Пустой", tpl_blank))


def new_project(board, name="Мой экран"):
    W, H = board["w"], board["h"]
    home = tpl_ring(W, H)
    home["name"] = "Главный"
    home["id"] = "main"
    st = tpl_settings(W, H)
    st["id"] = "bright"
    home["swipe"] = {"up": "bright"}
    return {"format": FORMAT, "name": name, "board": board["id"], "home": "main", "rev": 0,
            "settings": {"lang": "ru", "zone": "Киев", "tz": ZONES["Киев"], "wifi": False, "brightness": 80},
            "screens": [home, st]}


# ---------- чистка, проверка ----------
def clean(p):
    """Привести проект к формату: недостающее — из умолчаний, ссылки на несуществующие экраны — убрать."""
    p.setdefault("format", FORMAT)
    p.setdefault("name", "Проект")
    p.setdefault("rev", 0)
    st = p.setdefault("settings", {})
    st.setdefault("lang", "ru")
    st.setdefault("zone", "Киев")
    st.setdefault("tz", ZONES.get(st["zone"], ZONES["Киев"]))
    st.setdefault("wifi", False)
    st.setdefault("brightness", 80)
    scr = p.setdefault("screens", [])
    if not scr:
        scr.append(screen("Главный", sid="main"))
    ids = {s.get("id") for s in scr}
    if p.get("home") not in ids:
        p["home"] = scr[0]["id"]
    for s in scr:
        s.setdefault("id", new_id("s"))
        s.setdefault("name", "Экран")
        s.setdefault("bg", "#000000")
        s.setdefault("back", True)
        sw = s.setdefault("swipe", {})
        for k in list(sw):
            if sw[k] not in ids and sw[k] != "@back":
                del sw[k]
        for w in s.setdefault("widgets", []):
            w.setdefault("id", new_id())
            c = CATALOG.get(w.get("type"))
            if c:
                for k, v in c["defaults"].items():
                    w.setdefault(k, copy.deepcopy(v))
                w.setdefault("name", c["name"])
            for k in ("x", "y", "w", "h"):
                w[k] = int(w.get(k, 0) or 0)
            ln = w.get("link")
            if ln and ln.get("to") not in ids and ln.get("to") != "@back":
                w.pop("link", None)
    return p


def problems(p, board=None):
    """Что не так (для журнала перед Load): список строк."""
    out = []
    for s in p.get("screens", []):
        for w in s.get("widgets", []):
            if w.get("type") not in CATALOG:
                out.append(f"⚠ «{s['name']}»: неизвестный блок «{w.get('type')}» — плата его пропустит")
            if board:
                if w["x"] >= board["w"] or w["y"] >= board["h"] or w["x"] + max(w["w"], 1) <= 0:
                    out.append(f"⚠ «{s['name']}» / «{w.get('name')}»: за краем экрана")
    return out


def runtime_json(p):
    """То, что уходит в рантайм (плата, превью): без лишнего, одной строкой."""
    q = {k: p[k] for k in ("format", "name", "home", "settings", "screens") if k in p}
    q = copy.deepcopy(q)
    q["settings"] = {"lang": p.get("settings", {}).get("lang", "ru")}
    return json.dumps(q, ensure_ascii=False, separators=(",", ":"))


def used_chars(p):
    """Буквы, которые проект показывает (для урезания шрифтов)."""
    chars = set()
    for s in p.get("screens", []):
        for w in s.get("widgets", []):
            for k in ("text", "format"):
                chars.update(str(w.get(k, "")))
    return chars


def used_fonts(p):
    f = set()
    for s in p.get("screens", []):
        for w in s.get("widgets", []):
            if "font" in w:
                f.add(w["font"])
    return f or {"medium"}


def find_widget(p, wid):
    for s in p.get("screens", []):
        for w in s.get("widgets", []):
            if w.get("id") == wid:
                return s, w
    return None, None


def find_screen(p, sid):
    for s in p.get("screens", []):
        if s.get("id") == sid:
            return s
    return None


def links(p):
    """Связи для карты: (из экрана, из блока или None, на экран, вид: tap/swipe-left/...)."""
    out = []
    for s in p.get("screens", []):
        for w in s.get("widgets", []):
            to = (w.get("link") or {}).get("to")
            if to and to != "@back":
                out.append((s["id"], w["id"], to, "tap"))
        for d, to in (s.get("swipe") or {}).items():
            if to and to != "@back":
                out.append((s["id"], None, to, "swipe-" + d))
    return out


def slug(name):
    s = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return (s or "project")[:40] + "-" + time.strftime("%y%m%d%H%M%S")


class History:
    """Отмена / повтор: снимки проекта (JSON-строки)."""

    def __init__(self, limit=200):
        self.undo, self.redo, self.limit = [], [], limit

    def push(self, p):
        snap = json.dumps(p, ensure_ascii=False, sort_keys=True)
        if self.undo and self.undo[-1] == snap:
            return
        self.undo.append(snap)
        self.redo.clear()
        del self.undo[:-self.limit]

    def back(self, cur):
        snap = json.dumps(cur, ensure_ascii=False, sort_keys=True)
        while self.undo and self.undo[-1] == snap:      # снимок без изменений — пропустить
            self.undo.pop()
        if not self.undo:
            return None
        self.redo.append(snap)
        return json.loads(self.undo.pop())

    def fwd(self, cur):
        if not self.redo:
            return None
        self.undo.append(json.dumps(cur, ensure_ascii=False, sort_keys=True))
        return json.loads(self.redo.pop())
