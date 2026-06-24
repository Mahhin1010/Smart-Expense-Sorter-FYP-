@echo off
title Smart Sorter System Orchestrator
echo Launching system orchestration script via PowerShell...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_system.ps1"
pause
