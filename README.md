# Process Miner Starter (Phase 1 of the Build Route)

This is a working, tested mini pipeline that does exactly what Phase 1 of the
build route asks for: turn a raw CSV into a process map and three KPIs,
running entirely on your own machine, no web app, no cloud, no cost.

It has already been run once to confirm it works — `output/` contains a
sample result so you can see what you're aiming for before you run it
yourself.

## What's in here

```
process-miner-starter/
  data/
    sample_orders.csv      <- raw, messy sample data (generated, not hand-written)
    eventlog.db             <- created when you run map_to_eventlog.py
  src/
    generate_sample_data.py <- makes the sample CSV (skip this once you have real data)
    map_to_eventlog.py      <- maps raw columns into Case ID / Activity / Timestamp / Resource
    discover.py              <- the actual mining: process map, variants, KPIs
  output/
    process_map.png         <- the process map image
    variants.csv             <- every distinct path through the process, ranked by frequency
    kpis.json                 <- case count, avg duration, top variant, etc.
  requirements.txt
  run_all.bat                <- runs all three scripts in order (Windows)
```

## One-time setup (Windows)

**1. Install Python.** Go to python.org/downloads, download the latest
Python 3.11+ installer, run it. **On the first install screen, tick "Add
python.exe to PATH" before clicking Install** — this is the single most
common thing people miss, and if you skip it, `python` won't be recognized
in a terminal later.

Verify it worked: open PowerShell (Start menu -> type "PowerShell" -> Enter)
and run:
```
python --version
```
You should see something like `Python 3.11.x`. If you get an error, restart
your PC (PATH changes need a restart to take effect) and try again.

