chcp 65001 >nul
@echo off
rem build_exe.bat  v0.2.0 — собрать dist\line_studio.exe (класть в папку программы: рядом engine\, fonts\, boards\, firmware\, modules\)
cd /d "%~dp0"
echo === [1/4] Python ===
python --version || (echo Нет Python 3.10+ & pause & exit /b 1)
echo === [2/4] Библиотеки ===
python -m pip install -r requirements.txt pyinstaller || (pause & exit /b 1)
echo === [3/4] PyInstaller ===
python -m PyInstaller --noconfirm line_studio.spec || (pause & exit /b 1)
copy /y dist\line_studio.exe . >nul
echo === [4/4] Проверка ===
line_studio.exe --selftest || (echo Проверка не прошла & pause & exit /b 1)
echo Готово: line_studio.exe
pause
