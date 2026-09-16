@echo off
REM Runs the full Phase 1 pipeline in order: generate data -> map to event log -> discover.
REM Run this from the project folder, with your virtual environment already activated.

echo [1/3] Generating sample data...
python src\generate_sample_data.py
if errorlevel 1 goto :error

echo [2/3] Mapping to event log...
python src\map_to_eventlog.py
if errorlevel 1 goto :error

echo [3/3] Running discovery...
python src\discover.py
if errorlevel 1 goto :error

echo.
echo Done. Open output\process_map.png to see your process map.
goto :eof

:error
echo.
echo Something failed above -- scroll up to read the error message.
exit /b 1
