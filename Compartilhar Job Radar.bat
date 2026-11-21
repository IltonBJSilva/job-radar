@echo off
REM Gera um .zip para outra pessoa usar, sem nenhum dado seu (fica em dist\).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\compartilhar.ps1"
pause
