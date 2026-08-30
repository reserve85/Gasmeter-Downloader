"""Settings + gas-parameter use case tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.application.models import ParamsIntervalRequest
from app.application.use_cases.gas_parameters import GasParametersUseCase
from app.application.use_cases.settings import SettingsUseCase
from app.domain.entities import LogCategory
from app.infrastructure.config.security import TokenCrypto

from tests.conftest import FakeSettings


def test_settings_get_and_update(fake_repo, gas_repo, logger):
    settings = FakeSettings()
    use_case = SettingsUseCase(settings, logger)

    changes = {"device.ip": "192.168.10.66", "device.max_download_days": 45}
    updated = use_case.update(changes)

    assert updated["device.ip"] == "192.168.10.66"
    assert updated["device.max_download_days"] == 45
    assert logger.messages_of(LogCategory.SETTINGS)


def test_settings_rejects_invalid(fake_repo, gas_repo, logger):
    use_case = SettingsUseCase(FakeSettings(), logger)
    with pytest.raises(ValueError):
        use_case.update({"device.ip": "not-an-ip"})


def test_settings_coerces_bool_and_theme_mode(fake_repo, gas_repo, logger):
    settings = FakeSettings()
    use_case = SettingsUseCase(settings, logger)
    use_case.update({"device.auto_fetch_on_startup": "true", "theme.mode": "dark"})
    assert settings.get("device.auto_fetch_on_startup") is True
    assert settings.get("theme.mode") == "dark"
    with pytest.raises(ValueError):
        use_case.update({"theme.mode": "sepia"})


def test_settings_encrypts_token(fake_repo, gas_repo, logger):
    """A saved GitHub token must never be stored in clear text."""
    crypto = TokenCrypto()
    settings = FakeSettings()
    use_case = SettingsUseCase(settings, logger, token_crypto=crypto)
    use_case.update({"update.token": "ghp_plaintext"})
    stored = settings.get("update.token")
    assert stored != "ghp_plaintext"  # encrypted at rest
    assert TokenCrypto.is_encrypted(stored)
    assert crypto.decrypt(stored) == "ghp_plaintext"


def test_settings_encrypts_token_even_without_crypto(fake_repo, gas_repo, logger):
    """Encryption is mandatory - omitting the crypto must not fall back to clear text."""
    settings = FakeSettings()
    use_case = SettingsUseCase(settings, logger)  # no token_crypto passed
    use_case.update({"update.token": "ghp_x"})
    stored = settings.get("update.token")
    assert TokenCrypto.is_encrypted(stored)
    assert stored != "ghp_x"
    # and the dialog round-trip shows the decrypted value again
    assert use_case.get_all()["update.token"] == "ghp_x"


def test_migrate_legacy_plaintext_token(fake_repo, gas_repo, logger):
    """A clear-text token from an old build is encrypted at startup."""
    from app.main import _migrate_legacy_token

    settings = FakeSettings({"update.token": "ghp_plain"})
    crypto = TokenCrypto()
    _migrate_legacy_token(settings, crypto, logger)
    stored = settings.get("update.token")
    assert TokenCrypto.is_encrypted(stored)
    assert crypto.decrypt(stored) == "ghp_plain"


def test_migrate_legacy_keyfile_ciphertext_and_file_removed(tmp_path, fake_repo, gas_repo, logger):
    """Legacy key-file ciphertext is re-keyed and the obsolete file is deleted."""
    from cryptography.fernet import Fernet

    from app.main import _migrate_legacy_token

    key_file = tmp_path / ".gasmeter_token_key"
    key_file.write_bytes(Fernet.generate_key())
    old = Fernet(key_file.read_bytes()).encrypt(b"legacy_token").decode("ascii")

    settings = FakeSettings({"update.token": old})
    crypto = TokenCrypto(key_file)
    _migrate_legacy_token(settings, crypto, logger)

    assert not key_file.exists()  # obsolete key file removed
    stored = settings.get("update.token")
    assert crypto.decrypt(stored) == "legacy_token"  # still readable


def test_gas_params_auto_closes_predecessor(gas_repo, logger):
    use_case = GasParametersUseCase(gas_repo, logger)
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 6, 30),
            calorific_value=Decimal("11.5"),
            z_value=Decimal("0.95"),
        )
    )
    # starting exactly on the boundary is seamlessly accepted:
    # the predecessor is closed the day before, no gap, no overlap.
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2026, 6, 30),
            valid_to=date(2026, 12, 31),
            calorific_value=Decimal("11.3"),
            z_value=Decimal("0.96"),
        )
    )
    intervals = gas_repo.all_intervals()
    assert len(intervals) == 2
    assert intervals[0].valid_to == date(2026, 6, 29)
    assert intervals[1].valid_from == date(2026, 6, 30)
    assert logger.messages_of(LogCategory.GAS_PARAMS)


def test_gas_params_auto_closes_open_ended_predecessor(gas_repo, logger):
    use_case = GasParametersUseCase(gas_repo, logger)
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2020, 1, 1),
            valid_to=None,
            calorific_value=Decimal("11.342"),
            z_value=Decimal("0.9589"),
        )
    )
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2026, 7, 1),
            valid_to=None,
            calorific_value=Decimal("11.1"),
            z_value=Decimal("0.99"),
        )
    )
    intervals = gas_repo.all_intervals()
    assert len(intervals) == 2
    assert intervals[0].valid_to == date(2026, 6, 30)
    assert intervals[1].valid_to is None


def test_gas_params_rejects_overlap_starting_after_new_from(gas_repo, logger):
    use_case = GasParametersUseCase(gas_repo, logger)
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2026, 7, 1),
            valid_to=date(2026, 12, 31),
            calorific_value=Decimal("11.5"),
            z_value=Decimal("0.95"),
        )
    )
    # an interval starting at/after new_from cannot be auto-closed -> rejected
    with pytest.raises(ValueError):
        use_case.upsert(
            ParamsIntervalRequest(
                valid_from=date(2026, 6, 15),
                valid_to=date(2026, 7, 15),
                calorific_value=Decimal("11.3"),
                z_value=Decimal("0.96"),
            )
        )
    assert len(gas_repo.all_intervals()) == 1


def test_gas_params_inside_insert_warns_about_uncovered_tail(gas_repo, logger):
    use_case = GasParametersUseCase(gas_repo, logger)
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 12, 31),
            calorific_value=Decimal("11.5"),
            z_value=Decimal("0.95"),
        )
    )
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2026, 2, 1),
            valid_to=date(2026, 2, 28),
            calorific_value=Decimal("11.3"),
            z_value=Decimal("0.96"),
        )
    )
    intervals = gas_repo.all_intervals()
    assert [i.valid_to for i in intervals] == [date(2026, 1, 31), date(2026, 2, 28)]
    assert any("uncovered" in message for message in logger.messages_of(LogCategory.GAS_PARAMS))


def test_seed_gas_parameters_starts_at_first_logfile(gas_repo, fake_repo):
    """Owner: the parameter interval must start at the FIRST stored logfile."""
    from app.main import seed_gas_parameters

    fake_repo.save_import(date(2020, 3, 1), Decimal("100"))
    fake_repo.save_import(date(2020, 3, 2), Decimal("102"))
    fake_repo.save_import(date(2026, 8, 28), Decimal("31163"))
    seed_gas_parameters(gas_repo, FakeSettings(), fake_repo)
    intervals = gas_repo.all_intervals()
    assert len(intervals) == 1
    assert intervals[0].valid_from == date(2020, 3, 1)
    assert intervals[0].valid_to is None


def test_seed_gas_parameters_repairs_leading_gap(gas_repo, fake_repo):
    """Existing interval starting later -> coverage is extended back to the 1st logfile."""
    from app.domain.entities import GasParameterInterval
    from app.main import seed_gas_parameters

    gas_repo.upsert_interval(
        GasParameterInterval(date(2026, 8, 28), None, Decimal("11.342"), Decimal("0.9589"))
    )
    fake_repo.save_import(date(2026, 1, 5), Decimal("100"))
    fake_repo.save_import(date(2026, 8, 28), Decimal("31163"))
    seed_gas_parameters(gas_repo, FakeSettings(), fake_repo)
    intervals = sorted(gas_repo.all_intervals(), key=lambda i: i.valid_from)
    assert [i.valid_from for i in intervals] == [date(2026, 1, 5), date(2026, 8, 28)]
    # the leading repair ends the day before the next interval (seamless)
    assert intervals[0].valid_to == date(2026, 8, 27)
    assert intervals[0].calorific_value == Decimal("11.342")


def test_seed_gas_parameters_reopens_tail_covered_by_newer_readings(gas_repo, fake_repo):
    """Bounded last interval with readings after its end -> reopened (bis heute)."""
    from app.domain.entities import GasParameterInterval
    from app.main import seed_gas_parameters

    gas_repo.upsert_interval(
        GasParameterInterval(date(2026, 1, 1), date(2026, 3, 31), Decimal("11.5"), Decimal("0.95"))
    )
    fake_repo.save_import(date(2026, 1, 1), Decimal("100"))
    fake_repo.save_import(date(2026, 5, 1), Decimal("400"))
    seed_gas_parameters(gas_repo, FakeSettings(), fake_repo)
    intervals = gas_repo.all_intervals()
    assert len(intervals) == 1
    assert intervals[0].valid_from == date(2026, 1, 1)
    assert intervals[0].valid_to is None  # reopened to cover the newer reading


def test_gas_params_logs_changes(gas_repo, logger):
    use_case = GasParametersUseCase(gas_repo, logger)
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2026, 1, 1),
            valid_to=None,
            calorific_value=Decimal("11.342"),
            z_value=Decimal("0.9589"),
        )
    )
    assert logger.messages_of(LogCategory.GAS_PARAMS)


def test_gas_params_same_valid_from_replaces(gas_repo, logger):
    """Upserting an interval that starts on the same day replaces the old one.

    The settings dialog re-emits every row, including the auto-closed
    predecessor of a new interval; that must not raise an "overlap" error.
    """
    use_case = GasParametersUseCase(gas_repo, logger)
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2026, 1, 1),
            valid_to=None,
            calorific_value=Decimal("11.342"),
            z_value=Decimal("0.9589"),
        )
    )
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 6, 30),
            calorific_value=Decimal("11.5"),
            z_value=Decimal("0.95"),
        )
    )
    intervals = gas_repo.all_intervals()
    assert len(intervals) == 1
    assert intervals[0].valid_to == date(2026, 6, 30)
    assert intervals[0].calorific_value == Decimal("11.5")


def test_gas_params_dialog_reemits_closed_predecessor_then_new(gas_repo, logger):
    """The dialog flow that caused 'overlap existing interval'.

    Adding a new interval inside an open-ended one produces two rows to upsert:
    the closed predecessor (same valid_from as the DB row) and the new interval.
    """
    use_case = GasParametersUseCase(gas_repo, logger)
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2020, 1, 1),
            valid_to=None,
            calorific_value=Decimal("11.342"),
            z_value=Decimal("0.9589"),
        )
    )
    # rows as the dialog emits them after auto-closing the predecessor:
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2020, 1, 1),
            valid_to=date(2026, 6, 30),
            calorific_value=Decimal("11.342"),
            z_value=Decimal("0.9589"),
        )
    )
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2026, 7, 1),
            valid_to=None,
            calorific_value=Decimal("11.1"),
            z_value=Decimal("0.99"),
        )
    )
    intervals = gas_repo.all_intervals()
    assert len(intervals) == 2
    by_from = {i.valid_from: i for i in intervals}
    assert by_from[date(2020, 1, 1)].valid_to == date(2026, 6, 30)
    assert by_from[date(2026, 7, 1)].valid_to is None
