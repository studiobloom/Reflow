@echo off
REM Reflow - Webflow Site Exporter/Scraper
REM This script makes it easier to run the Reflow tool on Windows.

REM Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: Python is required but not installed.
    exit /b 1
)

REM Check if the required dependencies are installed
python -c "import requests, bs4, argparse" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Installing required dependencies...
    pip install -r requirements.txt
)

REM Run the Reflow CLI
python reflow_cli.py %* 