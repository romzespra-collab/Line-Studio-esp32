/* le_engine.c  v0.1.0 — движок превью LineStudio: тот же рантайм и LVGL, что на плате, в DLL для ПК.
 *
 * Журнал:
 * v0.1.0: первая версия — кадр RGB565 в памяти, палец мышью, своё время (живое или замороженное).
 *
 * Редактор (modules/mod_engine.py) зовёт через ctypes:
 *   le_init(w, h) → le_font(name, data, len) → le_load(json) → le_step(ms) → le_buffer() (w*h RGB565)
 */
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "lvgl.h"
#include "ls_runtime.h"

#ifdef _WIN32
#define LE_API __declspec(dllexport)
#else
#define LE_API __attribute__((visibility("default")))
#endif

static lv_display_t *g_disp;
static lv_indev_t *g_in;
static uint16_t *g_fb;
static int g_w, g_h, g_inited;
static uint32_t g_ms;
static int g_tx, g_ty, g_tdown;
static long long g_fixed;     /* > 0 — время заморожено (секунды «местного» времени от 1970) */
static long long g_offset;    /* сдвиг к системному местному времени, с */
static int g_bright = 80;
static char g_log[2048];

static uint32_t tick_cb(void) { return g_ms; }

static void flush_cb(lv_display_t *d, const lv_area_t *a, uint8_t *px) {
    (void)a; (void)px;
    lv_display_flush_ready(d);
}

static void read_cb(lv_indev_t *in, lv_indev_data_t *data) {
    (void)in;
    data->point.x = g_tx;
    data->point.y = g_ty;
    data->state = g_tdown ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
}

static int port_time(struct tm *out) {
    if (g_fixed > 0) {
        time_t t = (time_t)g_fixed;
#ifdef _WIN32
        gmtime_s(out, &t);
#else
        gmtime_r(&t, out);
#endif
        return 1;
    }
    time_t t = time(NULL) + (time_t)g_offset;
#ifdef _WIN32
    localtime_s(out, &t);
#else
    localtime_r(&t, out);
#endif
    return 1;
}

static void port_bright(int pct) { g_bright = pct; }

static void port_log(const char *m) {
    size_t L = strlen(g_log), M = strlen(m);
    if (L + M + 2 >= sizeof g_log) { g_log[0] = 0; L = 0; }
    memcpy(g_log + L, m, M);
    g_log[L + M] = '\n';
    g_log[L + M + 1] = 0;
}

LE_API const char *le_version(void) { return LS_RUNTIME_VERSION; }

LE_API int le_init(int w, int h) {
    if (w < 16 || h < 16 || w > 4096 || h > 4096) return -1;
    if (!g_inited) {
        lv_init();
        lv_tick_set_cb(tick_cb);
        ls_port_t p = {port_time, port_bright, port_log};
        ls_init(&p);
        g_inited = 1;
    }
    if (g_disp) {
        ls_unload();
        lv_display_delete(g_disp);
        g_disp = NULL;
        free(g_fb);
    }
    g_w = w;
    g_h = h;
    g_fb = (uint16_t *)calloc((size_t)w * h, 2);
    if (!g_fb) return -2;
    g_disp = lv_display_create(w, h);
    lv_display_set_color_format(g_disp, LV_COLOR_FORMAT_RGB565);
    lv_display_set_buffers(g_disp, g_fb, NULL, (uint32_t)w * h * 2, LV_DISPLAY_RENDER_MODE_DIRECT);
    lv_display_set_flush_cb(g_disp, flush_cb);
    lv_display_set_default(g_disp);
    if (!g_in) {
        g_in = lv_indev_create();
        lv_indev_set_type(g_in, LV_INDEV_TYPE_POINTER);
        lv_indev_set_read_cb(g_in, read_cb);
    }
    lv_indev_set_display(g_in, g_disp);
    return 0;
}

LE_API int le_font(const char *name, const void *data, int len) {
    /* данные копируются: Python-буфер может уйти */
    void *copy = malloc((size_t)len);
    if (!copy) return -1;
    memcpy(copy, data, (size_t)len);
    char *nm = (char *)malloc(strlen(name) + 1);
    strcpy(nm, name);
    ls_font_add(nm, copy, (size_t)len);
    return 0;
}

LE_API int le_load(const char *json) {
    if (!g_disp) return -10;
    int r = ls_load(json);
    lv_obj_invalidate(lv_screen_active());
    return r;
}

LE_API const char *le_error(void) { return ls_error(); }

LE_API const char *le_log(void) { return g_log; }
LE_API void le_log_clear(void) { g_log[0] = 0; }

/* Прожить ms миллисекунд: анимации, ввод, перерисовка. */
LE_API void le_step(int ms) {
    if (!g_disp) return;
    int left = ms > 0 ? ms : 0;
    do {
        int d = left > 16 ? 16 : left;
        g_ms += (uint32_t)d;
        left -= d;
        ls_tick();
        lv_timer_handler();
    } while (left > 0);
}

/* Перерисовать весь экран сейчас (после le_load / смены времени). */
LE_API void le_redraw(void) {
    if (!g_disp) return;
    ls_tick();
    lv_obj_invalidate(lv_screen_active());
    lv_refr_now(g_disp);
}

LE_API const uint16_t *le_buffer(void) { return g_fb; }
LE_API int le_width(void) { return g_w; }
LE_API int le_height(void) { return g_h; }

LE_API void le_touch(int x, int y, int down) {
    g_tx = x;
    g_ty = y;
    g_tdown = down;
}

LE_API void le_time(long long fixed_local, long long offset) {
    g_fixed = fixed_local;
    g_offset = offset;
}

LE_API int le_goto(const char *id) { return ls_goto(id, -1); }
LE_API int le_back(void) { return ls_back(); }
LE_API const char *le_screen(void) { return ls_screen_id(); }
LE_API int le_brightness(void) { return g_bright; }

LE_API int le_rect(const char *wid, int *out4) {
    int32_t r[4];
    if (ls_widget_rect(wid, r)) return -1;
    for (int i = 0; i < 4; i++) out4[i] = (int)r[i];
    return 0;
}
