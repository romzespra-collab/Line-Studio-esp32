#!/usr/bin/env bash
# build_engine.sh  v0.1.0 — собрать движок превью: engine/bin/line_engine.so (Linux) и line_engine.dll (Windows x64).
# Тот же LVGL (firmware/libraries/lvgl, lv_conf.h рядом) и тот же рантайм (runtime/), что уходят в прошивку.
# Windows-DLL собирается кросс-компилятором zig (pip install ziglang) — ставить на ПК ничего не нужно.
#   bash engine/build_engine.sh            — обе
#   bash engine/build_engine.sh linux|win  — одну
set -e
cd "$(dirname "$0")/.."
LV=firmware/libraries/lvgl
SRC="$(find $LV/src -name '*.c' | grep -v '/thorvg/' | sort) $(ls runtime/*.c) engine/le_engine.c"
FLAGS="-O2 -I$LV -Iruntime -DLV_LVGL_H_INCLUDE_SIMPLE -w"
OUT=engine/bin
mkdir -p $OUT /tmp/le_obj
what="${1:-all}"

build() {   # $1 — компилятор (с аргументами), $2 — файл, $3 — доп. флаги, $4 — папка объектов
  objs=""
  mkdir -p "$4"
  for f in $SRC; do
    o="$4/$(echo "$f" | tr '/' '_').o"
    if [ ! -f "$o" ] || [ "$f" -nt "$o" ] || [ firmware/libraries/lv_conf.h -nt "$o" ]; then
      $1 $FLAGS $3 -c "$f" -o "$o" &
      while [ "$(jobs -r | wc -l)" -ge 8 ]; do sleep 0.05; done
    fi
    objs="$objs $o"
  done
  wait
  $1 -shared -o "$2" $objs $5
  echo "собрано: $2 ($(wc -c < "$2") байт)"
}

if [ "$what" = all ] || [ "$what" = linux ]; then
  build "gcc" $OUT/line_engine.so "-fPIC -fvisibility=hidden" /tmp/le_obj/linux "-lm"
fi
if [ "$what" = all ] || [ "$what" = win ]; then
  ZIG="${PYTHON:-python3} -m ziglang cc -target x86_64-windows-gnu"
  build "$ZIG" $OUT/line_engine.dll "" /tmp/le_obj/win "-s"
fi
