@echo off
REM Rebuild OOTPCoachEditor.exe from source. Requires: pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --icon icon.ico ^
  --name OOTPCoachEditor ^
  --exclude-module numpy --exclude-module pandas --exclude-module matplotlib ^
  --exclude-module unittest --exclude-module pydoc --exclude-module doctest ^
  --exclude-module email --exclude-module http --exclude-module xml ^
  --exclude-module xmlrpc --exclude-module pdb --exclude-module lib2to3 ^
  --exclude-module distutils --exclude-module setuptools --exclude-module test ^
  --exclude-module sqlite3 --exclude-module bz2 --exclude-module lzma ^
  --exclude-module ssl --exclude-module hashlib --exclude-module asyncio ^
  --exclude-module multiprocessing --exclude-module concurrent ^
  --exclude-module decimal --exclude-module logging ^
  app.py
echo.
echo Built dist\OOTPCoachEditor.exe
certutil -hashfile dist\OOTPCoachEditor.exe SHA256
