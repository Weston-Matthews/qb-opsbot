@echo off
title qb-opsbot build
rem Run from anywhere: builds from the folder this script lives in
cd /d "%~dp0"
echo Building qb-opsbot
poetry run pyinstaller -y qb-opsbot.spec
pause
