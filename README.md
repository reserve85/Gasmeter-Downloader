# Gasmeter Downloader

A Windows desktop application (PyQt6 + Matplotlib) that automatically downloads
daily gas-meter logfiles from an **AI-on-the-Edge** device, stores every reading
in a local SQLite database (the single source of truth), interpolates missing
days, supports manual correction and restore, archives logfiles forever, and
visualizes consumption (kWh/m³, year-over-year comparison, trendlines with
forward projection).

- Native Windows light/dark theme (follows the OS live) or forced via the
  **Theme** toolbar button (**Automatic / Dark / Light**)
- App icon (title bar, taskbar, dialogs, exe) generated in
  `app/resources/` (`scripts/generate_icon.py`)
- Fully bilingual: English / German (auto-detected from Windows locale)
- Self-updating via the shared `github_updater` package fed by GitHub Releases
  (public-repo checks work **without a token**)
- **No file logging** — all events go to an in-memory UI log panel only
- Optional **automatic download on startup** (Settings → checkbox)

## Features

- **Sync** — scans the configured download window (default 30 days) on the
  device file server, downloads every missing daily logfile, extracts the last
  successful meter reading, stores it and moves the file into the archive.
  Today is always skipped; yesterday is always included when missing. Can be
  triggered automatically at startup.
- **Logfile formats** — current CSV (`data_YYYY-MM-DD.csv`, value = column 3 of
  the last `no error` row) and legacy TXT (`log_YYYY-MM-DD.txt`, last
  `Value: … Error: no error` match). Files can be imported manually from
  anywhere (archive, USB, …) at any date.
- **Three stored values per day** — `import_value`, `interpolated_value`,
  `modified_value` plus a source. Trust hierarchy: **modified > imported >
  interpolated**. Only the Modified value is user-editable; logfile imports
  never overwrite manual corrections; restore (with confirmation dialog)
  reverts to the import (or the interpolation). Manual edits must stay
  **non-decreasing** between their neighbours.
- **Interpolation** — any gap with both a left and a right reading is filled
  linearly (no maximum gap length). Gaps at the start or end of the data are
  left alone. Interpolation re-runs after every data mutation and is idempotent.
- **Statistics & charts (rendered by Matplotlib)** — KPI overview (with unit
  suffixes plus *year-so-far* and *year-end projection*, optionally based on the
  previous year). Every diagram is a Matplotlib figure: a cumulative meter line
  (every point visible, hover/click shows the date / meter / usage info bubble
  and highlights the point or bar), daily/weekly/monthly usage **line charts**
  with points + an OLS trend overlay, and a monthly column chart (x axis
  `MM/YYYY`, integer values inside the bars, never `1,8E+03`). Hover info stays
  visible until the mouse moves away; a click shows the same info. Every card
  can be opened **big in a modal window** (double-click, "Show in big").
- **Independent filters** — the table filters by day (From/To pickers +
  rolling presets such as "last 30 days"), the charts filter by **whole years
  only** (e.g. 2023–2026). Rolling presets never rewrite the pickers; each tab
  refreshes instantly ("AJAX-like") through the dashboard controller.
- **Units** — the database stores m³. kWh is a derived display unit computed
  per calendar day from the gas-parameter interval valid on that day
  (`kWh = m³ · calorific value · Z-value`).
- **Gas parameters** — dated intervals (calorific value / Z-value) are stored
  in SQLite, overlap-validated, and seeded on first run from the configured
  defaults (`11.342` kWh/m³, `0.9589`). Adding a new interval **automatically
  closes the previous one** (`valid_to` = day before) for a seamless transition.
- **Updates** — checks GitHub Releases of `reserve85/Gasmeter-Downloader`,
  downloads the `.exe` and applies it via the shared updater (Windows, frozen
  builds only). The check runs in the background **automatically after every
  program start** (the dialog only opens when an update is actually available;
  otherwise the result goes to the log panel) and on demand via Settings. The
  repository is **public**, so the check needs **no GitHub token**. Downloads
  show a live progress bar, then the app exits so the new version takes over.

## Requirements

- Python 3.11+ (Windows)
- See `requirements.txt` (PyQt6, Matplotlib, `github-updater` from the
  `reserve85/github_updater` git repo, pyyaml, cryptography; pytest/ruff for development)

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
  (`--hidden-import matplotlib.backends.backend_qtagg`), zips it, and publishes
  a GitHub Release with `.exe` + `.zip`.
- `cleanup.yml` — daily purge of old workflow runs/artifacts.

Manual equivalent:

```powershell
pyinstaller --onefile --windowed --name GasmeterDownloader --icon app/resources/Icon.ico --add-data "app/resources;app/resources" --hidden-import matplotlib.backends.backend_qtagg app/main.py
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
- The GitHub token is **optional** (the repo is public) and - if entered in
  Settings - is **never saved in clear text**: it is encrypted with a key
  derived from the machine (PBKDF2/Fernet, same scheme as MusicSceneReleaser).
  A config copy cannot be decrypted on another machine; legacy clear-text or
  old key-file ciphertext is migrated automatically at the next start.
