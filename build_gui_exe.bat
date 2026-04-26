@echo off
setlocal

echo Building ModbusLens GUI executable...

if not exist dist mkdir dist

pyinstaller --noconfirm --clean --onefile --windowed ^
  --name ModbusLens ^
  --icon assets\icon.ico ^
  --add-data "assets\icon.ico;assets" ^
  gui_main.py

if exist dist\ModbusLens.exe (
    echo Build complete: dist\ModbusLens.exe
) else (
    echo Build failed.
)

pause
