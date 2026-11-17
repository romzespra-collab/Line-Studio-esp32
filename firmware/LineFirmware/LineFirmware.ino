// LineFirmware.ino  v0.1.0 — прошивка LineStudio: экраны проекта на плате.
//
// Журнал:
// v0.1.0: первая версия — LVGL 9.2.2 + рантайм LineStudio (ls_runtime) + порт платы (port.h);
//         проект зашит в прошивку (project_data.h), Live по USB, время от редактора или по Wi-Fi (NTP).
//
// Редактор кладёт рядом при сборке (копия в build/<плата>/LineFirmware): port.h, ls_gt911.h, ls_*.c/h,
// project_data.h (проект JSON), fonts_data.h (шрифты — только нужные, урезанные до нужных букв), build_info.h.
//
// Команды по USB (строка, конец — \n), ответы — строкой «LS …»:
//   hello                 → LS hello board=<id> fw=<версия> project=<id> rev=<n> w=<W> h=<H> screen=<id>
//   time <utc> <TZ>       → установить время (секунды UTC и строка пояса POSIX)
//   live <json>           → показать проект сразу (без прошивки); save — запомнить его в плате; forget — забыть
//   goto <id> / back      → экран
//   bright <0..100>       → яркость
#include <Arduino.h>
#include <Preferences.h>
#include <sys/time.h>
#include <lvgl.h>
#include "ls_runtime.h"
#include "build_info.h"
#include "port.h"
#include "project_data.h"
#include "fonts_data.h"
#if LS_WIFI
#include <WiFi.h>
#include "wifi_net.h"
#endif

#define LS_FW_VERSION "0.1.0"
#define LS_LINE_MAX (256 * 1024)

static lv_display_t *disp;
static uint8_t *lvbuf1, *lvbuf2;
static Preferences prefs;
static char *line;                 // строка из порта (в PSRAM)
static size_t line_n;
static char *live_json;            // проект из Live (до save — только в памяти)
static int bright = LS_BRIGHT;

static void flush_cb(lv_display_t *d, const lv_area_t *a, uint8_t *px) {
  lsb_flush(a->x1, a->y1, lv_area_get_width(a), lv_area_get_height(a), (uint16_t *)px);
  lv_display_flush_ready(d);
}

static void touch_cb(lv_indev_t *in, lv_indev_data_t *data) {
  int x, y;
  bool down = lsb_touch(&x, &y);
  data->point.x = x;
  data->point.y = y;
  data->state = down ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
}

static uint32_t tick_cb() { return millis(); }

static int port_time(struct tm *out) {
  time_t t = time(nullptr);
  if (t < 1700000000) return 0;
  localtime_r(&t, out);
  return 1;
}

static void port_bright(int pct) {
  bright = pct;
  lsb_brightness(pct);
}

static void port_log(const char *m) { Serial.printf("LS log %s\n", m); }

static void set_tz(const char *tz) {
  setenv("TZ", tz, 1);
  tzset();
}

static void hello() {
  Serial.printf("LS hello board=%s fw=%s project=%s rev=%d w=%d h=%d screen=%s live=%d\n", LSB_ID, LS_FW_VERSION,
                LS_PROJECT_ID, LS_PROJECT_REV, LSB_W, LSB_H, ls_screen_id(), live_json ? 1 : 0);
}

static void command(char *s) {
  while (*s == ' ' || *s == '\r') s++;
  char *arg = strchr(s, ' ');
  if (arg) *arg++ = 0;
  else arg = s + strlen(s);
  if (!strcmp(s, "hello")) hello();
  else if (!strcmp(s, "time")) {
    long long utc = atoll(arg);
    char *tz = strchr(arg, ' ');
    if (tz) set_tz(tz + 1);
    struct timeval tv = {(time_t)utc, 0};
    settimeofday(&tv, nullptr);
    Serial.println("LS ok time");
  } else if (!strcmp(s, "live")) {
    if (ls_load(arg) == 0) {
      free(live_json);
      live_json = strdup(arg);
      Serial.printf("LS ok live %s\n", ls_screen_id());
    } else {
      Serial.printf("LS err live %s\n", ls_error());
      ls_load(live_json ? live_json : LS_PROJECT_JSON);
    }
  } else if (!strcmp(s, "save")) {
    if (!live_json) { Serial.println("LS err save нечего сохранять: Live не было"); return; }
    size_t n = strlen(live_json);
    prefs.begin("ls", false);
    bool ok = prefs.putBytes("proj", live_json, n) == n && prefs.putInt("rev", LS_PROJECT_REV);
    prefs.end();
    Serial.println(ok ? "LS ok save" : "LS err save не поместилось в NVS");
  } else if (!strcmp(s, "forget")) {
    prefs.begin("ls", false);
    prefs.remove("proj");
    prefs.end();
    free(live_json);
    live_json = nullptr;
    ls_load(LS_PROJECT_JSON);
    Serial.println("LS ok forget");
  } else if (!strcmp(s, "goto")) {
    Serial.println(ls_goto(arg, LV_SCR_LOAD_ANIM_FADE_IN) == 0 ? "LS ok goto" : "LS err goto нет такого экрана");
  } else if (!strcmp(s, "back")) {
    ls_back();
    Serial.println("LS ok back");
  } else if (!strcmp(s, "bright")) {
    ls_set_brightness(atoi(arg));
    Serial.println("LS ok bright");
  } else if (*s) {
    Serial.printf("LS err неизвестная команда «%s»\n", s);
  }
}

