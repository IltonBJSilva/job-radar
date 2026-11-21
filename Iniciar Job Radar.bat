@echo off
REM Abre o Job Radar (na primeira vez instala o que precisa).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\iniciar.ps1"
if errorlevel 1 pause
