@echo off
setlocal
cd /d "%~dp0"
echo Starting CompeteRivio AI...
if not exist ".venv\Scripts\python.exe" (
    echo Creating a local Python environment...
    python -m venv .venv
    if errorlevel 1 goto failed
)
set "COMPETERIVIO_PYTHON=.venv\Scripts\python.exe"
"%COMPETERIVIO_PYTHON%" -c "import sys, streamlit, pandas, plotly, requests, dotenv, reportlab; from google import genai; assert sys.version_info >= (3,11); assert tuple(int(v) for v in streamlit.__version__.split('.')[:2]) >= (1,62)" >nul 2>&1
if errorlevel 1 (
    echo Installing project dependencies. Internet access is required for first setup.
    "%COMPETERIVIO_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)
if not exist ".env" copy /y ".env.example" ".env" >nul
"%COMPETERIVIO_PYTHON%" -m streamlit run app.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Could not start the dashboard. Check the message above.
echo Python 3.11 or newer and internet access for first setup are required.
pause
exit /b 1
