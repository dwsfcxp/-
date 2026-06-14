@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   要素式起诉状转换器 - Web 界面
echo ========================================
echo.
echo 正在启动... 浏览器将自动打开 http://127.0.0.1:7860
echo.
python app.py
pause
