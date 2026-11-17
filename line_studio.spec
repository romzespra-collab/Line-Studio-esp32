# line_studio.spec  v0.1.0 — PyInstaller: один файл без консоли. modules/ не вшиваются (лежат рядом с exe).
a = Analysis(["line_studio.pyw"], pathex=["."], datas=[], hiddenimports=["serial.tools.list_ports", "fontTools.subset"],
             excludes=["modules", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
                       "PySide6.QtMultimedia", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtCharts", "tkinter"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="line_studio", console=False, upx=False)
