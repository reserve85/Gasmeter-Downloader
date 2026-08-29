"""Settings dialog tests: interval add/delete persistence semantics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

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
    assert deletes == []
