@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" goto missing
"%PYTHON_EXE%" -c "import PySide6, faster_whisper, pyaudiowpatch, sentencepiece, ctranslate2, scipy" >nul 2>&1
if errorlevel 1 goto missing
"%PYTHON_EXE%" app.py
if errorlevel 1 pause
exit /b
:missing
echo 请先双击 setup.cmd 完成首次准备。
pause
