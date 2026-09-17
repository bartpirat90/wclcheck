@echo off
rem Startet die Oberflaeche ohne Konsolenfenster.
rem Verknuepfung davon auf den Desktop legen, dann reicht ein Doppelklick.
setlocal
set "HERE=%~dp0"
if exist "%HERE%.venv\Scripts\wclcheck-gui.exe" (
  start "" "%HERE%.venv\Scripts\wclcheck-gui.exe"
) else (
  echo Umgebung fehlt. Einmalig im Projektordner ausfuehren:
  echo   uv sync --extra gui
  pause
)