**2. Install Graphviz.** This is a separate, non-Python program that
actually draws the process map — the Python `graphviz` package is just a
thin wrapper around it. Go to graphviz.org/download, download the Windows
installer, run it, and when the installer asks, choose the option to **add
Graphviz to the system PATH** (wording varies by version — look for "for
all users" or "add to PATH").

Verify it worked: **open a new PowerShell window** (must be new, so it
picks up the updated PATH) and run:
```
dot -V
```
You should see a version number. If you get "not recognized," Graphviz
wasn't added to PATH — reinstall and make sure you tick that option, or
manually add its `bin` folder (something like
`C:\Program Files\Graphviz\bin`) to your system PATH via
Settings -> System -> About -> Advanced system settings -> Environment
Variables.

**3. Unzip this project** somewhere easy to find, e.g. `C:\Users\<you>\process-miner-starter`.

## Running it

Open PowerShell, navigate into the project folder, and run these commands
one at a time:

```powershell
cd C:\Users\<you>\process-miner-starter

python -m venv venv
```

Activate the virtual environment:
```powershell
venv\Scripts\Activate.ps1
```

**If that gives you a red "running scripts is disabled" error** (a common
Windows security default, not a real problem), run this once and try again:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

You'll know it worked because your prompt now starts with `(venv)`. Now
install the two Python packages this project needs:
```powershell
pip install -r requirements.txt
```

Then run everything:
```powershell
.\run_all.bat
```

This runs, in order: generate the sample data, map it into an event log,
then discover the process map, variants, and KPIs. When it's done, open
`output\process_map.png` — you should see the same process map included in
this download.

## What to actually look at

Open `output\process_map.png` first — that picture is process discovery,
made visible. Each box is an activity, each arrow is "how often did B
happen right after A," and the arrow thickness scales with frequency. The
sample data has some deliberate messiness built in: a credit-check rework
loop, a skipped-approval fast path, a payment-reminder branch, and a
repeated packing step — see if you can spot all four in the picture before
you check `output\variants.csv`, which ranks every distinct path through
the process by how common it is.

Then open `output\kpis.json` — this is the same style of output your
dashboard will eventually show on-screen instead of in a file.

## Using this with your own data instead of the sample

1. Put your CSV in the `data\` folder.
2. Open `src\map_to_eventlog.py` and edit two things near the top:
   `INPUT_CSV` (your file name) and `COLUMN_MAP` (which of your columns
   are the case ID, activity name, timestamp, and resource).
3. Run `python src\map_to_eventlog.py` then `python src\discover.py`
   directly (skip `generate_sample_data.py` — that's only for the demo
   data).

## Where this fits in the bigger plan

This is Phase 1 of the Solo Build Route artifact from earlier in our
conversation — "Prove the Core Loop." Once you're comfortable with what
every part of `discover.py` is doing (ask your AI assistant to walk through
any line you don't understand — that's exactly what it's for), Phase 2 is
wrapping this same logic in a Streamlit app so someone else can use it
through a browser instead of a terminal.

---

## Part 2: Connecting to a real source system (`extract_from_db.py`)

This is the connector layer — pulling data automatically from a live
database instead of someone manually exporting and uploading a CSV. It was
built and tested around four rules, and together they're the actual answer
to "accurate, smooth, without any delays or lags":

**1. Never re-read the whole source table.** The connector tracks a
*watermark* — a column that only ever increases, almost always called
something like `updated_at` or `last_modified` — and each sync only asks
for rows changed since the last one. This is the single biggest lever for
both speed (small syncs finish in seconds) and being a good guest on
someone else's production database (a full re-scan every few minutes is
exactly the kind of thing that gets an integration tool banned by an IT
team).

**2. Page large pulls.** Even an incremental batch can be big after the
connector's been off a while, or on the very first backfill. Pulling in
chunks (2,000 rows at a time here) avoids one giant slow query.

**3. Make writes idempotent.** If a sync is interrupted and reruns, nothing
should duplicate. This is enforced at the database level with a `UNIQUE`
constraint on `(case_id, activity, timestamp, resource)` — not just "the
code should be careful," but a genuine guarantee.

**4. Only advance the watermark after a successful write.** If a sync fails
partway through, the next run resumes from the last confirmed-good point
instead of silently skipping the rows that failed.

### Try it yourself — see the delta behavior directly

This is worth actually running once so you can see incremental sync
working with your own eyes, not just take it on faith:

```powershell
# 1. Create a fake "source system" (a SQLite file standing in for a real database)
python src\setup_demo_source_db.py

# 2. First sync -- pulls everything, since nothing's been synced before
python src\extract_from_db.py --backfill

# 3. Run it again immediately -- watch it pull 0 rows, because nothing changed
python src\extract_from_db.py

# 4. Pretend time has passed in the source system
python src\setup_demo_source_db.py --simulate

# 5. Sync again -- watch it pull ONLY the handful of rows that actually changed
python src\extract_from_db.py
```

Every run is logged in a `sync_log` table inside `data\eventlog.db` — query
it any time to see exactly how far behind your data is:
```powershell
python -c "import sqlite3,pandas as pd; print(pd.read_sql('SELECT * FROM sync_log', sqlite3.connect('data/eventlog.db')))"
```

Once you've seen it work, run `python src\discover.py` — it reads from the
same `event_log` table regardless of whether the data came from a CSV or a
live database, which is the point of keeping the mining engine separate
from ingestion.

### Pointing it at your real database

Open `src\extract_from_db.py` and change the four values near the top:
`SOURCE_DB_URL` (a connection string — examples for Postgres, SQL Server,
and MySQL are commented in the file), `SOURCE_TABLE`, `WATERMARK_COLUMN`
(ask whoever owns that database which column reliably updates on every
change — if nothing does, that's a conversation to have with them before
building further, because incremental sync depends on it existing), and
`COLUMN_MAP`. Uncomment the matching driver in `requirements.txt` and
`pip install -r requirements.txt` again.

### Scheduling it (this is what actually removes the lag)

Running the script by hand isn't a real integration — a steady, automatic
cadence is. On Windows, use **Task Scheduler**:

1. Open Task Scheduler (Start menu -> type "Task Scheduler").
2. Create Task (not "Basic Task" — the full dialog gives you more control).
3. **General tab:** name it (e.g. "Process Miner Sync"), select "Run whether
   user is logged on or not."
4. **Triggers tab:** New -> Daily, then tick "Repeat task every" and set it
   to however fresh you need the data (every 10-15 minutes is a reasonable
   starting point for most business processes) with a duration of "Indefinitely."
5. **Actions tab:** New -> Program/script: browse to `schedule_sync.bat` in
   this project folder.
6. Save. It'll ask for your Windows password since you selected "run
   whether logged on or not."

That's the whole mechanism — a small, fast, incremental sync running every
few minutes, each one only touching what changed since the last one. This
is also exactly the pattern that avoids the kind of slowdown we discussed
with Power Automate Process Mining: small, frequent, targeted queries
instead of large synchronous recomputation.

One thing to plan for once you're integrating a real company's database
rather than the demo: agree with whoever owns that system on running
against a **read replica** if one exists, and on a sensible sync interval
for their specific system — a transactional database that's also serving
live customer traffic deserves a lighter touch than the demo above.

---

## Part 3: Phase 2 — the Streamlit app (`app.py`)

This wraps everything above in something clickable. It's the exact same
functions from `discover.py`, imported directly (not rewritten) — the
mining logic doesn't know or care that it's being called from a browser
instead of a terminal.

Run it:
```powershell
streamlit run app.py
```
or just double-click `run_app.bat`. It opens automatically in your
browser at `http://localhost:8501`.

You get three data source options in the sidebar:

**Upload a CSV** — pick any CSV, then tell it which column is which (Case
ID, Activity, Timestamp, Resource) with dropdowns instead of editing
Python. This is the "someone who isn't you can use it unaided" bar from
the Phase 2 exit criterion.

**Use the Phase 1 sample data** — the same synthetic order-to-cash data
from Part 1, useful for demoing without needing a real file on hand.

**Sync from the demo source database** — click "Run sync now" and it
calls the real `extract_from_db.py` connector, then displays whatever's
in `event_log` immediately. This is Part 2 and Part 3 wired together:
the same incremental sync you ran by hand earlier, now behind a button.

Every run shows the process map, the four headline KPIs, and the ranked
variant table — all three tested and confirmed working end to end before
this was sent to you.

This is also the natural point to stop and re-read the "Ready for Phase 3"
exit criterion from the Solo Build Route: **someone who isn't you** should
be able to open this app, load their own data, and get a process map back
without you explaining anything. Try it on someone before moving on.
