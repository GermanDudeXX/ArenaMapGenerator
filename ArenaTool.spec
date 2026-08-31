# PyInstaller-Bauplan: eine einzelne .exe.
#
# Die Grafiken wandern mit ins Bundle und landen beim Start in einem
# Temp-Verzeichnis. Dorthin darf nichts exportiert werden - das regelt
# za/paths.py, das zwischen "woher kommen die Grafiken" und "wohin gehen
# die Ergebnisse" unterscheidet.
#
# Bauen:  python -m PyInstaller --noconfirm ArenaTool.spec
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # Nur die Grafiken, die die Karte wirklich benutzt - der Rest des
    # CraftPix-Packs liegt ohnehin nicht in assets/.
    datas=[('assets', 'assets')],
    # `tools` wird erst zur Laufzeit importiert (beim Export aus dem
    # Viewer). PyInstaller findet solche Importe nicht von allein.
    hiddenimports=[
        'tools', 'tools.export_tiled', 'tools.export_godot',
        'tkinter', 'tkinter.filedialog',
        # Der Updater spricht HTTPS. `http` und `urllib.request` standen
        # vorher in den Ausschluessen - ohne sie faellt die Abfrage aus.
        'urllib.request', 'http.client', 'ssl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Was nicht gebraucht wird, macht die Datei nur gross und den Start
    # langsam. numpy zieht pygame optional, wir benutzen es nicht.
    # Alles, was dieses Werkzeug nicht anfasst. Was hier faelschlich
    # steht, faellt beim Selbsttest auf - der laeuft nach jedem Bau.
    excludes=[
        'numpy', 'PIL', 'matplotlib', 'scipy', 'pytest',
        'setuptools', 'pip', 'pkg_resources',
        'unittest', 'doctest', 'pydoc', 'pdb', 'lib2to3',
        'xmlrpc', 'ftplib', 'sqlite3', 'curses', 'asyncio',
        'multiprocessing', 'distutils', 'test',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ArenaMapTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Kein Konsolenfenster beim Doppelklick. Die Kommandozeilenschalter
    # funktionieren weiter, ihre Ausgabe ist dann aber nur in den Dateien
    # zu sehen, die sie schreiben - deshalb schreibt --selbsttest einen
    # Bericht und verlaesst sich nicht auf stdout.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
