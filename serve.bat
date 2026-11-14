@echo off
rem Serve the static web build on http://localhost:8000/web/
cd /d "%~dp0"
if "%~1"=="" (set PORT=8000) else (set PORT=%~1)
echo VOXELTERM web build: http://localhost:%PORT%/web%
echo Press Ctrl-C to stop.
python -m http.server %PORT%
