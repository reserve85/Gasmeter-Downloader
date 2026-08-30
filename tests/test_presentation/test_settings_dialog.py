"""Settings dialog tests: interval add/delete persistence semantics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PyQt6.QtWidgets import QGroupBox, QLineEdit, QPushButton

from app.presentation.i18n import Translator
from app.presentation.settings_dialog import SettingsDialog

_TR = Translator("en")


def _make_intervals():
    from app.domain.entities import GasParameterInterval

    return [
        GasParameterInterval(
            valid_from=date.fromisoformat("2026-01-01"),
            valid_to=date.fromisoformat("2026-06-30"),
            calorific_value=Decimal("11.5"),
            z_value=Decimal("0.95"),
        ),
        GasParameterInterval(
            valid_from=date.fromisoformat("2026-07-01"),
            valid_to=None,
            calorific_value=Decimal("11.342"),
            z_value=Decimal("0.9589"),
        ),
    ]


def test_collect_no_changes(qapp):
    settings = {
        "device.ip": "192.168.10.65",
        "device.max_download_days": 30,
        "app.language": "en",
        "app.unit": "m³",
        "paths.download": "downloads",
        "paths.archive": "archive",
        "paths.database": "gasmeter.db",
        "gas.default_calorific": 11.342,
        "gas.default_z_value": 0.9589,
    }
    dialog = SettingsDialog(_TR, settings, _make_intervals())
    changes, upserts, deletes = dialog.collect()
    assert changes["device.ip"] == "192.168.10.65"
    assert len(upserts) == 2
    assert deletes == []


def test_delete_interval_is_returned_as_delete(qapp):
    settings = {"device.ip": "192.168.10.65", "device.max_download_days": 30}
    dialog = SettingsDialog(_TR, settings, _make_intervals())
    dialog._gas_table.setCurrentCell(0, 0)  # noqa: SLF001
    dialog._delete_interval()  # noqa: SLF001
    changes, upserts, deletes = dialog.collect()
    assert deletes == [(date(2026, 1, 1), date(2026, 6, 30))]
    assert len(upserts) == 1
    assert upserts[0][0] == date(2026, 7, 1)


def test_add_interval_shows_in_upserts(qapp):
    settings = {"device.ip": "192.168.10.65", "device.max_download_days": 30}
    dialog = SettingsDialog(_TR, settings, _make_intervals())
    dialog._from_edit.setDate(__import__("PyQt6.QtCore", fromlist=["QDate"]).QDate(2026, 9, 1))
    dialog._to_open.setChecked(True)  # noqa: SLF001
    dialog._cal_spin.setValue(11.9)
    dialog._add_interval()  # noqa: SLF001
    changes, upserts, deletes = dialog.collect()
    assert len(upserts) == 3
    assert upserts[-1][0] == date(2026, 9, 1)
    assert upserts[-1][1] is None
    assert upserts[-1][2] == Decimal("11.9")
    # the previously open-ended interval is closed the day before (seamless)
    closed = [u for u in upserts if u[0] == date(2026, 7, 1)]
    assert closed and closed[0][1] == date(2026, 8, 31)
    # ... and the original open row is reported for deletion
    assert deletes == [(date(2026, 7, 1), None)]


def test_token_field_is_plain_edit_without_browse(qapp):
    """The GitHub token is a string, not a path - it must not get a Browse… button."""
    dialog = SettingsDialog(_TR, {"device.ip": "192.168.10.65"}, _make_intervals())
    # only the three storage paths may offer Browse…
    browse = [b for b in dialog.findChildren(QPushButton) if "Browse" in b.text()]
    assert len(browse) == 3
    # the token is a plain (password-masked) line edit
    assert isinstance(dialog._token_edit, QLineEdit)  # noqa: SLF001
    assert dialog._token_edit.echoMode() == QLineEdit.EchoMode.Password  # noqa: SLF001
    assert dialog._token_edit.parent() is dialog  # added directly, not via _path_row


def test_auto_fetch_checkbox_in_collect(qapp):
    dialog = SettingsDialog(
        _TR,
        {"device.ip": "192.168.10.65", "device.max_download_days": 30, "device.auto_fetch_on_startup": True},
        _make_intervals(),
    )
    assert dialog._auto_fetch.isChecked() is True  # noqa: SLF001
    dialog._auto_fetch.setChecked(False)  # noqa: SLF001
    changes, _upserts, _deletes = dialog.collect()
    assert changes["device.auto_fetch_on_startup"] is False


def test_theme_combo_in_collect(qapp):
    from app.presentation.settings_dialog import SettingsDialog

    dialog = SettingsDialog(
        _TR,
        {"device.ip": "192.168.10.65"},
        _make_intervals(),
        theme_mode="light",
    )
    assert dialog._theme.currentData() == "light"  # noqa: SLF001
    dialog._theme.setCurrentIndex(dialog._theme.findData("dark"))  # noqa: SLF001
    changes, _upserts, _deletes = dialog.collect()
    assert changes["theme.mode"] == "dark"


def test_actions_buttons_only_with_callbacks(qapp):
    calls = []
    dialog = SettingsDialog(
        _TR,
        {"device.ip": "192.168.10.65"},
        _make_intervals(),
        on_import_archive=lambda: calls.append("import"),
        on_check_updates=lambda: calls.append("update"),
    )
    layout = dialog.layout()
    texts = []
    for i in range(layout.count()):
        widget = layout.itemAt(i).widget()
        if widget is not None:
            title = widget.title() if hasattr(widget, "title") else ""
            text = widget.text() if hasattr(widget, "text") else ""
            texts.append(title or text)
    assert "Actions" in texts

    no_cb = SettingsDialog(_TR, {"device.ip": "192.168.10.65"}, _make_intervals())
    group_titles = []
    for i in range(no_cb.layout().count()):
        widget = no_cb.layout().itemAt(i).widget()
        if isinstance(widget, QGroupBox):
            group_titles.append(widget.title())
    assert "Actions" not in group_titles


def test_add_interval_prefills_day_after_last(qapp):
    from app.domain.entities import GasParameterInterval

    intervals = [
        GasParameterInterval(
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 6, 30),
            calorific_value=Decimal("11.5"),
            z_value=Decimal("0.95"),
        ),
        GasParameterInterval(
            valid_from=date(2026, 7, 1),
            valid_to=date(2026, 8, 31),
            calorific_value=Decimal("11.342"),
            z_value=Decimal("0.9589"),
        ),
    ]
    dialog = SettingsDialog(_TR, {"device.ip": "192.168.10.65"}, intervals)

    prefill = dialog._from_edit.date()  # noqa: SLF001
    assert (prefill.year(), prefill.month(), prefill.day()) == (2026, 9, 1)


def test_edit_interval_changes_value_in_place(qapp):
    """Owner: 'den Wert ändern geht nicht' - editing must replace the row."""
    dialog = SettingsDialog(_TR, {"device.ip": "192.168.10.65"}, _make_intervals())
    # select the open-ended interval (row 1) and edit its values
    dialog._gas_table.setCurrentCell(1, 0)  # noqa: SLF001
    dialog._on_edit_interval()  # noqa: SLF001
    assert dialog._cal_spin.value() == 11.342  # noqa: SLF001 - pre-filled
    assert dialog._to_open.isChecked() is True  # noqa: SLF001 - open-ended stays
    dialog._cal_spin.setValue(10.5)  # noqa: SLF001
    dialog._z_spin.setValue(0.99)  # noqa: SLF001
    dialog._add_interval()  # noqa: SLF001 - saves the edit
    changes, upserts, deletes = dialog.collect()
    # still exactly the two rows - the edited one was replaced, nothing deleted
    assert len(upserts) == 2
    assert deletes == []
    edited = [u for u in upserts if u[0] == date(2026, 7, 1)]
    assert len(edited) == 1
    assert edited[0][1] is None
    assert edited[0][2] == Decimal("10.5")
    assert edited[0][3] == Decimal("0.99")


def test_select_row_then_change_value_persists_on_ok(qapp):
    """Owner: 'Brennwert/Z landet nie' - selecting a row + editing + OK must persist."""
    dialog = SettingsDialog(_TR, {"device.ip": "192.168.10.65"}, _make_intervals())
    # selecting a row auto-loads it into the form (currentCellChanged)
    dialog._gas_table.setCurrentCell(0, 0)  # noqa: SLF001
    assert dialog._cal_spin.value() == 11.5  # noqa: SLF001 - auto-loaded from row 0
    dialog._cal_spin.setValue(9.9)  # noqa: SLF001 - user changes Brennwert
    dialog._z_spin.setValue(1.05)  # noqa: SLF001
    # NO extra add/edit click - the commit must happen in collect (the OK path)
    changes, upserts, deletes = dialog.collect()
    edited = [u for u in upserts if u[0] == date(2026, 1, 1)]
    assert len(edited) == 1
    assert edited[0][2] == Decimal("9.9")
    assert edited[0][3] == Decimal("1.05")
