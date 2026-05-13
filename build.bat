@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === Cleaning previous build ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo === Running PyInstaller ===
".venv\Scripts\pyinstaller.exe" ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --clean ^
  --name quant_trader ^
  --collect-submodules binance ^
  --exclude-module matplotlib ^
  --exclude-module numpy ^
  --exclude-module pandas ^
  --exclude-module scipy ^
  --exclude-module pytest ^
  --exclude-module IPython ^
  --exclude-module notebook ^
  --exclude-module PyQt5 ^
  --exclude-module PyQt6 ^
  --exclude-module PySide2 ^
  --exclude-module PySide6 ^
  gui.py

if exist dist\quant_trader.exe (
  echo.
  echo === Build OK ===
  dir dist\quant_trader.exe | findstr quant_trader
) else (
  echo.
  echo === Build FAILED ===
  exit /b 1
)
