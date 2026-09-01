# Implementation Plan — Four Bug Fixes

## Overview

Fix four distinct issues: (1) duplicate archive files when the database is deleted and the sync re-downloads everything, (2) the Compare tab not refreshing after an archive import, (3) chart legend text unreadable in dark mode, and (4) table column headers truncated when German translation is active.

---

## Issue 1: Duplicate archive files after DB deletion

### Problem

When the database is deleted but the archive folder already contains files, the next startup runs `SyncMissingLogfilesUseCase`. Since `repo.all_days_with_import()` returns an empty set, every day in the download window appears "missing". The sync downloads each logfile from the device and then calls `FileArchiver.archive()`. Because the archive already has a file with the same name, `_unique_target()` appends `_1`, creating duplicates like `data_2022-11-28_1.csv`.

### Solution

Before downloading a logfile from the device, check whether the archive already contains a file for that day. If it does, import from the archive file instead of downloading. This avoids both duplicate files and unnecessary network traffic.

### Files

| File | Change |
|---|---|
| `app/application/ports.py` | Add `find_by_date(day: date) -> Path \| None` to `LogfileArchiver` protocol. |
| `app/infrastructure/filesystem/file_archiver.py` | Implement `find_by_date(day)`: scan archive dir for files containing `data_{day.isoformat()}`. |
| `app/application/use_cases/sync.py` | In `run()`, check archive before downloading each candidate day. |
| `tests/conftest.py` | Add `find_by_date` to `FakeArchiver`. |
| `tests/test_infrastructure/test_archiver.py` | Tests for `find_by_date`. |
| `tests/test_application/test_sync.py` | Test: sync imports from archive when file exists there. |

### Functions

**New — `FileArchiver.find_by_date(day: date) -> Path | None`**

Scan `self._archive_dir` for any file whose name contains `data_{day.isoformat()}`. Return the first match (sorted), or `None`. This matches the device's naming convention (`data_YYYY-MM-DD.csv`).

**Modified — `SyncMissingLogfilesUseCase.run()`**

In the `for day in sorted(candidates)` loop, before calling `self._download_one(day)`:
1. Call `self._archiver.find_by_date(day)`.
2. If a path is returned, call `import_logfile(self._repo, self._parser, self._logger, archive_path)` directly. Log via `LogCategory.ARCHIVE`. Append outcome to `imported`. Skip download.
3. If no archive file found, proceed with existing download flow.

---

## Issue 2: Compare tab not refreshing after archive import

### Problem

`CompareTab._on_controller_dashboard()` only calls `_recompute()` when the unit has changed. After an archive import, `controller.refresh()` emits `charts_dashboard_changed`, but the Compare tab skips the recompute because the unit is unchanged. Charts show stale data.

### Solution

Always recompute when the controller emits a dashboard change. Update the unit combo only if the unit changed.

### Files

| File | Change |
|---|---|
| `app/presentation/compare.py` | Modify `_on_controller_dashboard` to always call `_recompute()`. |
| `tests/test_presentation/test_charts_smoke.py` | Test: Compare tab recomputes on controller signal even if unit unchanged. |

### Functions

**Modified — `CompareTab._on_controller_dashboard`**

```python
def _on_controller_dashboard(self, dashboard) -> None:
    if dashboard.unit != self._unit:
        self._unit = dashboard.unit
        self._unit_combo.blockSignals(True)
        index = self._unit_combo.findData(dashboard.unit)
        self._unit_combo.setCurrentIndex(index if index >= 0 else 0)
        self._unit_combo.blockSignals(False)
    self._recompute()  # always recompute — data may have changed
```

---

## Issue 3: Chart legend text unreadable in dark mode

### Problem

All five `ax.legend()` calls use `frameon=False` but do not set `labelcolor`. Matplotlib's default legend text color is black, invisible on the dark background (`#1E1E1E`).

### Solution

