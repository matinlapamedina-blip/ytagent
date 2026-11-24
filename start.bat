@echo off
chcp 65001 >nul
title ytagent - Agente de YouTube
cd /d "%~dp0"

echo ============================================================
echo   ytagent - Agente de contenido para YouTube
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No encuentro el entorno virtual.
    echo Ejecuta primero:  python -m venv .venv
    echo Y luego:         .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

set "PYTHONPATH=%CD%\src"
set "PYTHONIOENCODING=utf-8"

echo   Abriendo la interfaz en tu navegador...
echo   Para cerrar: pulsa Ctrl+C en esta ventana.
echo.
".venv\Scripts\python.exe" -m streamlit run "src\ytagent\dashboard.py" --server.port 8501

pause
