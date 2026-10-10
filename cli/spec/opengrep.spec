# -*- mode: python ; coding: utf-8 -*-
datas = []
datas += [("_opengrepinstall/semgrep/semgrep_interfaces", "semgrep/semgrep_interfaces")]
datas += [("_opengrepinstall/semgrep/templates", "semgrep/templates")]

binaries = [("_opengrepinstall/semgrep/bin", "semgrep/bin")]

a = Analysis(
    ['_opengrepinstall/semgrep/__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'jaraco',
        'google.protobuf',
        # 'contextvars',
        # 'unicodedata',
        # 'requests',
        # 'certifi',
        'chardet'
        # 'charset_normalizer'
        # 'attrs', 
        # 'boltons', 
        # 'click-option-group', 
        # 'click', 
        # 'colorama', 
        # 'defusedxml', 
        # 'exceptiongroup', 
        # 'glom', 
        # 'jsonschema', 
        # 'opentelemetry-api', 
        # 'opentelemetry-sdk', 
        # 'opentelemetry-exporter-otlp-proto-http', 
        # 'opentelemetry-instrumentation-requests',
        # 'opentelemetry.context',
        # 'opentelemetry.context.contextvars_context',
        # 'opentelemetry.context.threading_context',
        # 'packaging', 
        # 'peewee', 
        # 'requests', 
        # 'rich', 
        # 'ruamel.yaml', 
        # 'tomli', 
        # 'typing-extensions', 
        # 'urllib3', 
        # 'wcmatch'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=2
)
pyz = PYZ(a.pure)

# Optimised interpreter.
options = [('O', None, 'OPTION'), ('X utf8', None, 'OPTION')]

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    # [],
    options,
    # exclude_binaries=True,
    name='opengrep',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False, # True is not recommended for Windows.
    upx=False, # True is only used in Windows it seems.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='opengrep.ico',
)

# coll = COLLECT(
#     exe,  # Executable
#     a.binaries,  # Binary files
#     a.datas,  # Data files
#     name='opengrep',  # Name of the output directory
# )
