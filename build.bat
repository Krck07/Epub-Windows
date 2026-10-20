@echo off
rem Build a standalone EpubReader.exe (no Python required to run afterwards).
cd /d "%~dp0"

python -m pip install -r requirements.txt pyinstaller || goto :error

rem --onefile  : one portable exe (slower start-up, easiest to move around)
rem --onedir   : a folder with EpubReader.exe (fastest start-up)
python -m PyInstaller --noconfirm --clean --onefile --windowed --name EpubReader ^
  --add-data "epub_reader\web;epub_reader\web" ^
  main.py || goto :error

echo.
echo Done: dist\EpubReader.exe
goto :eof

:error
echo Build failed. & pause & exit /b 1
