# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置:pyinstaller packaging/liteseal.spec --noconfirm
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas, binaries, hiddenimports = [], [], []
for pkg in ("qfluentwidgets", "pymupdf"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
# pymupdf 2.0 导入即需 onnx 模型配置,必须随包收集(漏掉会启动即 FileNotFoundError)
datas += collect_data_files("pymupdf", include_py_files=False)
datas.append((os.path.join(ROOT, "app", "resources", "icon.png"), "app/resources"))

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
              "PySide6.QtWebChannel", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtOpenGL", "PySide6.QtPdf"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LiteSeal",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(ROOT, "app", "resources", "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LiteSeal",
)
