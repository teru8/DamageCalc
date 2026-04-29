# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for PokéDamageCalc.
Build with: build.bat  (uses .venv automatically)
Requires PyInstaller 6+.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=collect_dynamic_libs("cv2"),
    datas=[
        ("assets", "assets"),
        *collect_data_files("cv2"),
        *collect_data_files("winocr"),
    ],
    hiddenimports=[
        # winocr / WinRT
        "winocr",
        "winrt.windows.media.ocr",
        "winrt.windows.globalization",
        "winrt.windows.graphics.imaging",
        "winrt.windows.storage.streams",
        "winrt.windows.foundation",
        # Pillow
        "PIL",
        "PIL.Image",
        # PyQt5
        "PyQt5",
        "PyQt5.QtSvg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "torchvision", "easyocr"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PokeDamageCalc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PokeDamageCalc",
)