static void serial_poll() {
  while (Serial.available()) {
    int c = Serial.read();
    if (c < 0) break;
    if (c == '\n') {
      line[line_n] = 0;
      command(line);
      line_n = 0;
    } else if (line_n < LS_LINE_MAX - 1) {
      line[line_n++] = (char)c;
    }
  }
}

static const char *stored_project() {   // сохранённый Live этой же прошивки (rev совпадает) — иначе встроенный
  prefs.begin("ls", true);
  size_t n = prefs.getBytesLength("proj");
  int rev = prefs.getInt("rev", -1);
  char *p = nullptr;
  if (n > 0 && rev == LS_PROJECT_REV) {
    p = (char *)ps_malloc(n + 1);
    if (p) { prefs.getBytes("proj", p, n); p[n] = 0; }
  }
  prefs.end();
  return p;
}

void setup() {
  Serial.setRxBufferSize(8192);
  Serial.begin(115200);
  delay(100);
  Serial.printf("\nLS log старт %s fw %s, проект %s rev %d\n", LSB_ID, LS_FW_VERSION, LS_PROJECT_ID, LS_PROJECT_REV);
  set_tz(LS_TZ);
  line = (char *)ps_malloc(LS_LINE_MAX);
  if (!line) line = (char *)malloc(16 * 1024);
  if (!lsb_begin()) Serial.println("LS log экран не запустился");

  lv_init();
  lv_tick_set_cb(tick_cb);
  disp = lv_display_create(LSB_W, LSB_H);
  size_t bsz = (size_t)LSB_W * LSB_BUF_LINES * 2;
  lvbuf1 = (uint8_t *)heap_caps_malloc(bsz, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  lvbuf2 = (uint8_t *)heap_caps_malloc(bsz, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  if (!lvbuf1 || !lvbuf2) {   // нет внутренней памяти — из PSRAM (медленнее)
    lvbuf1 = (uint8_t *)ps_malloc(bsz);
    lvbuf2 = (uint8_t *)ps_malloc(bsz);
  }
  lv_display_set_buffers(disp, lvbuf1, lvbuf2, bsz, LV_DISPLAY_RENDER_MODE_PARTIAL);
  lv_display_set_flush_cb(disp, flush_cb);
  lv_indev_t *in = lv_indev_create();
  lv_indev_set_type(in, LV_INDEV_TYPE_POINTER);
  lv_indev_set_read_cb(in, touch_cb);

  ls_port_t port = {port_time, port_bright, port_log};
  ls_init(&port);
  ls_fonts_register();
  const char *saved = stored_project();
  if (saved) live_json = (char *)saved;
  if (ls_load(saved ? saved : LS_PROJECT_JSON) != 0) {
    Serial.printf("LS log проект не собрался: %s\n", ls_error());
    if (saved) ls_load(LS_PROJECT_JSON);
  }
  lv_refr_now(disp);
  ls_set_brightness(bright);
#if LS_WIFI
  WiFi.mode(WIFI_STA);
  WiFi.begin(LS_WIFI_SSID, LS_WIFI_PASS);
  configTzTime(LS_TZ, "pool.ntp.org", "time.google.com");
#endif
  hello();
}

void loop() {
  serial_poll();
  ls_tick();
  uint32_t wait = lv_timer_handler();
  delay(wait > 5 ? 5 : wait);
}
