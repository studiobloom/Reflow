#!/bin/bash
# Reflow - Webflow Site Exporter/Scraper
# This script makes it easier to run the Reflow tool.

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

# Check if the required dependencies are installed
if ! python3 -c "import requests, bs4, argparse" &> /dev/null; then
    echo "Installing required dependencies..."
    pip install -r requirements.txt
fi

# Run the Reflow CLI
python3 reflow_cli.py "$@" 