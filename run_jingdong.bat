@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d D:\taojinbi

rem 计划任务以系统身份运行时 PATH 与桌面不同，这里写死 python 路径，找不到再退回 PATH
set "PY=C:\Users\Admin\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=python"

echo ---- jd run start ---- >> D:\taojinbi\logs\run.log
"%PY%" D:\taojinbi\jingdong.py >> D:\taojinbi\logs\run.log 2>&1
echo ---- jd run end (exit %errorlevel%) ---- >> D:\taojinbi\logs\run.log
