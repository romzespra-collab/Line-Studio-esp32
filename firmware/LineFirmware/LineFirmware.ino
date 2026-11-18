// LineFirmware.ino  v0.2.0 — прошивка LineStudio: экраны проекта на плате.
//
// Журнал:
// v0.2.0: погода (open-meteo.com по HTTPS с проверкой сертификата — набор корневых из ядра), картинки
//         (images_data.h), значки (шрифт icons), платы без PSRAM (CYD: LSB_FONT_CACHE, LSB_LINE_MAX).
// v0.1.0: первая версия — LVGL 9.2.2 + рантайм LineStudio (ls_runtime) + порт платы (port.h);
//         проект зашит в прошивку (project_data.h), Live по USB, время от редактора или по Wi-Fi (NTP).
//
// Редактор кладёт рядом при сборке (копия в build/<плата>/LineFirmware): port.h, ls_gt911.h, ls_*.c/h,
// project_data.h (проект JSON), fonts_data.h (шрифты — только нужные, урезанные до нужных букв), images_data.h
// (картинки под размер блоков), build_info.h (id проекта, пояс, Wi-Fi, города погоды).
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
#include "images_data.h"
#if LS_WIFI
#include <WiFi.h>
#include "wifi_net.h"
#endif
#if LS_WEATHER
#include <HTTPClient.h>
#include <NetworkClientSecure.h>
#include "ls_json.h"
#endif

#define LS_FW_VERSION "0.2.0"
#ifdef LSB_LINE_MAX
#define LS_LINE_MAX LSB_LINE_MAX
#else
#define LS_LINE_MAX (256 * 1024)
#endif

static void *big_alloc(size_t n) {   // PSRAM, если есть, иначе обычная память
  void *p = ps_malloc(n);
  return p ? p : malloc(n);
}

#if LS_WEATHER
// ---------- погода: open-meteo.com, раз в 15 минут (сбой — через 2 минуты), в своей задаче ----------
extern const uint8_t ls_ca_start[] asm("_binary_x509_crt_bundle_start");   // корневые сертификаты из ядра
extern const uint8_t ls_ca_end[] asm("_binary_x509_crt_bundle_end");
struct LsCity { const char *name; float lat, lon; };
static const LsCity ls_cities[] = LS_CITIES;
static const int ls_ncities = sizeof ls_cities / sizeof ls_cities[0];
static ls_weather_t wx[sizeof ls_cities / sizeof ls_cities[0]];
static portMUX_TYPE wx_mux = portMUX_INITIALIZER_UNLOCKED;

static double jnum(lsJSON *o, const char *k, double def) {
  lsJSON *v = lsJSON_GetObjectItemCaseSensitive(o, k);
  return lsJSON_IsNumber(v) ? v->valuedouble : def;
}
static double jfirst(lsJSON *o, const char *k, double def) {
  lsJSON *v = lsJSON_GetObjectItemCaseSensitive(o, k);
  lsJSON *x = lsJSON_GetArrayItem(v, 0);
  return lsJSON_IsNumber(x) ? x->valuedouble : def;
}
static int r10(double v) { return (int)(v * 10 + (v >= 0 ? 0.5 : -0.5)); }

