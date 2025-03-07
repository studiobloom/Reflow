#!/bin/bash

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed or not in PATH. Please install Python 3.6 or higher."
    exit 1
fi

# Check if the first argument is provided
if [ -z "$1" ]; then
    echo "Usage: ./webflow_exporter.sh URL [options]"
    echo "Example: ./webflow_exporter.sh https://example.webflow.io --output my-site"
    exit 1
fi

# Pass all arguments to the Python script
python3 webflow_exporter.py "$@"

if [ $? -ne 0 ]; then
    echo "Export failed with error code $?."
    exit $?
fi

echo "Export completed successfully!"
exit 0 