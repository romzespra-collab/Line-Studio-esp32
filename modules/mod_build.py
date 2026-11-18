"""mod_build.py  v0.2.0 — платы, сборка прошивки и заливка: arduino-cli, ядро ESP32, шрифты, esptool.

Журнал:
v0.2.0: картинки в прошивку (images_data.h, RGB565 / RGB565A8 под размер блока), шрифт значков — только
        использованные значки, погода (LS_WEATHER, города в build_info.h), платы без PSRAM.
v0.1.0: первая версия — паспорта плат (boards/*/board.json), инструменты в своей папке tools/ (или уже
        установленное ядро Arduino15 нужной версии — чтобы не качать гигабайты второй раз), копия прошивки с
        проектом в build/<плата>/LineFirmware, урезанные шрифты (только нужные буквы), сборка, заливка, копия
        прошивки платы (read-flash) перед первой заливкой.
"""
import glob
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
BUILD = os.path.join(ROOT, "build")
BACKUPS = os.path.join(ROOT, "backups")
FIRMWARE = os.path.join(ROOT, "firmware")
CLI_VERSION = "1.3.1"
ESP32_INDEX = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
EXE = ".exe" if sys.platform == "win32" else ""
FW_VERSION = "0.2.0"


class BuildError(Exception):
    pass


# ---------- платы ----------
def load_boards():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "boards", "*", "board.json"))):
        try:
            b = json.load(open(p, encoding="utf-8"))
            b["dir"] = os.path.dirname(p)
            out.append(b)
        except Exception as e:                         # noqa: BLE001
            print(f"плата {p}: {e}")
    return out


def board_by_id(boards, bid):
    for b in boards:
        if b["id"] == bid:
            return b
    return boards[0] if boards else None


# ---------- инструменты ----------
def _decode(b):
    for enc in ("utf-8", "oem", "cp866", "cp1251"):
        try:
            return b.decode(enc)
        except Exception:                              # noqa: BLE001
            pass
    return b.decode("utf-8", "replace")


