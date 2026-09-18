@echo off
rem ---------------------------------------------------------------
rem  同一个入口，两种用法：
rem    把视频文件拖到本文件上  ->  命令行转写（CLI）
rem    直接双击本文件          ->  打开本地网页界面（GUI）
rem  也可以带参数运行：video2script.cmd "x.mp4" --level 3 --cut
rem ---------------------------------------------------------------
setlocal
chcp 65001 >nul
set "DIR=%~dp0"
if not exist "%DIR%.venv\Scripts\activate.bat" goto :novenv
call "%DIR%.venv\Scripts\activate.bat"
if "%~1"=="" (
  echo 没有参数：启动本地网页界面，浏览器会自动打开
  video2script --gui --open
) else (
  video2script %*
)
echo.
echo [done] exit code %ERRORLEVEL%
pause
exit /b 0

:novenv
echo [ERROR] venv not found: %DIR%.venv
echo         run:  python -m venv .venv ^&^& .venv\Scripts\pip install -e .
pause
exit /b 1
