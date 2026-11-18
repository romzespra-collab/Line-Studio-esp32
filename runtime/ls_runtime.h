/* ls_runtime.h  v0.2.0 — рантайм LineStudio: экраны из проекта (JSON) → объекты LVGL.
 *
 * Журнал:
 * v0.2.0: погода (ls_weather_t, port.weather), картинки (ls_image_add), кэш букв (ls_font_cache).
 * v0.1.0: первая версия — экраны, виджеты, переходы, свайпы, часы/дата, шрифты TTF любого размера.
 *
 * Один и тот же код работает на плате (прошивка) и в редакторе на ПК (engine: line_engine.dll / .so),
 * поэтому превью совпадает с платой пиксель в пиксель.
 *
 * Порядок: lv_init() + дисплей + ввод (платформа) → ls_init(&port) → ls_font_add(...) → ls_load(json)
 *          → в цикле: ls_tick(); lv_timer_handler();
 */
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <time.h>
#include "lvgl.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LS_RUNTIME_VERSION "0.2.0"
#define LS_FORMAT 1            /* версия формата проекта, которую понимает рантайм */

typedef struct {
    int valid;          /* 1 — данные есть */
    int temp10;         /* температура, десятые °C */
    int code;           /* код погоды WMO (0 ясно … 99 гроза) */
    int tmin10, tmax10; /* за сегодня */
    int wind10;         /* ветер, десятые м/с */
    int hum;            /* влажность, % */
    int is_day;
    char city[32];
} ls_weather_t;

typedef struct {
    int (*local_time)(struct tm *out);  /* местное время; 1 — известно, 0 — ещё нет */
    void (*brightness)(int pct);        /* яркость 0..100 (NULL — нет) */
    void (*log)(const char *msg);       /* журнал (NULL — молчать) */
    int (*weather)(int city, ls_weather_t *out);   /* погода города (по номеру из настроек); NULL — нет */
} ls_port_t;

void ls_init(const ls_port_t *port);
/* Шрифт TTF под именем (medium, bold, light ...). Данные не копируются — должны жить всегда. */
void ls_font_add(const char *name, const void *ttf, size_t len);
void ls_font_cache(int glyphs);            /* букв в кэше каждого размера (128; без PSRAM — 32) — до ls_load */
/* Картинка по ключу (как в проекте: "<id>@<w>x<h>"). Данные не копируются. */
void ls_image_add(const char *key, const lv_image_dsc_t *dsc);
void ls_image_remove(const char *key);
/* Собрать проект. Текущий экран сохраняется, если он есть в новом проекте. 0 — ок. */
int ls_load(const char *json);
void ls_unload(void);
const char *ls_error(void);
void ls_tick(void);                        /* часы, дата, дуги времени — звать часто (раз в кадр) */
int ls_goto(const char *screen_id, int anim);   /* anim: LV_SCR_LOAD_ANIM_* ; -1 — без анимации */
int ls_back(void);
const char *ls_screen_id(void);
int ls_screen_count(void);
const char *ls_project_name(void);
int ls_widget_rect(const char *wid, int32_t out[4]);   /* x, y, w, h на экране после раскладки */
void ls_set_brightness(int pct);           /* то, что показывает ползунок яркости */

#ifdef __cplusplus
}
#endif