def _download(url, dst, log, progress=None):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "LineStudio"})
    tmp = dst + ".part"
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress and total:
                progress(got * 100 // total)
    os.replace(tmp, dst)
    log(f"✓ скачано {os.path.basename(dst)} ({got // 1024} КБ)")


def arduino15_candidates():
    c = [os.path.join(TOOLS, "arduino15")]
    if sys.platform == "win32":
        c.append(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Arduino15"))
    elif sys.platform == "darwin":
        c.append(os.path.expanduser("~/Library/Arduino15"))
    else:
        c.append(os.path.expanduser("~/.arduino15"))
    return c


def core_dir(data, version):
    return os.path.join(data, "packages", "esp32", "hardware", "esp32", version)


class Tools:
    """arduino-cli и ядро ESP32. Всё своё — в tools/; уже установленное ядро нужной версии берётся как есть."""

    def __init__(self, log=print):
        self.log = log
        self.cli = os.path.join(TOOLS, "arduino-cli", "arduino-cli" + EXE)
        if not os.path.exists(self.cli) and shutil.which("arduino-cli"):
            self.cli = shutil.which("arduino-cli")
        self.cfg = os.path.join(TOOLS, "arduino-cli.yaml")

    def data_dir(self, version):
        for d in arduino15_candidates():
            if os.path.isdir(core_dir(d, version)):
                return d
        return os.path.join(TOOLS, "arduino15")

    def write_cfg(self, version):
        data = self.data_dir(version)
        os.makedirs(TOOLS, exist_ok=True)
        y = ("board_manager:\n  additional_urls:\n    - " + ESP32_INDEX + "\n"
             f"directories:\n  data: {data}\n  downloads: {os.path.join(data, 'staging')}\n"
             f"  user: {os.path.join(TOOLS, 'sketchbook')}\n")
        open(self.cfg, "w", encoding="utf-8").write(y)
        return data

    def ready(self, version):
        return os.path.exists(self.cli) and any(os.path.isdir(core_dir(d, version)) for d in arduino15_candidates())

    def ensure(self, version, progress=None, cancel=None):
        if not os.path.exists(self.cli):
            self.install_cli(progress)
        data = self.write_cfg(version)
        if not os.path.isdir(core_dir(data, version)):
            self.log(f"⏳ ставлю ядро ESP32 {version} в {data} — первый раз 1,5–3 ГБ, 5–20 минут")
            self.run([self.cli, "--config-file", self.cfg, "core", "update-index"], cancel=cancel)
            self.run([self.cli, "--config-file", self.cfg, "core", "install", f"esp32:esp32@{version}"], cancel=cancel,
                     line_cb=lambda s: progress and _pct(s, progress))
            self.log(f"✓ ядро ESP32 {version} установлено")
        else:
            self.log(f"✓ ядро ESP32 {version}: {data}")

    def install_cli(self, progress=None):
        plat = {"win32": "Windows_64bit.zip", "darwin": "macOS_64bit.tar.gz"}.get(sys.platform, "Linux_64bit.tar.gz")
        url = f"https://github.com/arduino/arduino-cli/releases/download/v{CLI_VERSION}/arduino-cli_{CLI_VERSION}_{plat}"
        d = os.path.join(TOOLS, "arduino-cli")
        os.makedirs(d, exist_ok=True)
        arc = os.path.join(d, os.path.basename(url))
        self.log(f"⏳ скачиваю arduino-cli {CLI_VERSION}")
        _download(url, arc, self.log, progress)
        if arc.endswith(".zip"):
            with zipfile.ZipFile(arc) as z:
                z.extract("arduino-cli" + EXE, d)
        else:
            import tarfile
            with tarfile.open(arc) as t:
                t.extract("arduino-cli", d, filter="data")
        os.remove(arc)
        self.cli = os.path.join(d, "arduino-cli" + EXE)
        self.log("✓ arduino-cli готов")

    def esptool(self, version):
        data = self.data_dir(version)
        cand = sorted(glob.glob(os.path.join(data, "packages", "esp32", "tools", "esptool_py", "*", "esptool" + EXE)))
        if cand:
            return [cand[-1]]
        py = sorted(glob.glob(os.path.join(data, "packages", "esp32", "tools", "esptool_py", "*", "esptool.py")))
        if py:
            return [sys.executable, py[-1]]
        raise BuildError("нет esptool: сначала поставьте ядро ESP32 (первая заливка ставит его сама)")

    def run(self, cmd, cancel=None, line_cb=None, cwd=None):
        """Запуск с выводом построчно в журнал. Ошибка → BuildError с хвостом вывода."""
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd,
                             creationflags=NO_WINDOW)
        tail = []
        buf = b""
        while True:
            ch = p.stdout.read1(4096) if hasattr(p.stdout, "read1") else p.stdout.read(4096)
            if not ch:
                break
            buf += ch
            parts = re.split(rb"[\r\n]", buf)
            buf = parts.pop()
            for raw in parts:
                s = _decode(raw).rstrip()
                if not s:
                    continue
                tail.append(s)
                del tail[:-40]
                if line_cb:
                    line_cb(s)
            if cancel and cancel():
                p.kill()
                raise BuildError("остановлено")
        rc = p.wait()
        if rc:
            raise BuildError("\n".join(tail[-15:]) or f"код {rc}")
        return tail


def _pct(s, progress):
    m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", s)
    if m:
        progress(min(100, int(float(m.group(1)))))


# ---------- копия прошивки с проектом ----------
def c_bytes(data, per=24):
    out = []
    for i in range(0, len(data), per):
        out.append(",".join(str(b) for b in data[i:i + per]))
    return ",\n".join(out)


def c_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


BASE_CHARS = set(chr(c) for c in range(0x20, 0x7F)) | set(chr(c) for c in range(0x400, 0x460)) | \
    set(chr(c) for c in (0x490, 0x491, 0x2BC, 0xB0, 0xAB, 0xBB, 0x2014, 0x2013, 0x2026, 0x2116, 0x2022))


def subset_font(src, chars):
    """TTF только с нужными буквами (fontTools). Нет fontTools — весь файл (значки — 350 КБ)."""
    data = open(src, "rb").read()
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
        import io
        f = TTFont(io.BytesIO(data))
        opt = subset.Options()
        opt.layout_features = ["kern"]
        opt.name_IDs = []
        opt.notdef_outline = True
        opt.hinting = False
        s = subset.Subsetter(opt)
        s.populate(unicodes=[ord(c) for c in chars])
        s.subset(f)
        b = io.BytesIO()
        f.save(b)
        return b.getvalue()
    except ImportError:
        return data


def write_sketch(project, board, meta, secrets=None, log=print):
    """Копия прошивки с проектом: build/<плата>/LineFirmware. Возвращает путь к скетчу."""
    from . import mod_project as mp
    from .mod_engine import FONT_FILES, FONTS_DIR
    sk = os.path.join(BUILD, board["id"], "LineFirmware")
    os.makedirs(sk, exist_ok=True)
    for old in glob.glob(os.path.join(sk, "*")):
        if os.path.isfile(old):
            os.remove(old)
    shutil.copy(os.path.join(FIRMWARE, "LineFirmware", "LineFirmware.ino"), sk)
    for f in glob.glob(os.path.join(FIRMWARE, "drivers", "*.h")) + glob.glob(os.path.join(ROOT, "runtime", "*.[ch]")):
        shutil.copy(f, sk)
    shutil.copy(os.path.join(board["dir"], board.get("port", "port.h")), os.path.join(sk, "port.h"))
    js = mp.runtime_json(project).encode("utf-8") + bytes(1)
    open(os.path.join(sk, "project_data.h"), "w", encoding="utf-8").write(
        "// Сделано LineStudio из проекта — не править руками.\n#pragma once\n"
        f"static const char LS_PROJECT_JSON[] = {{\n{c_bytes(js)}\n}};\n")
    chars = BASE_CHARS | mp.used_chars(project)
    lines = ["// Сделано LineStudio: шрифты проекта — только используемые, урезанные до нужных букв.", "#pragma once",
             "#include \"ls_runtime.h\""]
    reg = []
    total = 0
    icons = mp.used_icons(project)
    for name in sorted(mp.used_fonts(project)):
        fn = FONT_FILES.get(name)
        if not fn:
            continue
        data = subset_font(os.path.join(FONTS_DIR, fn), icons if name == "icons" else chars)
        total += len(data)
        lines.append(f"static const uint8_t ls_font_{name}[] = {{\n{c_bytes(data)}\n}};")
        reg.append(f"  ls_font_add(\"{name}\", ls_font_{name}, sizeof ls_font_{name});")
    lines.append("static void ls_fonts_register() {\n" + "\n".join(reg) + "\n}")
    open(os.path.join(sk, "fonts_data.h"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    log(f"✓ шрифты: {', '.join(sorted(mp.used_fonts(project)))} — {total // 1024} КБ")
    write_images(project, sk, meta.get("assets_dir", ""), log)
    st = project.get("settings", {})
    wifi = bool(st.get("wifi")) and secrets and secrets.get("ssid")
    weather = bool(wifi) and "weather" in mp.used_types(project)
    cities = st.get("cities") or mp.CITIES_DEFAULT
    city_c = ", ".join(f"{{{c_str(c.get('name', ''))}, {float(c.get('lat', 0)):.4f}f, {float(c.get('lon', 0)):.4f}f}}"
                       for c in cities[:8])
    open(os.path.join(sk, "build_info.h"), "w", encoding="utf-8").write(
        "// Сделано LineStudio — не править руками.\n#pragma once\n"
        f"#define LS_PROJECT_ID {c_str(meta.get('pid', '-'))}\n#define LS_PROJECT_REV {int(meta.get('rev', 0))}\n"
        f"#define LS_TZ {c_str(st.get('tz', 'UTC0'))}\n#define LS_BRIGHT {int(st.get('brightness', 80))}\n"
        f"#define LS_WIFI {1 if wifi else 0}\n#define LS_WEATHER {1 if weather else 0}\n"
        f"#define LS_CITIES {{{city_c}}}\n#define LS_BUILT {c_str(time.strftime('%Y-%m-%dT%H:%M'))}\n")
    if "weather" in mp.used_types(project) and not weather:
        log("⚠ погода есть, а Wi-Fi нет (или не задана сеть) — на плате будет «нет данных»")
    net = os.path.join(sk, "wifi_net.h")
    if wifi:
        with open(net, "w", encoding="utf-8") as f:
            f.write("// Wi-Fi платы — только для этой сборки, в git не попадает.\n#pragma once\n"
                    f"#define LS_WIFI_SSID {c_str(secrets['ssid'])}\n#define LS_WIFI_PASS {c_str(secrets.get('password', ''))}\n")
    return sk


def write_images(project, sk, assets_dir, log=print):
    """images_data.h: каждая картинка — под размер своего блока (одинаковые — один раз)."""
    from . import mod_images
    from . import mod_project as mp
    lines = ["// Сделано LineStudio: картинки проекта под размер блоков — не править руками.", "#pragma once",
             "#include \"ls_runtime.h\""]
    reg, done, total = [], {}, 0
    assets = project.get("assets", {})
    for s in project.get("screens", []):
        for w in s.get("widgets", []):
            if w.get("type") != "image" or w.get("asset") not in assets:
                continue
            key = mp.image_key(w)
            if key in done:
                continue
            path = os.path.join(assets_dir, assets[w["asset"]]["file"])
            rgb, alpha = mod_images.render(path, w["w"], w["h"], w.get("fit", "cover"))
            if rgb is None:
                log(f"⚠ картинка «{assets[w['asset']].get('name')}» не читается — пропущена")
                continue
            n = len(done)
            data = rgb + (alpha or b"")
            total += len(data)
            cf = "LV_COLOR_FORMAT_RGB565A8" if alpha else "LV_COLOR_FORMAT_RGB565"
            lines.append(f"static const uint8_t ls_img_{n}[] = {{\n{c_bytes(data, 32)}\n}};")
            lines.append(f"static const lv_image_dsc_t ls_imgd_{n} = {{{{LV_IMAGE_HEADER_MAGIC, {cf}, 0, {w['w']}, "
                         f"{w['h']}, {w['w'] * 2}, 0}}, {len(data)}, ls_img_{n}, NULL}};")
            reg.append(f"  ls_image_add({c_str(key)}, &ls_imgd_{n});")
            done[key] = n
    lines.append("static void ls_images_register() {\n" + "\n".join(reg) + "\n}")
    open(os.path.join(sk, "images_data.h"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    if done:
        log(f"✓ картинки: {len(done)} — {total // 1024} КБ")


def fqbn(board, variant=None):
    f = board["fqbn"]
    if variant:
        key = variant.split("=", 1)[0]
        f = re.sub(rf"{key}=[^,]+", variant, f)
    return f


def compile_sketch(tools, board, sketch, log, progress=None, cancel=None, variant=None):
    out = os.path.join(BUILD, board["id"], "out")
    cmd = [tools.cli, "--config-file", tools.cfg, "compile", "-v", "--fqbn", fqbn(board, variant),
           "--libraries", os.path.join(FIRMWARE, "libraries"), "--build-path", out, "--warnings", "none",
           "--jobs", "0", sketch]
    n = [0]
    t0 = time.time()

    def line(s):
        if " -c " in s and (" -o " in s):
            n[0] += 1
            if progress:
                progress(min(95, n[0] * 100 // 750))
            return
        if re.match(r"^(Sketch uses|Global variables|Скетч использует|Глобальные переменные)", s) or "error" in s.lower():
            log(s)

    tools.run(cmd, cancel=cancel, line_cb=line)
    if progress:
        progress(100)
    bins = glob.glob(os.path.join(out, "*.ino.bin"))
    size = os.path.getsize(bins[0]) if bins else 0
    log(f"✓ собрано за {time.time() - t0:.0f} с, прошивка {size // 1024} КБ")
    return out


def upload(tools, board, port, out, log, progress=None, cancel=None, variant=None):
    cmd = [tools.cli, "--config-file", tools.cfg, "upload", "--fqbn", fqbn(board, variant), "--port", port,
           "--input-dir", out, "-v"]

    def line(s):
        if "Writing at" in s or "Записано" in s:
            if progress:
                _pct(s, progress)
            return
        if any(k in s for k in ("Connecting", "Chip is", "Chip type", "Hash of data verified", "Hard resetting",
                                "error", "Error", "Failed", "A fatal")):
            log(s)

    try:
        tools.run(cmd, cancel=cancel, line_cb=line)
    except BuildError as e:
        t = str(e)
        if any(k in t for k in ("Failed to connect", "No serial data received", "Wrong boot mode", "could not open port")):
            raise BuildError(t + "\n⚠ Плата не ответила: держите BOOT, нажмите и отпустите RST (или переподключите "
                                 "кабель), отпустите BOOT — и «Залить» ещё раз.")
        raise
    log("✓ залито")


def backup(tools, board, port, log, progress=None, cancel=None):
    """Копия всей флеш-памяти платы — в backups/. Вернуть: путь к файлу."""
    os.makedirs(BACKUPS, exist_ok=True)
    path = os.path.join(BACKUPS, f"{board['id']}_{time.strftime('%Y%m%d_%H%M%S')}.bin")
    cmd = tools.esptool(board.get("core", "3.3.7")) + ["--chip", board.get("esptool_chip", "auto"), "--port", port,
                                                      "--baud", "921600", "read-flash", "0", "ALL", path]
    tools.run(cmd, cancel=cancel, line_cb=lambda s: progress and _pct(s, progress))
    with open(path + ".txt", "w", encoding="utf-8") as f:
        f.write(f"Копия прошивки платы {board['name']} ({time.strftime('%Y-%m-%d %H:%M')}).\n"
                "Вернуть на плату:\n"
                f"  esptool --chip {board.get('esptool_chip', 'auto')} --port COMx --baud 921600 "
                f"write-flash 0x0 {os.path.basename(path)}\n")
    log(f"✓ копия прошивки: {path}")
    return path
