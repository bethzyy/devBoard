@echo off
cd /d %~dp0
echo Starting Project Dashboard...
echo Open http://localhost:9999 in your browser
echo.
python -m dashboard.server
