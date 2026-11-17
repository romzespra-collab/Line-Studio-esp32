/* ls_runtime.c  v0.1.0 — рантайм LineStudio (см. ls_runtime.h).
 *
 * Журнал:
 * v0.1.0: первая версия. Виджеты: label, clock, date, rect, arc, analog, button, slider.
 *         Переходы между экранами (fade/left/right/up/down), свайпы экрана, «назад» свайпом вправо,
 *         шрифты TTF (tiny_ttf) любого размера с кириллицей, формат времени {HH}:{mm} и т.п.
 *
 * Формат проекта (JSON, format 1) — описан в docs/FORMAT.md. Коротко:
 *   {"format":1, "name":"...", "home":"main", "settings":{"lang":"ru"},
 *    "screens":[{"id":"main","name":"Главный","bg":"#000000","swipe":{"left":"id2"},"back":true,
 *                "widgets":[{"id":"w1","type":"clock","x":0,"y":0,"w":480,"h":0,...,"link":{"to":"id","anim":"fade"}}]}]}
 * Целые числа — пиксели экрана платы. Цвета — "#RRGGBB".
 * Вычисления — только целые (lv_trigo_sin): на плате и на ПК картинка одна и та же.
 */
#include "ls_runtime.h"
#include "ls_json.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LS_MAX_SCREENS 64
#define LS_MAX_DYN 256
#define LS_MAX_FONTS 8
#define LS_MAX_SIZES 64
#define LS_STACK 16

enum { K_CLOCK = 1, K_DATE, K_ARC, K_ANALOG, K_SLIDER };
enum { SRC_STATIC = 0, SRC_SECONDS, SRC_MINUTES, SRC_HOURS, SRC_DAY, SRC_BRIGHT };

typedef struct {
    const char *id;
    lv_obj_t *scr;
    lsJSON *def;
} ls_screen_t;

typedef struct {
    lv_obj_t *obj;
    uint8_t kind, src;
    const char *fmt;
    uint8_t ticks, secs;
    lv_color_t c_face, c_ticks, c_hour, c_min, c_sec;
} ls_dyn_t;

typedef struct { const char *name; const void *data; size_t len; } ls_fontdata_t;
typedef struct { int font; int size; lv_font_t *f; } ls_fontsize_t;

static ls_port_t g_port;
static lsJSON *g_proj;
static ls_screen_t g_scr[LS_MAX_SCREENS];
static int g_n, g_cur = -1;
static ls_dyn_t g_dyn[LS_MAX_DYN];
static int g_ndyn;
static struct { int idx; int anim; } g_stack[LS_STACK];
static int g_sp;
static char g_err[160];
static const char *g_lang = "ru";
static int g_last_sec = -1;
static int g_bright = 80;
static ls_fontdata_t g_fonts[LS_MAX_FONTS];
static int g_nfonts;
static ls_fontsize_t g_sizes[LS_MAX_SIZES];
static int g_nsizes;

/* ---------- мелочи ---------- */
static void say(const char *fmt, ...) {
    if (!g_port.log) return;
    char b[200];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(b, sizeof b, fmt, ap);
    va_end(ap);
    g_port.log(b);
}

static const char *jstr(const lsJSON *o, const char *k, const char *def) {
    const lsJSON *v = lsJSON_GetObjectItemCaseSensitive(o, k);
    return lsJSON_IsString(v) && v->valuestring ? v->valuestring : def;
}
static int jint(const lsJSON *o, const char *k, int def) {
    const lsJSON *v = lsJSON_GetObjectItemCaseSensitive(o, k);
    if (lsJSON_IsNumber(v)) return (int)v->valuedouble;
    if (lsJSON_IsBool(v)) return lsJSON_IsTrue(v);
    return def;
}
static lv_color_t jcolor(const lsJSON *o, const char *k, uint32_t def) {
    const char *s = jstr(o, k, NULL);
    uint32_t c = def;
    if (s && s[0] == '#' && strlen(s) >= 7) c = (uint32_t)strtoul(s + 1, NULL, 16) & 0xFFFFFF;
    return lv_color_hex(c);
}
static int clampi(int v, int lo, int hi) { return v < lo ? lo : v > hi ? hi : v; }

/* ---------- шрифты ---------- */
void ls_font_add(const char *name, const void *ttf, size_t len) {
    for (int i = 0; i < g_nfonts; i++)
        if (!strcmp(g_fonts[i].name, name)) { g_fonts[i].data = ttf; g_fonts[i].len = len; return; }
    if (g_nfonts >= LS_MAX_FONTS) return;
    g_fonts[g_nfonts].name = name;
    g_fonts[g_nfonts].data = ttf;
    g_fonts[g_nfonts].len = len;
    g_nfonts++;
}

