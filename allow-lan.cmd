@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\allow-lan.ps1" %*
pause
