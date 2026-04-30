# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for PokéDamageCalc.
Build with: build.bat  (uses .venv automatically)
Requires PyInstaller 6+.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules
from pathlib import Path

_ROOT = Path(globals().get("SPECPATH", ".")).resolve()
_USAGE_JSONS: list[tuple[str, str]] = []
for pattern in ("usage_data_*.json", "src/usage_data_*.json"):
    for p in _ROOT.glob(pattern):
        _USAGE_JSONS.append((str(p), "."))
_README = [("README.md", ".")] if (_ROOT / "README.md").exists() else []

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=collect_dynamic_libs("cv2"),
    datas=[
        ("assets", "assets"),
        ("src/calc/bridge.js", "src/calc"),
        ("src/calc/node_modules", "src/calc/node_modules"),
        *_USAGE_JSONS,
        *_README,
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
    name="DamageCalc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_ROOT / "assets" / "app_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DamageCalc",
)
