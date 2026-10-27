# -*- mode: python ; coding: utf-8 -*-
# Build with:  poetry run pyinstaller -y qb-opsbot.spec   (from the repository root)
# Output: dist/qb-opsbot/qb-opsbot.exe with config.example.json and the sample data next to it.

block_cipher = None


a = Analysis(['run_opsbot.py'],
             pathex=[SPECPATH],
             binaries=[],
             datas=[('config.example.json', '.'),
                    ('data/*.csv', 'data')],
             hiddenimports=['win32timezone'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='qb-opsbot',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='qb-opsbot')
