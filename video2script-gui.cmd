@echo off
rem 启动本地网页 GUI（浏览器会自动打开）
setlocal
chcp 65001 >nul
set "DIR=%~dp0"
if not exist "%DIR%.venv\Scripts\activate.bat" (
  echo [ERROR] venv not found: %DIR%.venv
  echo         run:  python -m venv .venv ^&^& .venv\Scripts\pip install -e .
  pause
  exit /b 1
)
call "%DIR%.venv\Scripts\activate.bat"
video2script-gui --open
endlocal
