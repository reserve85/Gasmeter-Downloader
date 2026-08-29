"""Settings + gas-parameter use case tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.application.models import ParamsIntervalRequest
from app.application.use_cases.gas_parameters import GasParametersUseCase
from app.application.use_cases.settings import SettingsUseCase
from app.domain.entities import LogCategory

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


def test_settings_encrypts_token(fake_repo, gas_repo, logger, tmp_path):
    from app.infrastructure.config.security import TokenCrypto

    crypto = TokenCrypto(tmp_path / "key")
    settings = FakeSettings()
    use_case = SettingsUseCase(settings, logger, token_crypto=crypto)
    use_case.update({"update.token": "ghp_plaintext"})
    stored = settings.get("update.token")
    assert stored != "ghp_plaintext"  # encrypted at rest
    assert crypto.decrypt(stored) == "ghp_plaintext"


def test_gas_params_upsert_and_overlap_rejected(gas_repo, logger):
    use_case = GasParametersUseCase(gas_repo, logger)
    use_case.upsert(
        ParamsIntervalRequest(
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 6, 30),
            calorific_value=Decimal("11.5"),
            z_value=Decimal("0.95"),
        )
    )
    assert len(gas_repo.all_intervals()) == 1
    with pytest.raises(ValueError):
        use_case.upsert(
            ParamsIntervalRequest(
                valid_from=date(2026, 6, 30),  # inclusive overlap with 06-30
                valid_to=date(2026, 12, 31),
                calorific_value=Decimal("11.5"),
                z_value=Decimal("0.95"),
            )
        )
    use_case.delete(date(2026, 1, 1), date(2026, 6, 30))
    assert gas_repo.all_intervals() == []


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
