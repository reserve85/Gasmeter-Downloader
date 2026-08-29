"""i18n tests: key parity between en and de, number/date formatting."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.presentation.i18n import Translator


def test_all_english_keys_present_in_german():
    from app.presentation.i18n import _CATALOGS

    assert set(_CATALOGS["de"].keys()) == set(_CATALOGS["en"].keys())


def test_format_number_de():
    de = Translator("de")
    assert de.format_number(Decimal("3116.4"), decimals=1) == "3.116,4"


def test_format_number_en():
    en = Translator("en")
    assert en.format_number(Decimal("3116.4"), decimals=1) == "3,116.4"


def test_format_number_none_uses_dash():
    tr = Translator("en")
    assert tr.format_number(None) == "–"


def test_format_date():
    en = Translator("en")
    de = Translator("de")
    assert en.format_date(date(2026, 8, 29)) == "2026-08-29"
    assert de.format_date(date(2026, 8, 29)) == "29.08.2026"


def test_translation_with_kwargs():
    tr = Translator("en")
    assert "42" in tr.t("status.synced", downloaded=42, missing=0, failed=0)
