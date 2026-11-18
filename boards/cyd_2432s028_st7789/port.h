// port.h  v0.2.0 — CYD ESP32-2432S028 с ST7789 (два разъёма USB) — 2.8″ 320×240, тач XPT2046. Без PSRAM.
// Пины — из прошивки ESP32_Screen 1.9.3 (TFT_eSPI: ST7789, порядок BGR, инверсия выкл.).
//
// Журнал:
// v0.2.0: первая версия: Arduino_GFX ST7789 по HSPI 40 МГц (SCK14 MOSI13 MISO12 CS15 DC2), поворот 1 (USB справа),
//         MADCTL с BGR, подсветка GPIO21; тач XPT2046 на VSPI (CLK25 MISO39 MOSI32 CS33 IRQ36).
// Не проверено на плате: если красный и синий перепутаны — LSB_BGR 0; если цвета негативом — LSB_INVERT 1;
// если тач зеркальный — поменяйте LSB_TOUCH_MAP (бит0 X↔Y, бит1 зеркало X, бит2 зеркало Y).
#pragma once
#include <Arduino_GFX_Library.h>
#include "ls_xpt2046.h"

#define LSB_ID "cyd_2432s028_st7789"
#define LSB_W 320
#define LSB_H 240
#define LSB_BUF_LINES 24
#define LSB_FONT_CACHE 32     // без PSRAM — меньше букв в кэше
#define LSB_LINE_MAX (24 * 1024)
#define LSB_BL 21
#define LSB_BL_HZ 5000
#define LSB_BL_MIN 5
#define LSB_BGR 1
#define LSB_INVERT 0
#define LSB_TOUCH_MAP 3

static Arduino_DataBus *lsb_bus = new Arduino_ESP32SPI(2 /*DC*/, 15 /*CS*/, 14 /*SCK*/, 13 /*MOSI*/, 12 /*MISO*/, HSPI);
static Arduino_ST7789 *lsb_gfx = new Arduino_ST7789(lsb_bus, GFX_NOT_DEFINED, 1, false, 240, 320);
static LsXPT2046 lsb_tp(25, 39, 32, 33, 36, LSB_W, LSB_H, LSB_TOUCH_MAP, 200, 3700, 240, 3800);

static bool lsb_begin() {
  pinMode(LSB_BL, OUTPUT);
  digitalWrite(LSB_BL, LOW);
  if (!lsb_gfx->begin(40000000)) return false;
  if (LSB_BGR) {   // поворот 1 + BGR: MX | MV | BGR
    lsb_bus->beginWrite();
    lsb_bus->writeC8D8(0x36, 0x40 | 0x20 | 0x08);
    lsb_bus->endWrite();
  }
  lsb_gfx->invertDisplay(LSB_INVERT);
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
