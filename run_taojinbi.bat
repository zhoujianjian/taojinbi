@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d D:\taojinbi
python D:\taojinbi\taojinbi_adb.py >> D:\taojinbi\logs\run.log 2>&1
