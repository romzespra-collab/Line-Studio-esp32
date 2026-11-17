"""line_studio.py  v0.1.0 — LineStudio: редактор экранов для плат ESP32 (ядро: запуск, настройки, журнал, проверка).

Журнал:
v0.1.0: первая версия — редактор экранов (Вид 2 «Пульт»): холст с превью из движка платы (LVGL в DLL),
        экраны/слои/блоки, свойства, Правка/Проба/Карта, Live по USB, «Залить» (arduino-cli + ядро ESP32),
        паспорта плат (boards/), Guition 4848S040 (S3) и JC4880P443C (P4).

Запуск: двойной клик по line_studio.pyw (библиотеки поставятся сами). Проверка: python line_studio.py --selftest
"""
import importlib
import importlib.util
import json
import logging
import logging.handlers
import os
import queue
import subprocess
import sys

APP_NAME = "LineStudio"
VERSION = "0.1.0"
REPO_OWNER = "romzespra-collab"
REPO_NAME = "Line-Studio-esp32"

FROZEN = getattr(sys, "frozen", False)
APP_ROOT = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)
CONFIG = os.path.join(APP_ROOT, "config.json")
SECRETS = os.path.join(APP_ROOT, "secrets.json")
PROJECTS = os.path.join(APP_ROOT, "projects")
LOG_FILE = os.path.join(APP_ROOT, "line_studio.log")

REQUIRED = (("PySide6", "PySide6>=6.5"), ("serial", "pyserial>=3.5"), ("fontTools", "fonttools>=4.40"))


# ---------- авто-установка библиотек ----------
def _missing():
    return [pip for mod, pip in REQUIRED if importlib.util.find_spec(mod) is None]


def pip_install(pips, console=True):
    py = sys.executable
    if py.lower().endswith("pythonw.exe"):
        cand = py[:-len("pythonw.exe")] + "python.exe"
        if os.path.exists(cand):
            py = cand
    win = sys.platform == "win32"
    flags = (0x10 if console else 0x08000000) if win else 0      # консоль с ходом установки / без окна
    hidden = 0x08000000 if win else 0
    base = [py, "-m", "pip", "install", "--disable-pip-version-check"]
    if subprocess.call([py, "-m", "pip", "--version"], creationflags=hidden) != 0:
        subprocess.call([py, "-m", "ensurepip", "--upgrade"], creationflags=flags)
    rc = subprocess.call(base + list(pips), creationflags=flags)
    if rc:
        rc = subprocess.call(base + ["--user"] + list(pips), creationflags=flags)
    importlib.invalidate_caches()
    return rc == 0


def ensure_packages():
    if FROZEN or "--selftest" in sys.argv:
        return
    need = _missing()
    if not need:
        return
    pip_install(need, console=True)
    still = _missing()
    if still:
        msg = ("Не удалось поставить библиотеки:\n  " + "\n  ".join(still) +
               "\n\nПоставьте вручную:\n  pip install " + " ".join(still))
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, APP_NAME, 0x10)
        else:
            print(msg)
        sys.exit(1)


# ---------- настройки ----------
DEFAULT_CONFIG = {"theme": "dark", "geometry": "", "splitter": "", "vsplit": "", "project": "", "zoom": 0,
                  "port": "", "chip_variant": {}, "update": {"token": "", "auto": True, "branch": "main",
                                                             "every_h": 12}}


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    for i in range(6):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:                        # WinError 5/32 — файл занят: подождать и ещё раз
            import time
            time.sleep(0.15 * (i + 1))
    os.replace(tmp, path)


def _read_json(path):
    """Битый JSON не читаем как пустой: берём .bak, иначе — None (и не записываем поверх)."""
    for p in (path, path + ".bak"):
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:                          # noqa: BLE001
                continue
    return None


def write_json(path, data):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if os.path.exists(path):
        try:
            import shutil
            shutil.copyfile(path, path + ".bak")
        except Exception:                              # noqa: BLE001
            pass
    _atomic_write(path, text)


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    d = _read_json(CONFIG)
    if isinstance(d, dict):
        cfg.update(d)
    return cfg