Add `labelcolor=_TEXT_COLOR[dark]` to every `ax.legend()` call. Import `_TEXT_COLOR` in both `charts.py` and `compare.py`.

### Files

| File | Change |
|---|---|
| `app/presentation/charts.py` | Add `_TEXT_COLOR` to mpl_charts import. Add `labelcolor=_TEXT_COLOR[dark]` to both `ax.legend()` calls (lines 124, 168). |
| `app/presentation/compare.py` | Add `_TEXT_COLOR` to mpl_charts import. Add `labelcolor=_TEXT_COLOR[dark]` to three `ax.legend()` calls (lines 372, 437, 503). |
| `tests/test_presentation/test_charts_smoke.py` | Test: legend text color matches `_TEXT_COLOR` for both light and dark mode. |

---

## Issue 4: Table headers truncated in German

### Problem

`MeterTableView` does not set any resize mode on its horizontal header. The default `Interactive` mode uses fixed column widths sized for English text. German translations are longer, so headers get truncated.

### Solution

Set `ResizeToContents` on the horizontal header. This auto-fits both header text and cell content.

### Files

| File | Change |
|---|---|
| `app/presentation/meter_table.py` | Add `QHeaderView` import. Set `ResizeToContents` on horizontal header in `__init__`. |
| `tests/test_presentation/test_table_model.py` | Test: verify header resize mode is `ResizeToContents`. |

### Specific changes

In `meter_table.py` line 8, add `QHeaderView` to the QtWidgets import. After line 27, add:
```python
self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
```

---

## Implementation Order

1. **Issue 4** (table headers) — smallest, self-contained.
2. **Issue 3** (legend colors) — small, touches only legend calls.
3. **Issue 2** (compare refresh) — one-line logic fix.
4. **Issue 1** (archive duplicates) — largest change.

## Testing

- Run `python -m pytest tests/ -q` after each issue (baseline: 298 passed).
- Run `ruff check app/ tests/` after all changes.

---

## Issue 5: Compare charts double-click → big dialog

### Problem

The three compare charts (meter, usage, monthly) have no double-click handler. The normal Charts tab opens a resizable `BigChartDialog` on double-click via `ChartCard._open_big()`. The compare tab uses raw `MplChartCanvas` widgets with no callback wired.

### Solution

Wire `set_double_click_callback` on each compare view to open a `BigChartDialog`. Store the last render per view so the dialog can re-render.

### Files

| File | Change |
|---|---|
| `app/presentation/compare.py` | Store last render per view. Wire double-click callbacks. Add `_open_big(view_key)`. Import `BigChartDialog` from `charts.py`. |

### Changes

In `__init__`, add `self._last_renders: dict[str, MplRender] = {}`.

In `_build_chart_area`, after creating each view:
```python
self._meter_view.set_double_click_callback(lambda: self._open_big("meter"))
self._usage_view.set_double_click_callback(lambda: self._open_big("usage"))
self._monthly_view.set_double_click_callback(lambda: self._open_big("monthly"))
```

In `_recompute`, store each render before passing to `store_interaction`:
```python
render = _compare_meter_render(...)()
self._last_renders["meter"] = render
self._meter_view.store_interaction(render)
```

New method `_open_big(key)`:
```python
def _open_big(self, key: str) -> None:
    render = self._last_renders.get(key)
    if render is None:
        return
    title = self._tr.t(f"charts.{key}.title") if key != "monthly" else self._tr.t("charts.monthly.title")
    dialog = BigChartDialog(render, title, self._dark, self)
    dialog.exec()
```

---

## Issue 6: Start application maximized

### Problem

The application starts at a fixed size. The user wants it maximized.

### Solution

Change `window.show()` to `window.showMaximized()` in `main.py`.

### Files

| File | Change |
|---|---|
| `app/main.py` | Line 251: `window.show()` → `window.showMaximized()` |

---

## Issue 7: Manual edit — disable Save when value out of range

### Problem

