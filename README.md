# Gasmeter Downloader

A Windows desktop application (PyQt6 + QtCharts) that automatically downloads
daily gas-meter logfiles from an **AI-on-the-Edge** device, stores every reading
in a local SQLite database (the single source of truth), interpolates missing
days, supports manual correction and restore, archives logfiles forever, and
visualizes consumption (kWh/m³, year-over-year comparison, trendlines with
forward projection).

- Native Windows light/dark theme (follows the OS live)
- Fully bilingual: English / German (auto-detected from Windows locale)
- Self-updating via the shared `github_updater` package fed by GitHub Releases
- **No file logging** — all events go to an in-memory UI log panel only

## Features

- **Sync** — scans the configured download window (default 30 days) on the
  device file server, downloads every missing daily logfile, extracts the last
  successful meter reading, stores it and moves the file into the archive.
  Today is always skipped; yesterday is always included when missing.
- **Logfile formats** — current CSV (`data_YYYY-MM-DD.csv`, value = column 3 of
  the last `no error` row) and legacy TXT (`log_YYYY-MM-DD.txt`, last
  `Value: … Error: no error` match). Files can be imported manually from
  anywhere (archive, USB, …) at any date.
- **Three stored values per day** — `import_value`, `interpolated_value`,
  `modified_value` plus a source. Trust hierarchy: **modified > imported >
  interpolated**. Only the Modified value is user-editable; logfile imports
  never overwrite manual corrections; restore reverts to the import (or the
  interpolation).
- **Interpolation** — any gap with both a left and a right reading is filled
  linearly (no maximum gap length). Gaps at the start or end of the data are
  left alone. Interpolation re-runs after every data mutation and is idempotent.
- **Statistics & charts** — KPI cards, cumulative meter line (interpolated
  spans drawn dashed), daily/weekly/monthly usage bars with OLS trend + 30-day
  projection overlay, and a monthly column chart with previous-year comparison.
  One global date-range filter drives the table and every chart simultaneously
  ("AJAX-like" refresh).
- **Units** — the database stores m³. kWh is a derived display unit computed
  per calendar day from the gas-parameter interval valid on that day
  (`kWh = m³ · calorific value · Z-value`).
- **Gas parameters** — dated intervals (calorific value / Z-value) are stored
  in SQLite, overlap-validated, and seeded on first run from the configured
  defaults (`11.342` kWh/m³, `0.9589`).
- **Updates** — checks GitHub Releases of `reserve85/Gasmeter-Downloader`,
  downloads the `.exe` and applies it via the shared updater (Windows, frozen
  builds only).

## Requirements

- Python 3.11+ (Windows)
- See `requirements.txt` (PyQt6, PyQt6-Charts, `github-updater` from the
  `Python_Units` git repo, pyyaml, cryptography; pytest/ruff for development)

## Setup (development)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main          # or: python app/main.py
```

On first run the app creates `config/app_config.yaml`, the folders
`downloads/` and `archive/`, and the database `gasmeter.db` next to the source
root (or next to the `.exe` in a packaged build).

### Device

Default device IP: `192.168.10.65` (change in Settings). The client reads the
directory listing at `http://<ip>/fileserver/log/data/` and downloads
`data_YYYY-MM-DD.csv` per day.

## Tests

```powershell
pytest tests/ -q
ruff check app/ tests/ --select E,F,W --ignore E501
```

GUI tests run headless with `QT_QPA_PLATFORM=offscreen` (set automatically by
the test suite).

## Build & release

The repository ships GitHub Actions:

- `ci.yml` — lint + test on every push/PR (`windows-latest`, Python 3.11).
- `release.yml` — on a `v*` tag: runs the tests, writes the tag into
  `app/_version.py`, builds a one-file windowed `.exe` with PyInstaller
  (`--hidden-import PyQt6.QtCharts`), zips it, and publishes a GitHub Release
  with `.exe` + `.zip`.
- `cleanup.yml` — daily purge of old workflow runs/artifacts.

Manual equivalent:

```powershell
pyinstaller --onefile --windowed --name GasmeterDownloader --hidden-import PyQt6.QtCharts app/main.py
```

## Runtime layout (next to the `.exe`)

```
GasmeterDownloader.exe
gasmeter.db                 (SQLite - single source of truth)
config/app_config.yaml      (settings: IP, paths, language, unit, gas defaults, token)
downloads/                  (logfile download folder)
archive/                    (archived logfiles - never deleted)
```

## Notes / limitations

- Meter values are stored as SQLite REAL; all domain math uses
  `decimal.Decimal` (REAL round-trips through its string form).
- Historical days older than the download window are imported through the
  *Import logfiles…* action (they are not downloaded automatically).
- The GitHub token is optional (public releases need none) and is stored
  encrypted with a local machine key.
