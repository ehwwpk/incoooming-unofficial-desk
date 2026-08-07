@echo off
setlocal
pushd "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"
set "exit_code=%ERRORLEVEL%"
popd
exit /b %exit_code%
