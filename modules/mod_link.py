"""mod_link.py  v0.1.0 — связь с платой по USB: поиск портов, «кто ты» (hello), время, Live.

Журнал:
v0.1.0: первая версия — порты по VID:PID из паспортов плат, hello без перезагрузки платы (DTR/RTS не дёргаем),
        Live одной строкой «live <json>», время «time <utc> <TZ>».

Протокол прошивки — firmware/LineFirmware/LineFirmware.ino (шапка).
"""
import threading
import time

try:
    import serial
    from serial.tools import list_ports
except Exception:                                      # noqa: BLE001 (pyserial ставится сам при запуске)
    serial = None
    list_ports = None

BAUD = 115200


def ports(boards):
    """Порты USB: [{port, vid_pid, desc, boards: [id, ...]}] — какие платы могут быть на этом порту."""
    out = []
    if not list_ports:
        return out
    for p in list_ports.comports():
        if p.vid is None:
            continue
        vp = f"{p.vid:04X}:{p.pid:04X}"
        fits = [b["id"] for b in boards if vp in [u.upper() for u in b.get("usb", [])]]
        out.append({"port": p.device, "vid_pid": vp, "desc": p.description or "", "boards": fits})
    return out


def _open(port, timeout=0.2):
    s = serial.Serial()
    s.port = port
    s.baudrate = BAUD
    s.timeout = timeout
    s.write_timeout = 5
    s.dtr = False          # не перезагружать плату при открытии порта
    s.rts = False
    s.open()
    return s


def parse_hello(line):
    """«LS hello board=x fw=0.1.0 …» → dict."""
    if not line.startswith("LS hello"):
        return None
    d = {}
    for part in line[8:].split():
        if "=" in part:
            k, v = part.split("=", 1)
            d[k] = v
    return d


def hello(port, seconds=1.5):
    """Спросить плату, кто она. None — молчит или чужая прошивка; иначе dict из ответа."""
    try:
        s = _open(port)
    except Exception as e:                             # noqa: BLE001
        return {"error": str(e)}
    try:
        s.reset_input_buffer()
        s.write(b"\nhello\n")
        end = time.time() + seconds
        buf = b""
        while time.time() < end:
            buf += s.read(512)
            while b"\n" in buf:
                ln, buf = buf.split(b"\n", 1)
                h = parse_hello(ln.decode("utf-8", "replace").strip())
                if h is not None:
                    return h
        return None
    finally:
        s.close()


class Link:
    """Постоянное соединение (Live): пишет команды, читает ответы в журнал."""

    def __init__(self, port, on_line=None):
        self.port = port
        self.on_line = on_line or (lambda s: None)
        self.s = _open(port, timeout=0.1)
        self._stop = False
        self._lock = threading.Lock()
        self.last_hello = None
        self.t = threading.Thread(target=self._read, daemon=True)
        self.t.start()

    def _read(self):
        buf = b""
        while not self._stop:
            try:
                buf += self.s.read(1024)
            except Exception as e:                     # noqa: BLE001
                self.on_line(f"✗ порт {self.port}: {e}")
                self._stop = True
                break
            while b"\n" in buf:
                ln, buf = buf.split(b"\n", 1)
                t = ln.decode("utf-8", "replace").strip()
                if not t:
                    continue
                h = parse_hello(t)
                if h is not None:
                    self.last_hello = h
                self.on_line(t)

    def send(self, cmd):
        with self._lock:
            self.s.write(cmd.encode("utf-8") + b"\n")
            self.s.flush()

    def live(self, json_text):
        self.send("live " + json_text)

    def set_time(self, tz):
        self.send(f"time {int(time.time())} {tz}")

    @property
    def alive(self):
        return not self._stop

    def close(self):
        self._stop = True
        try:
            self.s.close()
        except Exception:                              # noqa: BLE001
            pass
