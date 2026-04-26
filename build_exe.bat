@echo off
echo Building ModbusLens executables with icon...
pyinstaller --onefile --icon=assets/icon.ico main.py
pyinstaller --onefile --windowed --icon=assets/icon.ico gui_main.py
if exist dist\main.exe (
    move dist\main.exe dist\ModbusLens_CLI.exe
    echo CLI executable created: dist\ModbusLens_CLI.exe
) else (
    echo CLI build failed!
)
if exist dist\gui_main.exe (
    move dist\gui_main.exe dist\ModbusLens_GUI.exe
    echo GUI executable created: dist\ModbusLens_GUI.exe
) else (
    echo GUI build failed!
)
echo Build complete!
pause