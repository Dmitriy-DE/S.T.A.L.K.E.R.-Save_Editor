@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python 3 is required. Install Python 3.11 or newer. 1>&2
        exit /b 1
    )
    set "PYTHON=python"
)

%PYTHON% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo Tkinter is not available in this Python installation. 1>&2
    exit /b 2
)

%PYTHON% app.py
exit /b %errorlevel%
