// port.h  v0.1.0 — Guition ESP32-4848S040 (ESP32-S3, 4″ IPS 480×480, ST7701 RGB, тач GT911).
// Пины и тайминги — из прошивки ESP32_S3_Panel 2.61 (проверены на плате).
//
// Журнал:
// v0.1.0: первая версия: Arduino_GFX 1.6.7 (ST7701 type9, pclk 12 МГц, bounce-буфер 20 строк — не увеличивать),
//         LVGL рисует пачками прямо в кадр панели (без Canvas), подсветка GPIO38 ШИМ 150 Гц, тач GT911 SDA19/SCL45.
//
// Договор порта (все платы одинаково): LSB_W, LSB_H, LSB_ID; lsb_begin(), lsb_flush(), lsb_touch(), lsb_brightness().
#pragma once
#include <Arduino_GFX_Library.h>
#include "ls_gt911.h"

#define LSB_ID "guition_4848s040"
#define LSB_W 480
#define LSB_H 480
#define LSB_BUF_LINES 40      // строк в буфере LVGL (два буфера во внутренней памяти)
#define LSB_BL 38
#define LSB_BL_HZ 150
#define LSB_BL_MIN 10         // % ШИМ при яркости 1

static Arduino_DataBus *lsb_bus = new Arduino_SWSPI(GFX_NOT_DEFINED, 39, 48, 47, GFX_NOT_DEFINED);
static Arduino_ESP32RGBPanel *lsb_rgb = new Arduino_ESP32RGBPanel(
    18, 17, 16, 21,
    11, 12, 13, 14, 0,
    8, 20, 3, 46, 9, 10,
    4, 5, 6, 7, 15,
    1, 10, 8, 50, 1, 10, 8, 20,
    0, 12000000, false, 0, 0, 480 * 20);
static Arduino_RGB_Display *lsb_gfx = new Arduino_RGB_Display(
    480, 480, lsb_rgb, 0, true,
    lsb_bus, GFX_NOT_DEFINED, st7701_type9_init_operations, sizeof(st7701_type9_init_operations));
static LsGT911 lsb_tp(19, 45, -1, -1, LSB_W, LSB_H, 0);

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
