@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  python -m venv "%~dp0..\.venv"
  if errorlevel 1 goto failed
)
if exist "wheels\pyside6_essentials-6.11.2-cp310-abi3-win_amd64.whl" (
  "%PYTHON_EXE%" -m pip install --no-index --find-links wheels -r requirements-lock.txt
) else (
  "%PYTHON_EXE%" -m pip install -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple
)
if errorlevel 1 goto failed
"%PYTHON_EXE%" prepare_models.py
if errorlevel 1 goto failed
echo 准备完成，请双击 start.cmd。
pause
exit /b 0
:failed
echo 准备失败，请检查上方提示与网络连接后重试。
pause
exit /b 1