static const lv_font_t *font_get(const char *name, int size) {
    int fi = -1;
    for (int i = 0; i < g_nfonts; i++)
        if (!strcmp(g_fonts[i].name, name ? name : "medium")) { fi = i; break; }
    if (fi < 0 && g_nfonts) fi = 0;
    if (fi < 0) return LV_FONT_DEFAULT;
    size = clampi(size, 6, 400);
    for (int i = 0; i < g_nsizes; i++)
        if (g_sizes[i].font == fi && g_sizes[i].size == size) return g_sizes[i].f;
    if (g_nsizes >= LS_MAX_SIZES) return LV_FONT_DEFAULT;
    lv_font_t *f = lv_tiny_ttf_create_data_ex(g_fonts[fi].data, g_fonts[fi].len, size, LV_FONT_KERNING_NORMAL, 128);
    if (!f) return LV_FONT_DEFAULT;
    g_sizes[g_nsizes].font = fi;
    g_sizes[g_nsizes].size = size;
    g_sizes[g_nsizes].f = f;
    g_nsizes++;
    return f;
}

/* ---------- время: {HH}:{mm} и т.п. ---------- */
static const char *const MON_RU[] = {"январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"};
static const char *const MONG_RU[] = {"января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"};
static const char *const MONS_RU[] = {"янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"};
static const char *const DAY_RU[] = {"воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"};
static const char *const DAYS_RU[] = {"вс", "пн", "вт", "ср", "чт", "пт", "сб"};
static const char *const MON_UK[] = {"січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"};
static const char *const MONG_UK[] = {"січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"};
static const char *const MONS_UK[] = {"січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"};
static const char *const DAY_UK[] = {"неділя", "понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота"};
static const char *const DAYS_UK[] = {"нд", "пн", "вт", "ср", "чт", "пт", "сб"};
static const char *const MON_EN[] = {"January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"};
static const char *const MONS_EN[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
static const char *const DAY_EN[] = {"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"};
static const char *const DAYS_EN[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};

static void put(char **o, char *end, const char *s, int upper) {
    while (*s && *o < end) {
        char c = *s++;
        if (upper && c >= 'a' && c <= 'z') c -= 32;
        *(*o)++ = c;
    }
}

/* Слова: {dddd} день недели, {ddd} кратко, {MMMM} месяц, {MMMMg} месяц в родительном (ноября), {MMM} кратко;
 * числа: {HH} {H} {hh} {h} {mm} {ss} {dd} {d} {MM} {M} {YYYY} {YY}; {AMPM}. ^ после { — ЗАГЛАВНЫМИ: {^dddd} */
static void fmt_time(char *out, size_t n, const char *fmt, const struct tm *t, int known) {
    char *o = out, *end = out + n - 1;
    int ru = !strcmp(g_lang, "ru"), uk = !strcmp(g_lang, "uk");
    const char *const *mon = ru ? MON_RU : uk ? MON_UK : MON_EN;
    const char *const *mong = ru ? MONG_RU : uk ? MONG_UK : MON_EN;
    const char *const *mons = ru ? MONS_RU : uk ? MONS_UK : MONS_EN;
    const char *const *day = ru ? DAY_RU : uk ? DAY_UK : DAY_EN;
    const char *const *days = ru ? DAYS_RU : uk ? DAYS_UK : DAYS_EN;
    while (*fmt && o < end) {
        if (*fmt != '{') { *o++ = *fmt++; continue; }
        const char *c = strchr(fmt, '}');
        if (!c) { *o++ = *fmt++; continue; }
        char tok[12] = {0};
        size_t L = (size_t)(c - fmt - 1);
        if (L >= sizeof tok) { *o++ = *fmt++; continue; }
        memcpy(tok, fmt + 1, L);
        fmt = c + 1;
        int up = 0;
        char *k = tok;
        if (*k == '^') { up = 1; k++; }
        char num[8];
        if (!known) { put(&o, end, (!strcmp(k, "HH") || !strcmp(k, "mm") || !strcmp(k, "ss") || !strcmp(k, "dd") || !strcmp(k, "MM") || !strcmp(k, "hh")) ? "--" : "-", 0); continue; }
        int h12 = t->tm_hour % 12 ? t->tm_hour % 12 : 12;
        if (!strcmp(k, "HH")) snprintf(num, sizeof num, "%02d", t->tm_hour), put(&o, end, num, 0);
        else if (!strcmp(k, "H")) snprintf(num, sizeof num, "%d", t->tm_hour), put(&o, end, num, 0);
        else if (!strcmp(k, "hh")) snprintf(num, sizeof num, "%02d", h12), put(&o, end, num, 0);
        else if (!strcmp(k, "h")) snprintf(num, sizeof num, "%d", h12), put(&o, end, num, 0);
        else if (!strcmp(k, "mm")) snprintf(num, sizeof num, "%02d", t->tm_min), put(&o, end, num, 0);
        else if (!strcmp(k, "ss")) snprintf(num, sizeof num, "%02d", t->tm_sec), put(&o, end, num, 0);
        else if (!strcmp(k, "dd")) snprintf(num, sizeof num, "%02d", t->tm_mday), put(&o, end, num, 0);
        else if (!strcmp(k, "d")) snprintf(num, sizeof num, "%d", t->tm_mday), put(&o, end, num, 0);
        else if (!strcmp(k, "MM")) snprintf(num, sizeof num, "%02d", t->tm_mon + 1), put(&o, end, num, 0);
        else if (!strcmp(k, "M")) snprintf(num, sizeof num, "%d", t->tm_mon + 1), put(&o, end, num, 0);
        else if (!strcmp(k, "YYYY")) snprintf(num, sizeof num, "%04d", t->tm_year + 1900), put(&o, end, num, 0);
        else if (!strcmp(k, "YY")) snprintf(num, sizeof num, "%02d", t->tm_year % 100), put(&o, end, num, 0);
        else if (!strcmp(k, "AMPM")) put(&o, end, t->tm_hour < 12 ? "AM" : "PM", 0);
        else if (!strcmp(k, "dddd")) put(&o, end, day[t->tm_wday % 7], up);
        else if (!strcmp(k, "ddd")) put(&o, end, days[t->tm_wday % 7], up);
        else if (!strcmp(k, "MMMM")) put(&o, end, mon[t->tm_mon % 12], up);
        else if (!strcmp(k, "MMMMg")) put(&o, end, mong[t->tm_mon % 12], up);
        else if (!strcmp(k, "MMM")) put(&o, end, mons[t->tm_mon % 12], up);
        else { put(&o, end, "{", 0); put(&o, end, tok, 0); put(&o, end, "}", 0); }
    }
    *o = 0;
    /* ЗАГЛАВНЫЕ для кириллицы: {^...} — UTF-8 строчные а..я (D0 B0..D0 BF, D1 80..D1 8F) → А..Я */
    (void)0;
}

/* UTF-8: строчные кириллические → заглавные (для {^dddd} и т.п.) */
static void upper_utf8(char *s) {
    unsigned char *p = (unsigned char *)s;
    while (*p) {
        if (p[0] >= 'a' && p[0] <= 'z') { p[0] -= 32; p++; continue; }
        if (p[0] == 0xD0 && p[1] >= 0xB0 && p[1] <= 0xBF) { p[1] -= 0x20; p += 2; continue; }        /* а..п → А..П */
        if (p[0] == 0xD1 && p[1] >= 0x80 && p[1] <= 0x8F) { p[0] = 0xD0; p[1] += 0x20; p += 2; continue; }  /* р..я → Р..Я */
        if (p[0] == 0xD1 && p[1] >= 0x90 && p[1] <= 0x9F) { p[0] = 0xD0; p[1] -= 0x10; p += 2; continue; }  /* ѐ..џ (ё, є, і, ї) */
        if (p[0] == 0xD2 && p[1] == 0x91) { p[1] = 0x90; p += 2; continue; }                              /* ґ → Ґ */
        p++;
    }
}

static int now_tm(struct tm *t) {
    memset(t, 0, sizeof *t);
    if (g_port.local_time && g_port.local_time(t)) return 1;
    return 0;
}

static void dyn_text(ls_dyn_t *d, const struct tm *t, int known) {
    char b[160];
    fmt_time(b, sizeof b, d->fmt, t, known);
    if (strstr(d->fmt, "{^")) upper_utf8(b);
    const char *cur = lv_label_get_text(d->obj);
    if (!cur || strcmp(cur, b)) lv_label_set_text(d->obj, b);
}

static int src_value(int src, const struct tm *t, int stat) {   /* 0..1000 */
    switch (src) {
    case SRC_SECONDS: return t->tm_sec * 1000 / 60;
    case SRC_MINUTES: return (t->tm_min * 60 + t->tm_sec) * 1000 / 3600;
    case SRC_HOURS: return ((t->tm_hour % 12) * 60 + t->tm_min) * 1000 / 720;
    case SRC_DAY: return (t->tm_hour * 60 + t->tm_min) * 1000 / 1440;
    case SRC_BRIGHT: return g_bright * 10;
    default: return clampi(stat, 0, 100) * 10;
    }
}

static int src_parse(const char *s) {
    if (!s) return SRC_STATIC;
    if (!strcmp(s, "seconds")) return SRC_SECONDS;
    if (!strcmp(s, "minutes")) return SRC_MINUTES;
    if (!strcmp(s, "hours")) return SRC_HOURS;
    if (!strcmp(s, "day")) return SRC_DAY;
    if (!strcmp(s, "brightness")) return SRC_BRIGHT;
    return SRC_STATIC;
}

static int anim_parse(const char *s) {
    if (!s || !strcmp(s, "fade")) return LV_SCR_LOAD_ANIM_FADE_IN;
    if (!strcmp(s, "left")) return LV_SCR_LOAD_ANIM_MOVE_LEFT;
    if (!strcmp(s, "right")) return LV_SCR_LOAD_ANIM_MOVE_RIGHT;
    if (!strcmp(s, "up")) return LV_SCR_LOAD_ANIM_MOVE_TOP;
    if (!strcmp(s, "down")) return LV_SCR_LOAD_ANIM_MOVE_BOTTOM;
    if (!strcmp(s, "over")) return LV_SCR_LOAD_ANIM_OVER_LEFT;
    if (!strcmp(s, "none")) return LV_SCR_LOAD_ANIM_NONE;
    return LV_SCR_LOAD_ANIM_FADE_IN;
}

static int anim_back(int a) {
    switch (a) {
    case LV_SCR_LOAD_ANIM_MOVE_LEFT: return LV_SCR_LOAD_ANIM_MOVE_RIGHT;
    case LV_SCR_LOAD_ANIM_MOVE_RIGHT: return LV_SCR_LOAD_ANIM_MOVE_LEFT;
    case LV_SCR_LOAD_ANIM_MOVE_TOP: return LV_SCR_LOAD_ANIM_MOVE_BOTTOM;
    case LV_SCR_LOAD_ANIM_MOVE_BOTTOM: return LV_SCR_LOAD_ANIM_MOVE_TOP;
    case LV_SCR_LOAD_ANIM_OVER_LEFT: return LV_SCR_LOAD_ANIM_OUT_RIGHT;
    default: return a;
    }
}

/* ---------- навигация ---------- */
static int screen_index(const char *id) {
    if (!id) return -1;
    for (int i = 0; i < g_n; i++)
        if (g_scr[i].id && !strcmp(g_scr[i].id, id)) return i;
    return -1;
}

static void show(int i, int anim) {
    if (i < 0 || i >= g_n) return;
    g_cur = i;
    if (anim < 0 || anim == LV_SCR_LOAD_ANIM_NONE) lv_screen_load(g_scr[i].scr);
    else lv_screen_load_anim(g_scr[i].scr, (lv_screen_load_anim_t)anim, 260, 0, false);
}

int ls_goto(const char *screen_id, int anim) {
    int i = screen_index(screen_id);
    if (i < 0 || i == g_cur) return -1;
    if (g_cur >= 0) {
        if (g_sp == LS_STACK) { memmove(g_stack, g_stack + 1, sizeof g_stack[0] * (LS_STACK - 1)); g_sp--; }
        g_stack[g_sp].idx = g_cur;
        g_stack[g_sp].anim = anim;
        g_sp++;
    }
    show(i, anim);
    return 0;
}

int ls_back(void) {
    if (!g_sp) return -1;
    g_sp--;
    show(g_stack[g_sp].idx, anim_back(g_stack[g_sp].anim));
    return 0;
}

const char *ls_screen_id(void) { return g_cur >= 0 ? g_scr[g_cur].id : ""; }
int ls_screen_count(void) { return g_n; }
const char *ls_project_name(void) { return g_proj ? jstr(g_proj, "name", "") : ""; }

static void on_link(lv_event_t *e) {
    const lsJSON *link = (const lsJSON *)lv_event_get_user_data(e);
    const char *to = jstr(link, "to", NULL);
    if (!to) return;
    if (!strcmp(to, "@back")) { ls_back(); return; }
    ls_goto(to, anim_parse(jstr(link, "anim", "fade")));
}

static void on_gesture(lv_event_t *e) {
    const lsJSON *def = (const lsJSON *)lv_event_get_user_data(e);
    lv_indev_t *in = lv_indev_active();
    if (!in) return;
    lv_dir_t d = lv_indev_get_gesture_dir(in);
    const lsJSON *sw = lsJSON_GetObjectItemCaseSensitive(def, "swipe");
    const char *to = NULL;
    int anim = LV_SCR_LOAD_ANIM_FADE_IN;
    if (d == LV_DIR_LEFT) { to = jstr(sw, "left", NULL); anim = LV_SCR_LOAD_ANIM_MOVE_LEFT; }
    else if (d == LV_DIR_RIGHT) { to = jstr(sw, "right", NULL); anim = LV_SCR_LOAD_ANIM_MOVE_RIGHT; }
    else if (d == LV_DIR_TOP) { to = jstr(sw, "up", NULL); anim = LV_SCR_LOAD_ANIM_MOVE_TOP; }
    else if (d == LV_DIR_BOTTOM) { to = jstr(sw, "down", NULL); anim = LV_SCR_LOAD_ANIM_MOVE_BOTTOM; }
    if (to && *to) { if (!strcmp(to, "@back")) ls_back(); else ls_goto(to, anim); return; }
    if (d == LV_DIR_RIGHT && jint(def, "back", 1)) ls_back();
}

/* ---------- виджеты ---------- */
static ls_dyn_t *dyn_add(lv_obj_t *o, int kind) {
    if (g_ndyn >= LS_MAX_DYN) return NULL;
    ls_dyn_t *d = &g_dyn[g_ndyn++];
    memset(d, 0, sizeof *d);
    d->obj = o;
    d->kind = (uint8_t)kind;
    return d;
}

static void text_style(lv_obj_t *o, const lsJSON *w) {
    lv_obj_set_style_text_font(o, font_get(jstr(w, "font", "medium"), jint(w, "size", 24)), 0);
    lv_obj_set_style_text_color(o, jcolor(w, "color", 0xFFFFFF), 0);
    lv_obj_set_style_text_letter_space(o, jint(w, "spacing", 0), 0);
    lv_obj_set_style_text_line_space(o, jint(w, "line_space", 0), 0);
    const char *al = jstr(w, "align", "left");
    lv_obj_set_style_text_align(o, !strcmp(al, "center") ? LV_TEXT_ALIGN_CENTER : !strcmp(al, "right") ? LV_TEXT_ALIGN_RIGHT : LV_TEXT_ALIGN_LEFT, 0);
}

static void place(lv_obj_t *o, const lsJSON *w, int auto_h) {
    lv_obj_set_pos(o, jint(w, "x", 0), jint(w, "y", 0));
    int ww = jint(w, "w", 0), hh = jint(w, "h", 0);
    lv_obj_set_size(o, ww > 0 ? ww : LV_SIZE_CONTENT, (hh > 0 && !auto_h) ? hh : LV_SIZE_CONTENT);
    int opa = jint(w, "opa", 100);
    if (opa < 100) lv_obj_set_style_opa(o, (lv_opa_t)(clampi(opa, 0, 100) * 255 / 100), 0);
    if (jint(w, "hidden", 0)) lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
}

static lv_obj_t *mk_label(lv_obj_t *p, const lsJSON *w) {
    lv_obj_t *o = lv_label_create(p);
    lv_obj_remove_style_all(o);
    text_style(o, w);
    place(o, w, 1);
    if (jint(w, "w", 0) > 0) lv_label_set_long_mode(o, jint(w, "wrap", 0) ? LV_LABEL_LONG_WRAP : LV_LABEL_LONG_CLIP);
    lv_label_set_text(o, jstr(w, "text", ""));
    return o;
}

static lv_obj_t *mk_timelabel(lv_obj_t *p, const lsJSON *w, int kind) {
    lv_obj_t *o = lv_label_create(p);
    lv_obj_remove_style_all(o);
    text_style(o, w);
    place(o, w, 1);
    if (jint(w, "w", 0) > 0) lv_label_set_long_mode(o, LV_LABEL_LONG_CLIP);
    ls_dyn_t *d = dyn_add(o, kind);
    if (d) {
        d->fmt = jstr(w, "format", kind == K_CLOCK ? "{HH}:{mm}" : "{dddd}, {d} {MMMMg}");
        struct tm t;
        int k = now_tm(&t);
        dyn_text(d, &t, k);
    }
    return o;
}

static lv_obj_t *mk_rect(lv_obj_t *p, const lsJSON *w) {
    lv_obj_t *o = lv_obj_create(p);
    lv_obj_remove_style_all(o);
    place(o, w, 0);
    lv_obj_set_style_bg_color(o, jcolor(w, "color", 0x2A2E38), 0);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    const char *g = jstr(w, "grad", NULL);
    if (g && *g) {
        lv_obj_set_style_bg_grad_color(o, jcolor(w, "grad", 0), 0);
        lv_obj_set_style_bg_grad_dir(o, LV_GRAD_DIR_VER, 0);
    }
    lv_obj_set_style_radius(o, jint(w, "radius", 0), 0);
    int bw = jint(w, "border", 0);
    if (bw > 0) {
        lv_obj_set_style_border_width(o, bw, 0);
        lv_obj_set_style_border_color(o, jcolor(w, "border_color", 0xFFFFFF), 0);
        lv_obj_set_style_border_opa(o, LV_OPA_COVER, 0);
    }
    lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
    return o;
}

static lv_obj_t *mk_button(lv_obj_t *p, const lsJSON *w) {
    lv_obj_t *o = lv_obj_create(p);
    lv_obj_remove_style_all(o);
    place(o, w, 0);
    lv_color_t bg = jcolor(w, "color", 0x4F8CFF);
    lv_obj_set_style_bg_color(o, bg, 0);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(o, lv_color_darken(bg, 60), LV_STATE_PRESSED);
    lv_obj_set_style_radius(o, jint(w, "radius", 14), 0);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_t *l = lv_label_create(o);
    lv_obj_remove_style_all(l);
    lv_obj_set_style_text_font(l, font_get(jstr(w, "font", "medium"), jint(w, "size", 24)), 0);
    lv_obj_set_style_text_color(l, jcolor(w, "text_color", 0xFFFFFF), 0);
    lv_label_set_text(l, jstr(w, "text", "Кнопка"));
    lv_obj_center(l);
    return o;
}

static lv_obj_t *mk_arc(lv_obj_t *p, const lsJSON *w) {
    lv_obj_t *o = lv_arc_create(p);
    lv_obj_remove_style_all(o);
    place(o, w, 0);
    int th = jint(w, "thick", 10);
    lv_arc_set_rotation(o, jint(w, "rotation", 270));
    lv_arc_set_bg_angles(o, 0, clampi(jint(w, "sweep", 360), 1, 360));
    lv_arc_set_range(o, 0, 1000);
    lv_obj_set_style_arc_width(o, th, LV_PART_MAIN);
    lv_obj_set_style_arc_width(o, th, LV_PART_INDICATOR);
    lv_obj_set_style_arc_color(o, jcolor(w, "track", 0x2A2E38), LV_PART_MAIN);
    lv_obj_set_style_arc_color(o, jcolor(w, "color", 0x4F8CFF), LV_PART_INDICATOR);
    lv_obj_set_style_arc_opa(o, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_arc_opa(o, LV_OPA_COVER, LV_PART_INDICATOR);
    int rnd = jint(w, "rounded", 1);
    lv_obj_set_style_arc_rounded(o, rnd, LV_PART_MAIN);
    lv_obj_set_style_arc_rounded(o, rnd, LV_PART_INDICATOR);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
    int src = src_parse(jstr(w, "source", "static"));
    struct tm t;
    now_tm(&t);
    lv_arc_set_value(o, src_value(src, &t, jint(w, "value", 60)));
    if (src != SRC_STATIC) {
        ls_dyn_t *d = dyn_add(o, K_ARC);
        if (d) d->src = (uint8_t)src;
    }
    return o;
}

static void on_slider(lv_event_t *e) {
    lv_obj_t *o = lv_event_get_target(e);
    uintptr_t src = (uintptr_t)lv_event_get_user_data(e);
    if (src == SRC_BRIGHT) ls_set_brightness(lv_slider_get_value(o));
}

static lv_obj_t *mk_slider(lv_obj_t *p, const lsJSON *w) {
    lv_obj_t *o = lv_slider_create(p);
    lv_obj_remove_style_all(o);
    place(o, w, 0);
    int h = jint(w, "h", 16);
    lv_obj_set_style_bg_color(o, jcolor(w, "track", 0x2A2E38), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_radius(o, LV_RADIUS_CIRCLE, LV_PART_MAIN);
    lv_obj_set_style_bg_color(o, jcolor(w, "color", 0x4F8CFF), LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, LV_PART_INDICATOR);
    lv_obj_set_style_radius(o, LV_RADIUS_CIRCLE, LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(o, jcolor(w, "knob", 0xFFFFFF), LV_PART_KNOB);
    lv_obj_set_style_bg_opa(o, LV_OPA_COVER, LV_PART_KNOB);
    lv_obj_set_style_radius(o, LV_RADIUS_CIRCLE, LV_PART_KNOB);
    lv_obj_set_style_pad_all(o, h / 4 > 2 ? h / 4 : 2, LV_PART_KNOB);
    lv_slider_set_range(o, 0, 100);
    int src = src_parse(jstr(w, "source", "static"));
    lv_slider_set_value(o, src == SRC_BRIGHT ? g_bright : clampi(jint(w, "value", 50), 0, 100), LV_ANIM_OFF);
    lv_obj_add_event_cb(o, on_slider, LV_EVENT_VALUE_CHANGED, (void *)(uintptr_t)src);
    if (src == SRC_BRIGHT) {
        ls_dyn_t *d = dyn_add(o, K_SLIDER);
        if (d) d->src = (uint8_t)src;
    }
    return o;
}

static void hand(lv_layer_t *layer, int cx, int cy, int deg10, int len, int back, int width, lv_color_t c) {
    /* угол в десятых долях градуса от 12 часов по часовой стрелке */
    int deg = (deg10 / 10) % 360;
    int32_t s = lv_trigo_sin((int16_t)deg), co = lv_trigo_cos((int16_t)deg);
    lv_draw_line_dsc_t d;
    lv_draw_line_dsc_init(&d);
    d.color = c;
    d.width = width;
    d.round_start = 1;
    d.round_end = 1;
    d.p1.x = cx - (s * back >> LV_TRIGO_SHIFT);
    d.p1.y = cy + (co * back >> LV_TRIGO_SHIFT);
    d.p2.x = cx + (s * len >> LV_TRIGO_SHIFT);
    d.p2.y = cy - (co * len >> LV_TRIGO_SHIFT);
    lv_draw_line(layer, &d);
}

static void on_analog_draw(lv_event_t *e) {
    lv_obj_t *o = lv_event_get_target(e);
    ls_dyn_t *dd = (ls_dyn_t *)lv_event_get_user_data(e);
    lv_layer_t *layer = lv_event_get_layer(e);
    lv_area_t a;
    lv_obj_get_coords(o, &a);
    int w = lv_area_get_width(&a), h = lv_area_get_height(&a);
    int r = (w < h ? w : h) / 2;
    int cx = a.x1 + w / 2, cy = a.y1 + h / 2;
    if (dd->ticks) {
        for (int i = 0; i < 60; i++) {
            int big = i % 5 == 0;
            int32_t s = lv_trigo_sin((int16_t)(i * 6)), co = lv_trigo_cos((int16_t)(i * 6));
            int r1 = r - 4, r0 = r1 - (big ? r / 8 : r / 22);
            lv_draw_line_dsc_t d;
            lv_draw_line_dsc_init(&d);
            d.color = dd->c_ticks;
            d.width = big ? (r / 40 > 2 ? r / 40 : 2) : 1;
            d.opa = big ? LV_OPA_COVER : LV_OPA_60;
            d.p1.x = cx + (s * r0 >> LV_TRIGO_SHIFT);
            d.p1.y = cy - (co * r0 >> LV_TRIGO_SHIFT);
            d.p2.x = cx + (s * r1 >> LV_TRIGO_SHIFT);
            d.p2.y = cy - (co * r1 >> LV_TRIGO_SHIFT);
            lv_draw_line(layer, &d);
        }
    }
    struct tm t;
    if (!now_tm(&t)) { t.tm_hour = 10; t.tm_min = 10; t.tm_sec = 30; }
    int hw = r / 18 > 3 ? r / 18 : 3;
    hand(layer, cx, cy, ((t.tm_hour % 12) * 60 + t.tm_min) * 5, r * 52 / 100, r / 12, hw, dd->c_hour);
    hand(layer, cx, cy, (t.tm_min * 60 + t.tm_sec) * 10 / 10, r * 78 / 100, r / 12, hw * 2 / 3 > 2 ? hw * 2 / 3 : 2, dd->c_min);
    if (dd->secs) hand(layer, cx, cy, t.tm_sec * 60, r * 86 / 100, r / 6, 2, dd->c_sec);
    lv_draw_rect_dsc_t rd;
    lv_draw_rect_dsc_init(&rd);
    rd.bg_color = dd->secs ? dd->c_sec : dd->c_min;
    rd.radius = LV_RADIUS_CIRCLE;
    lv_area_t c = {cx - hw, cy - hw, cx + hw, cy + hw};
    lv_draw_rect(layer, &rd, &c);
}

static lv_obj_t *mk_analog(lv_obj_t *p, const lsJSON *w) {
    lv_obj_t *o = lv_obj_create(p);
    lv_obj_remove_style_all(o);
    place(o, w, 0);
    if (jint(w, "w", 0) <= 0) lv_obj_set_size(o, 200, 200);
    lv_obj_set_style_radius(o, LV_RADIUS_CIRCLE, 0);
    const char *face = jstr(w, "face", "#14161B");
    if (face && *face) {
        lv_obj_set_style_bg_color(o, jcolor(w, "face", 0x14161B), 0);
        lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
    }
    lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
    ls_dyn_t *d = dyn_add(o, K_ANALOG);
    if (d) {
        d->ticks = (uint8_t)jint(w, "ticks", 1);
        d->secs = (uint8_t)jint(w, "seconds", 1);
        d->c_ticks = jcolor(w, "tick_color", 0xC9CED8);
        d->c_hour = jcolor(w, "hour_color", 0xFFFFFF);
        d->c_min = jcolor(w, "min_color", 0xFFFFFF);
        d->c_sec = jcolor(w, "sec_color", 0xFF5D6C);
        lv_obj_add_event_cb(o, on_analog_draw, LV_EVENT_DRAW_MAIN_END, d);
    }
    return o;
}

static lv_obj_t *mk_widget(lv_obj_t *scr, const lsJSON *w) {
    const char *type = jstr(w, "type", "");
    lv_obj_t *o = NULL;
    if (!strcmp(type, "label")) o = mk_label(scr, w);
    else if (!strcmp(type, "clock")) o = mk_timelabel(scr, w, K_CLOCK);
    else if (!strcmp(type, "date")) o = mk_timelabel(scr, w, K_DATE);
    else if (!strcmp(type, "rect")) o = mk_rect(scr, w);
    else if (!strcmp(type, "button")) o = mk_button(scr, w);
    else if (!strcmp(type, "arc")) o = mk_arc(scr, w);
    else if (!strcmp(type, "slider")) o = mk_slider(scr, w);
    else if (!strcmp(type, "analog")) o = mk_analog(scr, w);
    else { say("ls: неизвестный виджет «%s»", type); return NULL; }
    const lsJSON *link = lsJSON_GetObjectItemCaseSensitive(w, "link");
    if (o && link && jstr(link, "to", NULL) && *jstr(link, "to", "")) {
        lv_obj_add_flag(o, LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_event_cb(o, on_link, LV_EVENT_CLICKED, (void *)link);
    }
    if (o) lv_obj_set_user_data(o, (void *)jstr(w, "id", ""));
    return o;
}

/* ---------- проект ---------- */
void ls_init(const ls_port_t *port) {
    if (port) g_port = *port;
}

static void free_screens(ls_screen_t *s, int n) {
    for (int i = 0; i < n; i++)
        if (s[i].scr) lv_obj_delete(s[i].scr);
}

void ls_unload(void) {
    lv_obj_t *blank = lv_obj_create(NULL);
    lv_screen_load(blank);
    free_screens(g_scr, g_n);
    memset(g_scr, 0, sizeof g_scr);
    g_n = 0;
    g_cur = -1;
    g_ndyn = 0;
    g_sp = 0;
    if (g_proj) lsJSON_Delete(g_proj);
    g_proj = NULL;
}

const char *ls_error(void) { return g_err; }

int ls_load(const char *json) {
    g_err[0] = 0;
    lsJSON *p = lsJSON_Parse(json);
    if (!p) {
        const char *e = lsJSON_GetErrorPtr();
        snprintf(g_err, sizeof g_err, "JSON: ошибка около «%.30s»", e ? e : "?");
        return -1;
    }
    int fmt = jint(p, "format", 1);
    if (fmt > LS_FORMAT) {
        snprintf(g_err, sizeof g_err, "проект формата %d, рантайм понимает до %d — обновите прошивку", fmt, LS_FORMAT);
        lsJSON_Delete(p);
        return -2;
    }
    const lsJSON *screens = lsJSON_GetObjectItemCaseSensitive(p, "screens");
    int n = lsJSON_GetArraySize(screens);
    if (n <= 0) {
        snprintf(g_err, sizeof g_err, "в проекте нет экранов");
        lsJSON_Delete(p);
        return -3;
    }
    if (n > LS_MAX_SCREENS) n = LS_MAX_SCREENS;
    /* старое — запомнить, новое — собрать, показать, старое — удалить */
    ls_screen_t old[LS_MAX_SCREENS];
    int old_n = g_n;
    memcpy(old, g_scr, sizeof old);
    char cur_id[48] = "";
    if (g_cur >= 0 && g_scr[g_cur].id) snprintf(cur_id, sizeof cur_id, "%s", g_scr[g_cur].id);
    lsJSON *old_proj = g_proj;
    g_proj = p;
    memset(g_scr, 0, sizeof g_scr);
    g_n = 0;
    g_ndyn = 0;
    g_sp = 0;
    g_last_sec = -1;
    const lsJSON *st = lsJSON_GetObjectItemCaseSensitive(p, "settings");
    g_lang = jstr(st, "lang", "ru");
    for (int i = 0; i < n; i++) {
        const lsJSON *s = lsJSON_GetArrayItem(screens, i);
        lv_obj_t *scr = lv_obj_create(NULL);
        lv_obj_remove_style_all(scr);
        lv_obj_set_style_bg_color(scr, jcolor(s, "bg", 0x000000), 0);
        lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
        lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_add_event_cb(scr, on_gesture, LV_EVENT_GESTURE, (void *)s);
        g_scr[i].id = jstr(s, "id", "");
        g_scr[i].scr = scr;
        g_scr[i].def = (lsJSON *)s;
        const lsJSON *ws = lsJSON_GetObjectItemCaseSensitive(s, "widgets");
        const lsJSON *w;
        lsJSON_ArrayForEach(w, ws) mk_widget(scr, w);
        g_n++;
    }
    int start = screen_index(cur_id);
    if (start < 0) start = screen_index(jstr(p, "home", NULL));
    if (start < 0) start = 0;
    g_cur = start;
    lv_screen_load(g_scr[start].scr);
    free_screens(old, old_n);
    if (old_proj) lsJSON_Delete(old_proj);
    say("ls: проект «%s», экранов %d, показан «%s»", jstr(p, "name", ""), g_n, g_scr[start].id);
    return 0;
}

void ls_set_brightness(int pct) {
    g_bright = clampi(pct, 1, 100);
    if (g_port.brightness) g_port.brightness(g_bright);
}

void ls_tick(void) {
    struct tm t;
    int known = now_tm(&t);
    int sec = known ? t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec : -2;
    if (sec == g_last_sec) return;
    g_last_sec = sec;
    for (int i = 0; i < g_ndyn; i++) {
        ls_dyn_t *d = &g_dyn[i];
        switch (d->kind) {
        case K_CLOCK:
        case K_DATE: dyn_text(d, &t, known); break;
        case K_ARC: lv_arc_set_value(d->obj, known || d->src == SRC_BRIGHT ? src_value(d->src, &t, 0) : 0); break;
        case K_ANALOG: lv_obj_invalidate(d->obj); break;
        case K_SLIDER:
            if (lv_slider_get_value(d->obj) != g_bright && !lv_obj_has_state(d->obj, LV_STATE_PRESSED))
                lv_slider_set_value(d->obj, g_bright, LV_ANIM_OFF);
            break;
        }
    }
}

int ls_widget_rect(const char *wid, int32_t out[4]) {
    if (g_cur < 0 || !wid) return -1;
    lv_obj_t *scr = g_scr[g_cur].scr;
    uint32_t n = lv_obj_get_child_count(scr);
    for (uint32_t i = 0; i < n; i++) {
        lv_obj_t *c = lv_obj_get_child(scr, (int32_t)i);
        const char *id = (const char *)lv_obj_get_user_data(c);
        if (id && !strcmp(id, wid)) {
            lv_obj_update_layout(c);
            lv_area_t a;
            lv_obj_get_coords(c, &a);
            out[0] = a.x1;
            out[1] = a.y1;
            out[2] = lv_area_get_width(&a);
            out[3] = lv_area_get_height(&a);
            return 0;
        }
    }
    return -1;
}
