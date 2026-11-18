# Как добавить плату

Плата — папка `boards/<id>/` с двумя файлами. Больше ничего менять не нужно: редактор найдёт её сам.

## board.json — паспорт
| поле | что |
|---|---|
| id, name, short, maker, chip, screen, touch | имя и описание |
| w, h, shape | экран: ширина, высота, `rect` или `round` |
| core | версия ядра arduino-esp32 (3.3.7) |
| fqbn | плата для arduino-cli со всеми опциями (PSRAM, флеш, разделы, USB) |
| chip_variants | (необяз.) ревизии чипа: имя → опция FQBN |
| usb | VID:PID портов, по которым плату узнавать |
| esptool_chip | чип для esptool (копия прошивки) |
| port | файл порта (`port.h`) |

## port.h — порт (договор, у всех плат одинаковый)
```cpp
#define LSB_ID "<id>"
#define LSB_W 480
#define LSB_H 480
#define LSB_BUF_LINES 40                       // строк в буфере LVGL
static bool lsb_begin();                        // экран, подсветка, тач
static void lsb_flush(int x, int y, int w, int h, uint16_t *px);   // пачка пикселей RGB565 на экран
static bool lsb_touch(int *x, int *y);          // палец: true — нажато
static void lsb_brightness(int pct);            // 0..100
```
Экраны — через Arduino_GFX 1.6.7 (`firmware/libraries`): сотни контроллеров (SPI, QSPI, RGB, DSI). Тач GT911 —
`firmware/drivers/ls_gt911.h`, XPT2046 — `ls_xpt2046.h`; другие (CST816, FT6x36) — добавить драйвер рядом.
Плата без PSRAM: `#define LSB_FONT_CACHE 32` и `#define LSB_LINE_MAX (24 * 1024)` в port.h.

Проверить: новый проект на этой плате → «Залить» (сборка без платы тоже проверяет порт).
