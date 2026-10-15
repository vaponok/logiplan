# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller progakvoti.spec
# Результат: dist/КвотыNOD.exe (onefile, без консоли)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('resources.json', '.'),
        ('icon.ico', '.'),
        ('images', 'images'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # мусор, который PyQt5-сборки тянут зря — режем размер
        'tkinter', 'unittest', 'pydoc', 'doctest',
        'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngineCore',
        'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtMultimedia',
        'PyQt5.QtBluetooth', 'PyQt5.QtDBus', 'PyQt5.QtDesigner',
        'PyQt5.QtHelp', 'PyQt5.QtLocation', 'PyQt5.QtNfc',
        'PyQt5.QtPositioning', 'PyQt5.QtSensors', 'PyQt5.QtSerialPort',
        'PyQt5.QtSql', 'PyQt5.QtTest', 'PyQt5.QtWebChannel',
        'PyQt5.QtWebSockets', 'PyQt5.QtXmlPatterns',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='КвотыNOD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX любит триггерить антивирусы — не включай
    console=False,        # без чёрного окна
    icon='icon.ico',
)
