@echo off
rem ---------------------------------------------------------------
rem  Drag a video file onto this .cmd  ->  CLI transcription
rem  Want the GUI? double-click video2script-gui.cmd
rem  All arguments are passed straight through to the video2script CLI
rem ---------------------------------------------------------------
setlocal
chcp 65001 >nul
set "DIR=%~dp0"
if "%~1"=="" (
  echo Usage: drop a video file on this .cmd, or run:
  echo     video2script.cmd "C:\path\to\video.mp4" [--lang zh] [--model medium] [--level 3] [--cut]
  echo.
  pause
  exit /b 1
)
if not exist "%DIR%.venv\Scripts\activate.bat" (
  echo [ERROR] venv not found: %DIR%.venv
  echo         run:  python -m venv .venv ^&^& .venv\Scripts\pip install -e .
  pause
  exit /b 1
)
call "%DIR%.venv\Scripts\activate.bat"
video2script %*
echo.
echo [done] exit code %ERRORLEVEL%
pause
endlocal