def save_config(cfg):
    write_json(CONFIG, cfg)


def load_secrets():
    d = _read_json(SECRETS)
    return d if isinstance(d, dict) else {}


def save_secrets(d):
    write_json(SECRETS, d)


# ---------- журнал ----------
DONE = object()
log_q = queue.Queue()


class _QueueHandler(logging.Handler):
    def emit(self, rec):
        msg = rec.getMessage()
        for k in ("password", "pass", "token"):
            if k + "=" in msg:
                import re
                msg = re.sub(rf"({k}=)\S+", r"\1***", msg)
        log_q.put(msg)


def setup_log():
    lg = logging.getLogger("ls")
    if lg.handlers:
        return lg
    lg.setLevel(logging.INFO)
    lg.addHandler(_QueueHandler())
    try:
        fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
        lg.addHandler(fh)
    except Exception:                                  # noqa: BLE001
        pass
    return lg


log = setup_log()


# ---------- проекты ----------
def project_path(pid):
    return os.path.join(PROJECTS, pid + ".json")


def list_projects():
    os.makedirs(PROJECTS, exist_ok=True)
    out = []
    for fn in sorted(os.listdir(PROJECTS)):
        if fn.endswith(".json"):
            d = _read_json(os.path.join(PROJECTS, fn))
            if isinstance(d, dict):
                out.append((fn[:-5], d.get("name", fn[:-5]), d.get("board", "")))
    return out


def read_project(pid):
    d = _read_json(project_path(pid))
    return d if isinstance(d, dict) else None


def save_project(pid, data):
    os.makedirs(PROJECTS, exist_ok=True)
    write_json(project_path(pid), data)


# ---------- проверка ----------
def selftest():
    lines, ok = [], True

    def chk(name, fn):
        nonlocal ok
        try:
            r = fn()
            lines.append(f"✓ {name}" + (f": {r}" if r else ""))
        except Exception as e:                         # noqa: BLE001
            ok = False
            lines.append(f"✗ {name}: {e}")

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    chk("PySide6", lambda: importlib.import_module("PySide6.QtWidgets") and "")
    chk("pyserial", lambda: importlib.import_module("serial") and "")
    chk("fontTools", lambda: importlib.import_module("fontTools.subset") and "")
    from modules import mod_build, mod_engine, mod_project
    for m in ("mod_project", "mod_engine", "mod_build", "mod_link", "mod_stage"):
        chk(m, lambda m=m: importlib.import_module("modules." + m) and "")
    chk("app.theme / рамка / обновление", lambda: [importlib.import_module("app." + m) for m in
                                                   ("theme", "window_frame", "int_field", "gh_update",
                                                    "gh_update_qt")] and "")
    boards = mod_build.load_boards()
    chk("платы", lambda: ", ".join(b["id"] for b in boards) or (_ for _ in ()).throw(RuntimeError("нет плат")))

    def eng():
        e = mod_engine.Engine()
        b = boards[0]
        e.init(b["w"], b["h"])
        p = mod_project.clean(mod_project.new_project(b))
        r, err = e.load(mod_project.runtime_json(p))
        if r:
            raise RuntimeError(err)
        e.redraw()
        return f"{os.path.basename(e.path)} v{e.version}, {b['w']}×{b['h']}"
    chk("движок превью", eng)
    chk("окно", lambda: importlib.import_module("line_studio_qt") and "")
    text = f"{APP_NAME} v{VERSION} — проверка\n" + "\n".join(lines) + f"\nИТОГ: {'OK' if ok else 'ОШИБКИ'}\n"
    print(text)
    try:
        open(os.path.join(APP_ROOT, "selftest.txt"), "w", encoding="utf-8").write(text)
    except Exception:                                  # noqa: BLE001
        pass
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    ensure_packages()
    import line_studio_qt
    sys.exit(line_studio_qt.run())


if __name__ == "__main__":
    main()
