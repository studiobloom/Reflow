@echo off
setlocal enabledelayedexpansion

REM Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Python is not installed or not in PATH. Please install Python 3.6 or higher.
    exit /b 1
)

REM Check if the first argument is provided
if "%~1"=="" (
    echo Usage: webflow_exporter.bat URL [options]
    echo Example: webflow_exporter.bat https://example.webflow.io --output my-site
    exit /b 1
)

REM Pass all arguments to the Python script
python webflow_exporter.py %*

if %ERRORLEVEL% neq 0 (
    echo Export failed with error code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
)

echo Export completed successfully!
exit /b 0 