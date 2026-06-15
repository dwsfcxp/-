@echo off
chcp 65001 >nul
REM 创建桌面快捷方式：要素式文书转换器
setlocal
set "TARGET=%~dp0desktop_app.py"
set "WORKDIR=%~dp0"

REM 优先用 pythonw.exe（无控制台黑窗），找不到则回退 python.exe
where pythonw.exe >nul 2>&1 && (set "PYEXE=pythonw.exe") || (set "PYEXE=python.exe")

powershell -NoProfile -Command ^
  "$ws=New-Object -ComObject WScript.Shell;" ^
  "$desktop=[Environment]::GetFolderPath('Desktop');" ^
  "$lnk=Join-Path $desktop '要素式文书转换器.lnk';" ^
  "$s=$ws.CreateShortcut($lnk);" ^
  "$s.TargetPath='%PYEXE%';" ^
  "$s.Arguments='\"%TARGET%\"';" ^
  "$s.WorkingDirectory='%WORKDIR%';" ^
  "$s.Description='普通起诉状/申请书 -> 要素式 转换器';" ^
  "$s.Save();" ^
  "Write-Host ('已创建桌面图标: ' + $lnk);"

echo.
echo ✅ 双击桌面【要素式文书转换器】图标即可启动应用窗口。
echo    （首次启动需几秒加载，请稍候）
echo.
pause
