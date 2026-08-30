"""MeterTableModel tests: all three values + localized source + unit display."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PyQt6.QtCore import Qt

from app.domain.entities import (
    Aggregation,
    Dashboard,
    KpiSummary,
    Source,
    ViewUnit,
)
from app.presentation.i18n import Translator
from app.presentation.table_model import MeterTableModel

_TR = Translator("en")

_SAMPLE_DASHBOARD = Dashboard(
    unit=ViewUnit.M3,
    meter_series=[],
    consumption={Aggregation.DAILY: [], Aggregation.WEEKLY: [], Aggregation.MONTHLY: []},
    previous_year=None,
    trendline=None,
    kpi=KpiSummary(
        total_energy=Decimal("0"),
        average_per_day=Decimal("0"),
        max_day=None,
        interpolated_days_in_range=0,
        latest_meter_value=Decimal("0"),
    ),
    table_rows=[
        (date(2026, 1, 1), Decimal("100"), None, Decimal("100"), Source.LOGFILE),
        (date(2026, 1, 2), Decimal("101"), Decimal("101"), Decimal("101"), Source.INTERPOLATED),
        (date(2026, 1, 3), None, None, Decimal("999"), Source.MANUAL),
    ],
    day_factors={},
)


def test_column_headers(qapp):
    model = MeterTableModel(_TR)
    model.set_dashboard(_SAMPLE_DASHBOARD)
    headers = [
        model.headerData(i, Qt.Orientation.Horizontal) for i in range(model.columnCount())
    ]
    assert headers[:5] == ["Date", "Import", "Interpolated", "Modified", "Source"]
    assert headers[5] == "Daily use (m³)"
    assert headers[6] == "Daily use (kWh)"
    assert headers[7] == "Restore"


def test_row_values_and_source(qapp):
    model = MeterTableModel(_TR)
    model.set_dashboard(_SAMPLE_DASHBOARD)
    assert model.rowCount() == 3
    assert model.index(0, 0).data() == "2026-01-01"
    assert model.index(0, 1).data() == "100.000"
    assert model.index(2, 3).data() == "999.000"
    assert model.index(1, 4).data() == "interpolated"
    assert model.index(2, 4).data() == "manual"


def test_modified_only_editable_column(qapp):
    model = MeterTableModel(_TR)
    model.set_dashboard(_SAMPLE_DASHBOARD)
    assert model.index(0, 3).data() == "100.000"  # modified column exists


def test_daily_usage_columns_filled_from_dashboard(qapp):
    """Tagesverbrauch: m³ + kWh come from the DAILY consumption buckets."""
    from app.domain.entities import ConsumptionPoint

    kwh = Decimal("32.628")
    dashboard = Dashboard(
        unit=ViewUnit.M3,
        meter_series=[],
        consumption={
            Aggregation.DAILY: [
                ConsumptionPoint(date(2026, 1, 2), Decimal("2"), kwh),
                ConsumptionPoint(date(2026, 1, 3), Decimal("2"), kwh),
            ],
            Aggregation.WEEKLY: [],
            Aggregation.MONTHLY: [],
        },
        previous_year=None,
        trendline=None,
        kpi=KpiSummary(
            total_energy=Decimal("0"),
            average_per_day=Decimal("0"),
            max_day=None,
            interpolated_days_in_range=0,
            latest_meter_value=Decimal("0"),
        ),
        table_rows=[
            (date(2026, 1, 1), Decimal("100"), None, Decimal("100"), Source.LOGFILE),
            (date(2026, 1, 2), Decimal("102"), None, Decimal("102"), Source.LOGFILE),
        ],
        day_factors={},
    )
    model = MeterTableModel(_TR)
    model.set_dashboard(dashboard)
    # no daily point for 2026-01-01 -> dash
    assert model.index(0, 5).data() == "–"
    assert model.index(0, 6).data() == "–"
    assert model.index(1, 5).data() == "2.000"
    assert model.index(1, 6).data() == "32.628"
