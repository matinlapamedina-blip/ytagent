@echo off
chcp 65001 >nul
title ComfyUI - Generador de imagenes
cd /d "D:\ComfyUI\ComfyUI_windows_portable"

echo ============================================================
echo   ComfyUI - generador de imagenes
echo ============================================================
echo.
echo   Deja esta ventana ABIERTA mientras generas imagenes.
echo   La primera vez tarda 1-2 minutos en arrancar.
echo.
echo   Cuando veas "To see the GUI go to: http://127.0.0.1:8188"
echo   ya puedes volver a la app de ytagent.
echo.
echo   Para cerrar: pulsa Ctrl+C o cierra esta ventana.
echo ============================================================
echo.

call run_nvidia_gpu.bat

pause
