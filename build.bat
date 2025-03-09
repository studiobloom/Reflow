@echo off
echo Cleaning previous builds...
rmdir /s /q build
rmdir /s /q dist
del /f /q Reflow.spec

echo Installing requirements...
pip install -r requirements.txt

echo Building Reflow.exe...
pyinstaller --onefile --noconsole --icon=icon.ico --name Reflow reflow_gui.py

echo Build complete!
echo Executable is located in the dist folder.
pause 