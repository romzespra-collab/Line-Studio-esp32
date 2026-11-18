// ls_xpt2046.h  v0.2.0 — резистивный тач XPT2046 (CYD) для LineStudio: свой SPI (VSPI), без библиотек.
//
// Журнал:
// v0.2.0: первая версия — чтение как в XPT2046_Touchscreen 1.4 (конвейер команд, Z = Z1 + 4095 − Z2, среднее
//         двух ближайших из трёх), преобразование: бит0 — X↔Y, бит1 — зеркало X, бит2 — зеркало Y (до масштаба),
//         масштаб сырых 0..4095 по краям x0..x1 / y0..y1 на экран.
#pragma once
#include <Arduino.h>
#include <SPI.h>

class LsXPT2046 {
 public:
  LsXPT2046(int clk, int miso, int mosi, int cs, int irq, int w, int h, int map, int x0, int x1, int y0, int y1)
      : _clk(clk), _miso(miso), _mosi(mosi), _cs(cs), _irq(irq), _w(w), _h(h), _map(map),
        _x0(x0), _x1(x1), _y0(y0), _y1(y1) {}

  void begin() {
    _spi = new SPIClass(VSPI);
    _spi->begin(_clk, _miso, _mosi, _cs);
    pinMode(_cs, OUTPUT);
    digitalWrite(_cs, HIGH);
    if (_irq >= 0) pinMode(_irq, INPUT);
    Serial.println("LS log тач XPT2046");
  }

  bool read(int *x, int *y) {
    uint32_t now = millis();
    if (now - _at < 10) { *x = _x; *y = _y; return _down; }
    _at = now;
    if (_irq >= 0 && digitalRead(_irq) == HIGH) { _down = false; *x = _x; *y = _y; return false; }
    int16_t d[6] = {0};
    _spi->beginTransaction(SPISettings(2000000, MSBFIRST, SPI_MODE0));
    digitalWrite(_cs, LOW);
    _spi->transfer(0xB1);
    int z1 = _spi->transfer16(0xC1) >> 3;
    int z = z1 + 4095;
    int z2 = _spi->transfer16(0x91) >> 3;
    z -= z2;
    if (z >= 400) {
      _spi->transfer16(0x91);
      d[0] = _spi->transfer16(0xD1) >> 3;
      d[1] = _spi->transfer16(0x91) >> 3;
      d[2] = _spi->transfer16(0xD1) >> 3;
      d[3] = _spi->transfer16(0x91) >> 3;
    }
    d[4] = _spi->transfer16(0xD0) >> 3;
    d[5] = _spi->transfer16(0) >> 3;
    digitalWrite(_cs, HIGH);
    _spi->endTransaction();
    if (z < 400) { _down = false; *x = _x; *y = _y; return false; }
    int a = best(d[0], d[2], d[4]), b = best(d[1], d[3], d[5]);   // сырые X, Y (как в XPT2046_Touchscreen)
    if (_map & 1) { int t = a; a = b; b = t; }
    if (_map & 2) a = 4095 - a;
    if (_map & 4) b = 4095 - b;
    int sx = (a - _x0) * _w / (_x1 - _x0), sy = (b - _y0) * _h / (_y1 - _y0);
    _x = sx < 0 ? 0 : sx >= _w ? _w - 1 : sx;
    _y = sy < 0 ? 0 : sy >= _h ? _h - 1 : sy;
    _down = true;
    *x = _x; *y = _y;
    return true;
  }

 private:
  int _clk, _miso, _mosi, _cs, _irq, _w, _h, _map, _x0, _x1, _y0, _y1;
  SPIClass *_spi = nullptr;
  uint32_t _at = 0;
  int _x = 0, _y = 0;
  bool _down = false;
  static int best(int a, int b, int c) {
    int ab = abs(a - b), ac = abs(a - c), bc = abs(b - c);
    if (ab <= ac && ab <= bc) return (a + b) / 2;
    if (ac <= ab && ac <= bc) return (a + c) / 2;
    return (b + c) / 2;
  }
};
