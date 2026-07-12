# -*- mode: python ; coding: utf-8 -*-
import os
import sys

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

# SPECPATH is injected by PyInstaller as the directory containing this file.
# Building the entry-point path from it (instead of a hardcoded relative
# path) keeps the spec correct on Windows/macOS/Linux and regardless of the
# working directory the build is invoked from.
entry_point = os.path.join(SPECPATH, 'scripts', 'desktop_entry.py')

datas = []
binaries = []
hiddenimports = []
datas += collect_data_files('agentbench')
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [entry_point],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# One-dir (exclude_binaries=True + COLLECT below), not one-file: a one-file
# build self-extracts to a temp dir on every launch, which is exactly the
# behavior Windows Defender/SmartScreen heuristics flag as suspicious on an
# unsigned binary. One-dir launches the real exe directly. `upx=False`
# similarly avoids the packed-binary heuristic UPX compression trips.
# `version=` embeds AgentBench.version.txt as a Windows version resource
# (ignored on macOS/Linux) — an exe with no publisher/version metadata at
# all is its own SmartScreen red flag.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AgentBench',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPECPATH, 'src', 'agentbench', 'ui', 'static', 'agentbench-logo.ico'),
    version=os.path.join(SPECPATH, 'AgentBench.version.txt'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='AgentBench',
)

# macOS needs an .app bundle (Dock icon, Finder double-click, WebKit runs
# inside it correctly) — a bare EXE is just a Unix executable there. This is
# a no-op on Windows/Linux, which use the COLLECT'd AgentBench/ folder
# directly.
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='AgentBench.app',
        icon=os.path.join(SPECPATH, 'src', 'agentbench', 'ui', 'static', 'agentbench-logo.ico'),
        bundle_identifier='dev.casualstack.agentbench',
    )
