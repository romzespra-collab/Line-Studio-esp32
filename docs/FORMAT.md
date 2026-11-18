# Формат проекта LineStudio (format 1)

Проект — JSON (`projects/<id>.json`). В прошивку и превью уходит то же самое без служебных полей
(`modules/mod_project.runtime_json`). Рантайм — `runtime/ls_runtime.c`.

```json
{"format": 1, "name": "Мой экран", "board": "guition_4848s040", "home": "main", "rev": 3,
 "settings": {"lang": "ru", "zone": "Киев", "tz": "EET-2EEST,M3.5.0/3,M10.5.0/4", "wifi": false, "brightness": 80},
 "screens": [
   {"id": "main", "name": "Главный", "bg": "#000000", "back": true, "swipe": {"up": "bright"},
    "widgets": [
      {"id": "w1a2b3", "type": "clock", "name": "Часы", "x": 0, "y": 140, "w": 480, "h": 0,
       "format": "{HH}:{mm}", "font": "bold", "size": 120, "color": "#FFFFFF", "align": "center",
       "link": {"to": "bright", "anim": "left"}}]}],
 "map": {"main": [0, 0]}}
```

- Координаты — пиксели экрана платы, (0,0) — левый верхний угол. `h: 0` у текста — высота по тексту.
- Цвета — `#RRGGBB`. `opa` — видимость 0..100. `hidden` — скрыт.
- `link.to` — id экрана или `@back`; `anim`: fade, left, right, up, down, over, none.
- `swipe`: left/right/up/down → id экрана или `@back`. `back: true` — свайп вправо без цели = назад.
- Шрифты: `medium`, `bold`, `light` (Montserrat, любой размер 6..400 — tiny_ttf).

## Блоки
| type | свойства |
|---|---|
| clock, date | format, font, size, color, align, spacing |
| label | text, font, size, color, align, spacing, wrap |
| analog | face, tick_color, hour_color, min_color, sec_color, ticks, seconds |
| rect | color, grad, radius, border, border_color |
| button | text, font, size, color, text_color, radius |
| arc | source (static, seconds, minutes, hours, day, brightness), value, thick, color, track, rotation, sweep, rounded |
| slider | source (brightness, static), value, color, track, knob |
| icon | icon (имя Material Icons), size, color — в рантайм уходит `glyph` (символ) |
| image | asset (id в `assets`), fit (cover, contain, stretch) — в рантайм уходит `src` = `<asset>@<w>x<h><f>` |
| weather | style (line, card), city (номер в settings.cities), font, size, color, muted, icon, desc, city_name |

`assets`: `{"a1b2c3": {"name": "фото.png", "file": "a1b2c3.png", "w": 640, "h": 480}}` — файлы в
`projects/<id>.assets/`. `settings.cities`: `[{"name": "Киев", "lat": 50.45, "lon": 30.52}]` (до 8).

Формат времени: `{HH} {H} {hh} {h} {mm} {ss} {AMPM} {d} {dd} {M} {MM} {YYYY} {YY} {dddd} {ddd} {MMMM} {MMMMg} {MMM}`,
`{^…}` — заглавными.

Новый блок: функция `mk_*` в `ls_runtime.c` + описание в `CATALOG` (`mod_project.py`) + пересобрать движок
(`bash engine/build_engine.sh`).
