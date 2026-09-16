@echo off
REM Runs ONE incremental sync cycle. This is the file you point Windows
REM Task Scheduler at -- see README.md "Scheduling it" for the exact steps.
REM It does NOT loop or sleep itself; the scheduler is what provides the
REM steady cadence (e.g. every 10 minutes), which is what keeps each run
REM small, fast, and low-impact on the source system.

cd /d %~dp0
call venv\Scripts\activate.bat
python src\extract_from_db.py
