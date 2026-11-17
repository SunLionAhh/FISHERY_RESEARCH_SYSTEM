@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" goto NOPY
start "" /min powershell -NoProfile -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:5000/workbench'"
"%PY%" "%~dp004_SOURCE_CODE\run.py"
goto END
:NOPY
echo 未找到项目虚拟环境：.venv\Scripts\python.exe
pause
:END