static bool wx_fetch(int i) {
  NetworkClientSecure cl;
  cl.setCACertBundle(ls_ca_start, ls_ca_end - ls_ca_start);
  HTTPClient http;
  char url[420];
  snprintf(url, sizeof url,
           "https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f&timezone=auto&forecast_days=1"
           "&wind_speed_unit=ms&current=temperature_2m,weather_code,is_day,wind_speed_10m,relative_humidity_2m"
           "&daily=temperature_2m_max,temperature_2m_min", ls_cities[i].lat, ls_cities[i].lon);
  if (!http.begin(cl, url)) return false;
  http.setTimeout(12000);
  int code = http.GET();
  if (code != 200) {
    Serial.printf("LS log погода «%s»: ответ %d\n", ls_cities[i].name, code);
    http.end();
    return false;
  }
  String body = http.getString();
  http.end();
  lsJSON *j = lsJSON_Parse(body.c_str());
  if (!j) return false;
  lsJSON *c = lsJSON_GetObjectItemCaseSensitive(j, "current"), *d = lsJSON_GetObjectItemCaseSensitive(j, "daily");
  ls_weather_t w = {};
  w.valid = c != nullptr;
  w.temp10 = r10(jnum(c, "temperature_2m", 0));
  w.code = (int)jnum(c, "weather_code", -1);
  w.is_day = (int)jnum(c, "is_day", 1);
  w.wind10 = r10(jnum(c, "wind_speed_10m", 0));
  w.hum = (int)jnum(c, "relative_humidity_2m", 0);
  w.tmax10 = r10(jfirst(d, "temperature_2m_max", 0));
  w.tmin10 = r10(jfirst(d, "temperature_2m_min", 0));
  snprintf(w.city, sizeof w.city, "%s", ls_cities[i].name);
  lsJSON_Delete(j);
  portENTER_CRITICAL(&wx_mux);
  wx[i] = w;
  portEXIT_CRITICAL(&wx_mux);
  Serial.printf("LS log погода «%s»: %.1f°, код %d\n", ls_cities[i].name, w.temp10 / 10.0, w.code);
  return w.valid;
}

static void wx_task(void *) {
  for (;;) {
    if (WiFi.status() != WL_CONNECTED) { vTaskDelay(pdMS_TO_TICKS(5000)); continue; }
    bool ok = true;
    for (int i = 0; i < ls_ncities; i++) ok = wx_fetch(i) && ok;
    vTaskDelay(pdMS_TO_TICKS(ok ? 15 * 60 * 1000 : 2 * 60 * 1000));
  }
}

static int port_weather(int city, ls_weather_t *out) {
  if (city < 0 || city >= ls_ncities) return 0;
  portENTER_CRITICAL(&wx_mux);
  *out = wx[city];
  portEXIT_CRITICAL(&wx_mux);
  return out->valid;
}
#endif

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
    p = (char *)big_alloc(n + 1);
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
  line = (char *)big_alloc(LS_LINE_MAX);
  if (!lsb_begin()) Serial.println("LS log экран не запустился");

  lv_init();
  lv_tick_set_cb(tick_cb);
  disp = lv_display_create(LSB_W, LSB_H);
  size_t bsz = (size_t)LSB_W * LSB_BUF_LINES * 2;
  lvbuf1 = (uint8_t *)heap_caps_malloc(bsz, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  lvbuf2 = (uint8_t *)heap_caps_malloc(bsz, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  if (!lvbuf1 || !lvbuf2) {   // нет внутренней памяти — из PSRAM (медленнее)
    lvbuf1 = (uint8_t *)big_alloc(bsz);
    lvbuf2 = (uint8_t *)big_alloc(bsz);
  }
  lv_display_set_buffers(disp, lvbuf1, lvbuf2, bsz, LV_DISPLAY_RENDER_MODE_PARTIAL);
  lv_display_set_flush_cb(disp, flush_cb);
  lv_indev_t *in = lv_indev_create();
  lv_indev_set_type(in, LV_INDEV_TYPE_POINTER);
  lv_indev_set_read_cb(in, touch_cb);

#if LS_WEATHER
  ls_port_t port = {port_time, port_bright, port_log, port_weather};
#else
  ls_port_t port = {port_time, port_bright, port_log, nullptr};
#endif
  ls_init(&port);
#ifdef LSB_FONT_CACHE
  ls_font_cache(LSB_FONT_CACHE);
#endif
  ls_fonts_register();
  ls_images_register();
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
#if LS_WEATHER
  xTaskCreate(wx_task, "ls_wx", 10240, nullptr, 1, nullptr);
#endif
  hello();
}

void loop() {
  serial_poll();
  ls_tick();
  uint32_t wait = lv_timer_handler();
  delay(wait > 5 ? 5 : wait);
}
