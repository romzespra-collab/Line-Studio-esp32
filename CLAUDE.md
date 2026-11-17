# LineStudio — правила проекта

- Вид окна: **Вид 2 «Пульт»** (как PinFlow_esp32: холст в центре), своя рамка, общая палитра (тёмная/светлая).
  Компоновку не менять без вопроса.
- Версия — одна у программы: VERSION в line_studio.py, шапки изменённых файлов, CHANGELOG.md (3 последние версии),
  README.md, README.txt, .spec, .bat. Рантайм (runtime/, engine/, firmware/) — своя версия LS_RUNTIME_VERSION /
  LS_FW_VERSION, поднимать при правке C-кода.
- После правки C-кода (runtime/, engine/) — пересобрать движок: `bash engine/build_engine.sh` (Linux .so и Windows .dll
  через zig) и проверить сборку прошивки обеих плат (arduino-cli, ядро esp32 3.3.7).
- Архив: release/line_studio_vX.Y.Z.zip (`git archive --prefix=line_studio/ HEAD`), один, старый удалить.
- Общие модули из SmartMon (app/window_frame.py, app/int_field.py, app/gh_update*.py) — побайтно как в SmartMon.
