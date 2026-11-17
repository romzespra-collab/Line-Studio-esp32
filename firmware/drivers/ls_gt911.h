// ls_gt911.h  v0.1.0 — тач GT911 для LineStudio (по I2C, опросом; без библиотек).
//
// Журнал:
// v0.1.0: из прошивок ESP32_P4_Panel / ESP32_S3_Panel: разблокировка шины (9+ тактов SCL и STOP — RST тача
//         может быть не подключён, и после перепрошивки GT911 держит SDA в нуле), адрес 0x5D / 0x14 — кто ответит,
//         перепоиск, если молчит; точка 1 с 0x814F; преобразование: бит0 — X↔Y, бит1 — зеркало X, бит2 — зеркало Y.
#pragma once
#include <Arduino.h>
#include <Wire.h>

class LsGT911 {
 public:
  // sda, scl; rst/intr — -1, если не подключены; w, h — логический экран; map — биты преобразования
  LsGT911(int sda, int scl, int rst, int intr, int w, int h, int map)
      : _sda(sda), _scl(scl), _rst(rst), _int(intr), _w(w), _h(h), _map(map) {}

  void begin() {
    if (_rst >= 0) {  // честный сброс: INT низкий во время сброса → адрес 0x5D
      if (_int >= 0) { pinMode(_int, OUTPUT); digitalWrite(_int, LOW); }
      pinMode(_rst, OUTPUT); digitalWrite(_rst, LOW); delay(20);
      digitalWrite(_rst, HIGH); delay(60);
      if (_int >= 0) pinMode(_int, INPUT);
      delay(60);
    }
    busClear();
    Wire.begin(_sda, _scl, 400000);
    probe();
  }

  // true — палец на экране; x, y — в координатах экрана
  bool read(int *x, int *y) {
    uint32_t now = millis();
    if (!_addr) {
      if (now - _probeAt > 2000) probe();
      return false;
    }
    if (now - _readAt < 10) { *x = _x; *y = _y; return _down; }   // не чаще 100 раз в секунду
    _readAt = now;
    uint8_t s = 0;
    if (readReg(0x814E, &s, 1) != 1) {
      if (++_err > 50) { _err = 0; _addr = 0; }
      return false;
    }
    _err = 0;
    if (s & 0x80) {
      uint8_t n = s & 0x0F;
      if (n > 0) {
        uint8_t d[8];
        if (readReg(0x814F, d, 8) == 8) {
          int a = d[1] | (d[2] << 8), b = d[3] | (d[4] << 8);
          if (_map & 1) { int t = a; a = b; b = t; }
          if (_map & 2) a = (_w - 1) - a;
          if (_map & 4) b = (_h - 1) - b;
          _x = a < 0 ? 0 : a >= _w ? _w - 1 : a;
          _y = b < 0 ? 0 : b >= _h ? _h - 1 : b;
          _down = true;
        }
      } else {
        _down = false;
      }
      writeReg(0x814E, 0);
    }
    *x = _x; *y = _y;
    return _down;
  }

  uint8_t address() const { return _addr; }
  void setMap(int m) { _map = m; }

 private:
  int _sda, _scl, _rst, _int, _w, _h, _map;
  uint8_t _addr = 0;
  uint32_t _probeAt = 0, _readAt = 0;
  int _err = 0, _x = 0, _y = 0;
  bool _down = false;

  void busClear() {
    pinMode(_sda, INPUT_PULLUP); pinMode(_scl, OUTPUT_OPEN_DRAIN); digitalWrite(_scl, HIGH); delayMicroseconds(10);
    for (int i = 0; i < 16; i++) { digitalWrite(_scl, LOW); delayMicroseconds(6); digitalWrite(_scl, HIGH); delayMicroseconds(6); }
    pinMode(_sda, OUTPUT_OPEN_DRAIN); digitalWrite(_sda, LOW); delayMicroseconds(6);
    digitalWrite(_scl, HIGH); delayMicroseconds(6); digitalWrite(_sda, HIGH); delayMicroseconds(10);
  }
  bool ping(uint8_t a) { Wire.beginTransmission(a); return Wire.endTransmission() == 0; }
  void probe() {
    _probeAt = millis();
    _addr = ping(0x5D) ? 0x5D : ping(0x14) ? 0x14 : 0;
    Serial.printf("LS log тач GT911: %s\n", _addr == 0x5D ? "0x5D" : _addr == 0x14 ? "0x14" : "не найден");
  }
  int readReg(uint16_t reg, uint8_t *buf, int len) {
    Wire.beginTransmission(_addr); Wire.write(reg >> 8); Wire.write(reg & 0xFF);
    if (Wire.endTransmission(false) != 0) return 0;
    Wire.requestFrom((int)_addr, len);
    int i = 0;
    while (Wire.available() && i < len) buf[i++] = Wire.read();
    return i;
  }
  void writeReg(uint16_t reg, uint8_t v) {
    Wire.beginTransmission(_addr); Wire.write(reg >> 8); Wire.write(reg & 0xFF); Wire.write(v); Wire.endTransmission();
  }
};