The `ManualEditDialog` uses `QDoubleSpinBox.setRange(lower, upper)` which clamps typed values, but the Save button is always enabled. The user wants the Save button disabled when the value is outside the allowed range, providing immediate visual feedback.

### Solution

Connect the spinbox's `valueChanged` signal to a validation method that enables/disables the OK button. Add a status label for feedback.

### Files

| File | Change |
|---|---|
| `app/presentation/manual_edit_dialog.py` | Store OK button reference. Connect `valueChanged` to `_validate`. Add `_validate()` and a status label. |

### Changes

In `__init__`, store `self._lower`, `self._upper` from `_allowed_range`. Store `self._ok_button = buttons.button(...)`. Add a `self._status_label = QLabel("")` before the buttons. Connect `self._spin.valueChanged.connect(self._validate)`. Call `self._validate()` once.

New method:
```python
def _validate(self) -> None:
    v = Decimal(str(self._spin.value()))
    in_range = Decimal(str(self._lower)) <= v <= Decimal(str(self._upper))
    self._ok_button.setEnabled(in_range)
    if not in_range:
        self._status_label.setText(
            self._tr.t("manual.ascending_error",
                       prev=self._tr.format_number(self._lower),
                       next=self._tr.format_number(self._upper))
        )
    else:
        self._status_label.setText("")
```

---

## Issue 8: Remove 'restore' column from table

### Problem

The table has a "Restore" column with a QPushButton per row. The restore action is also available via right-click context menu. The button column is redundant.

### Solution

Remove the "restore" column from `_COLUMNS`. Remove button creation from `MeterTableView`.

### Files

| File | Change |
|---|---|
| `app/presentation/table_model.py` | Remove `"restore"` from `_COLUMNS`. Remove `if col == "restore"` branch from `data()`. Remove `"table.restore"` from `headerData` mapping. |
| `app/presentation/meter_table.py` | Remove `_refresh_buttons` method. Remove `model.modelReset.connect(...)` and `self._refresh_buttons()` from `set_model`. Remove `QPushButton` from imports. |
| `tests/test_presentation/test_table_model.py` | Update `test_column_headers`: expect 7 columns, no "Restore". |

---

## Issue 9: Import/Interpolated/Modified always in m³

### Problem

The Import, Interpolated, and Modified columns convert to kWh when the view unit is kWh. These are absolute meter readings and should always show in m³. The header should indicate "(m³)".

### Solution

Simplify `_format()` to always format in m³. Update i18n headers.

### Files

| File | Change |
|---|---|
| `app/presentation/table_model.py` | Simplify `_format()`: remove kWh branch, always return `self._tr.format_number(value)`. |
| `app/presentation/i18n.py` | EN: `"table.import_value": "Import (m³)"`, `"table.interpolated_value": "Interpolated (m³)"`, `"table.modified_value": "Modified (m³)"`. DE: `"table.import_value": "Import (m³)"`, `"table.interpolated_value": "Interpoliert (m³)"`, `"table.modified_value": "Korrigiert (m³)"`. |
| `tests/test_presentation/test_table_model.py` | Update header assertions for "(m³)" suffix. |

---

## Updated Implementation Order

1. **Issue 4** (table headers auto-fit) — smallest, self-contained.
2. **Issue 8** (remove restore column) — small, table-only.
3. **Issue 9** (always m³ in table) — small, table + i18n.
4. **Issue 3** (legend colors) — small, touches only legend calls.
5. **Issue 2** (compare refresh) — one-line logic fix.
6. **Issue 7** (manual edit validation) — small, dialog-only.
7. **Issue 6** (start maximized) — one-line change.
8. **Issue 5** (compare double-click big dialog) — medium, compare tab.
9. **Issue 1** (archive duplicates) — largest change.

## Testing

- Run `python -m pytest tests/ -q` after each issue (baseline: 298 passed).
- Run `ruff check app/ tests/` after all changes.

