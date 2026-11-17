// port.h  v0.1.0 — Guition JC4880P443C (ESP32-P4 + C6, 4.3″ IPS 480×800 → 800×480, ST7701S MIPI-DSI, тач GT911).
// Пины и тайминги — из прошивки ESP32_P4_Panel 2.61 (проверены на плате).
//
// Журнал:
// v0.1.0: первая версия: Arduino_GFX 1.6.7 (DSI 2 линии, DPI 34 МГц, 12/42/42 2/8/166, RST GPIO5), поворот 1 —
//         драйвер сам поворачивает каждую пачку при записи в кадр; подсветка GPIO23; тач GT911 SDA7/SCL8, RST22/INT21,
//         преобразование 5 (X↔Y + зеркало Y: сырые координаты — в портретной системе панели).
#pragma once
#include <Arduino_GFX_Library.h>
#include "ls_gt911.h"

#define LSB_ID "guition_jc4880p443c"
#define LSB_W 800
#define LSB_H 480
#define LSB_BUF_LINES 48
#define LSB_BL 23
#define LSB_BL_HZ 20000
#define LSB_BL_MIN 5

static Arduino_ESP32DSIPanel *lsb_dsi = new Arduino_ESP32DSIPanel(
    12, 42, 42,      // hsync: pulse, back porch, front porch
    2, 8, 166,       // vsync: pulse, back porch, front porch
    34000000,        // DPI 34 МГц
    500);            // lane bit rate, Мбит/с
static Arduino_DSI_Display *lsb_gfx = new Arduino_DSI_Display(
    480, 800, lsb_dsi, 1 /*горизонтально*/, true,
    5 /*RST*/, st7701_dsi_init_operations, sizeof(st7701_dsi_init_operations) / sizeof(lcd_init_cmd_t));
static LsGT911 lsb_tp(7, 8, 22, 21, LSB_W, LSB_H, 5);

static bool lsb_begin() {
  pinMode(LSB_BL, OUTPUT);
  digitalWrite(LSB_BL, LOW);
  if (!lsb_gfx->begin()) return false;
  lsb_gfx->fillScreen(0x0000);
  ledcAttach(LSB_BL, LSB_BL_HZ, 10);
  lsb_tp.begin();
  return true;
}
static void lsb_flush(int x, int y, int w, int h, uint16_t *px) { lsb_gfx->draw16bitRGBBitmap(x, y, px, w, h); }
static bool lsb_touch(int *x, int *y) { return lsb_tp.read(x, y); }
static void lsb_brightness(int pct) {
  pct = pct < 0 ? 0 : pct > 100 ? 100 : pct;
  int duty = pct == 0 ? 0 : (LSB_BL_MIN + (100 - LSB_BL_MIN) * pct / 100) * 1023 / 100;
  ledcWrite(LSB_BL, duty);
}
