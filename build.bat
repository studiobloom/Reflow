@echo off
echo Cleaning previous builds...
rmdir /s /q build
rmdir /s /q dist
del /f /q Reflow.spec

echo Installing requirements...
pip install -r requirements.txt

echo Building Reflow.exe...
pyinstaller --onefile --noconsole --icon=reflow.ico --name Reflow --add-data "reflow.ico;." reflow_gui.py

echo Build complete!
echo Executable is located in the dist folder.
pause 