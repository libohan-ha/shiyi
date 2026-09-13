@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -PauseOnReuse %*
if errorlevel 1 pause
