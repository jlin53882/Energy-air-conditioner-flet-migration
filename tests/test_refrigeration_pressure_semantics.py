"""冷凍現場判讀的錶壓力／絕對壓力語意：從 UI 輸入到 application request 的整條路徑。"""

from __future__ import annotations

import pytest

from application.refrigeration import RefrigerationService
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter
from Flet_ui.ui_components.analysis_modules.refrigeration_cycle_module import RefrigerationCycleModule
from Flet_ui.ui_components.unit.UnitConverter import (
    ABSOLUTE_TO_GAUGE_UNIT,
    GAUGE_PRESSURE,
    GAUGE_TO_ABSOLUTE_UNIT,
    UnitConverter,
)

PSI_PA = 6_894.757
ATM_PA = 101_325.0


class DummyPage:
    """提供模組建構所需的最小 page 介面。"""

    def __init__(self) -> None:
        """初始化 overlay。

回傳：
    無。"""
        self.overlay = []

    def update(self) -> None:
        """在沒有 Flet session 時接受更新呼叫。

回傳：
    無。"""


class RecordingRefrigerationService(RefrigerationService):
    """記錄模組實際送出的 SuperheatCheckRequest，再交給真正的服務計算。"""

    def __init__(self) -> None:
        """以真正的熱力狀態服務初始化。

回傳：
    無。"""
        super().__init__(ThermodynamicStateService(CanonicalUnitConverter()))
        self.requests = []

    def check_superheat(self, request):
        """記錄 request 後照常判讀。

參數：
    request: SuperheatCheckRequest。

回傳：
    SaturationCheckResult。"""
        self.requests.append(request)
        return super().check_superheat(request)


@pytest.fixture
def module_and_service():
    """建立使用記錄服務的冷凍循環模組。

回傳：
    (RefrigerationCycleModule, RecordingRefrigerationService)。"""
    service = RecordingRefrigerationService()
    module = RefrigerationCycleModule(UnitConverter(), DummyPage(), service)
    return module, service


def _set(module, key: str, value: str, unit: str | None = None) -> None:
    """設定輸入列的數值（與選用的單位，不經換算）。

參數：
    module: 冷凍循環模組。
    key: 輸入列識別鍵。
    value: 數值文字。
    unit: 選用的單位。

回傳：
    無。"""
    entry = module.all_entries[key]
    entry["val"].value = value
    if unit is not None:
        entry["unit"].value = unit
        module._last_units[key] = unit


def _switch_mode(module, mode: str) -> None:
    """以使用者操作的方式切換壓力類型。

參數：
    module: 冷凍循環模組。
    mode: "Gauge" 或 "Absolute"。

回傳：
    無。"""
    module.sh_pressure_type.selected = [mode]
    module.on_pressure_type_change(None)


def _select_unit(module, key: str, unit: str) -> None:
    """以使用者操作的方式切換輸入列單位（觸發單位換算處理器）。

參數：
    module: 冷凍循環模組。
    key: 輸入列識別鍵。
    unit: 新單位。

回傳：
    無。"""
    dropdown = module.all_entries[key]["unit"]
    dropdown.value = unit
    dropdown.on_select(type("Event", (), {"control": dropdown})())


def test_gauge_kpag_plus_atmosphere_reaches_application_as_absolute_pa(module_and_service) -> None:
    """900 kPag + 101.325 kPa 大氣壓力 → request 為 1001.325 kPa 絕對壓力。

回傳：
    無。"""
    module, service = module_and_service
    _set(module, "sh_p", "900", "kPag")
    _set(module, "sh_atm", "101.325", "kPa")

    module.calculate_superheat(False)

    assert service.requests[-1].pressure_pa == pytest.approx(1_001_325.0)


def test_gauge_psig_plus_atmosphere_reaches_application_as_absolute_pa(module_and_service) -> None:
    """100 psig + 1 atm → request 約為 114.6959 psia。

回傳：
    無。"""
    module, service = module_and_service
    _set(module, "sh_p", "100", "psig")
    _set(module, "sh_atm", "101.325", "kPa")

    module.calculate_superheat(False)

    assert service.requests[-1].pressure_pa / PSI_PA == pytest.approx(114.6959, abs=1e-4)


def test_gauge_mode_only_offers_gauge_units_and_absolute_mode_only_absolute(module_and_service) -> None:
    """錶壓力模式不會出現 psia 等絕對單位；絕對壓力模式不會出現錶壓單位。

回傳：
    無。"""
    module, _service = module_and_service
    entry = module.all_entries["sh_p"]

    gauge_units = [option.key for option in entry["unit"].options]
    assert entry["prop_code"] == GAUGE_PRESSURE
    assert set(gauge_units) == set(GAUGE_TO_ABSOLUTE_UNIT)
    assert "psia" not in gauge_units and entry["unit"].value == "kPag"

    _switch_mode(module, "Absolute")
    absolute_units = [option.key for option in entry["unit"].options]
    assert entry["prop_code"] == "P"
    assert "psia" in absolute_units
    assert not set(absolute_units) & set(GAUGE_TO_ABSOLUTE_UNIT)
    assert entry["unit"].value == "kPa"

    _switch_mode(module, "Gauge")
    assert entry["prop_code"] == GAUGE_PRESSURE
    assert entry["unit"].value == "kPag"


def test_absolute_mode_does_not_add_atmospheric_pressure(module_and_service) -> None:
    """絕對壓力模式使用 psia 時不再加大氣壓力，隱藏的大氣壓力欄位不影響結果。

回傳：
    無。"""
    module, service = module_and_service
    _switch_mode(module, "Absolute")
    _set(module, "sh_p", "130", "psia")
    _set(module, "sh_atm", "50", "kPa")

    module.calculate_superheat(False)

    assert module.all_entries["sh_atm"]["ui_row"].visible is False
    assert service.requests[-1].pressure_pa == pytest.approx(130 * PSI_PA)


def test_switching_gauge_units_converts_the_value(module_and_service) -> None:
    """kPag → psig 會換算數值，代表同一個錶壓力。

回傳：
    無。"""
    module, service = module_and_service
    _set(module, "sh_p", "900", "kPag")
    _set(module, "sh_atm", "101.325", "kPa")

    _select_unit(module, "sh_p", "psig")

    assert float(module.all_entries["sh_p"]["val"].value) == pytest.approx(900_000 / PSI_PA, rel=1e-6)
    module.calculate_superheat(False)
    assert service.requests[-1].pressure_pa == pytest.approx(1_001_325.0, rel=1e-6)


@pytest.mark.parametrize("gauge_unit", sorted(GAUGE_TO_ABSOLUTE_UNIT))
def test_switching_mode_preserves_the_physical_pressure(module_and_service, gauge_unit) -> None:
    """錶壓 ↔ 絕對壓力切換時換算數值，實際絕對壓力不變，單位維持同尺度。

參數：
    module_and_service: 模組與記錄服務。
    gauge_unit: 錶壓單位。

回傳：
    無。"""
    module, service = module_and_service
    converter = module.unit_converter
    gauge_value = converter.convert_from_si(GAUGE_PRESSURE, 900_000.0, gauge_unit)
    _set(module, "sh_p", f"{gauge_value:.9g}", gauge_unit)
    _set(module, "sh_atm", "101.325", "kPa")

    _switch_mode(module, "Absolute")
    entry = module.all_entries["sh_p"]
    assert entry["unit"].value == GAUGE_TO_ABSOLUTE_UNIT[gauge_unit]
    module.calculate_superheat(False)
    assert service.requests[-1].pressure_pa == pytest.approx(1_001_325.0, rel=1e-6)

    _switch_mode(module, "Gauge")
    assert entry["unit"].value == ABSOLUTE_TO_GAUGE_UNIT[GAUGE_TO_ABSOLUTE_UNIT[gauge_unit]]
    assert float(entry["val"].value) == pytest.approx(gauge_value, rel=1e-6)


def test_mode_switch_is_refused_when_atmospheric_pressure_is_invalid(module_and_service) -> None:
    """大氣壓力無效時無法換算，維持錶壓模式並提示，不會把錶壓數值當成絕對壓力。

回傳：
    無。"""
    module, _service = module_and_service
    _set(module, "sh_p", "900", "kPag")
    _set(module, "sh_atm", "abc", "kPa")

    _switch_mode(module, "Absolute")

    entry = module.all_entries["sh_p"]
    assert module.sh_pressure_type.selected == ["Gauge"]
    assert entry["prop_code"] == GAUGE_PRESSURE
    assert (entry["val"].value, entry["unit"].value) == ("900", "kPag")
    assert module.all_entries["sh_atm"]["val"].error_text


@pytest.mark.parametrize(
    ("gauge", "atmosphere", "message"),
    [("-200", "101.325", "絕對壓力必須大於 0"), ("100", "0", "大氣壓力必須")],
)
def test_non_positive_absolute_or_atmospheric_pressure_is_rejected(
    module_and_service, gauge, atmosphere, message
) -> None:
    """錶壓換算後的絕對壓力或大氣壓力不是正值時明確報錯，不送出 request。

參數：
    module_and_service: 模組與記錄服務。
    gauge: 錶壓力（kPag）。
    atmosphere: 大氣壓力（kPa）。
    message: 預期的錯誤訊息片段。

回傳：
    無。"""
    module, service = module_and_service
    _set(module, "sh_p", gauge, "kPag")
    _set(module, "sh_atm", atmosphere, "kPa")

    with pytest.raises(ValueError, match=message):
        module.calculate_superheat(False)
    assert service.requests == []


def test_gauge_pressure_never_reaches_the_domain_layer() -> None:
    """錶壓力是通道層概念：domain／application 程式碼不得出現錶壓單位或 PGauge。

回傳：
    無。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    gauge_tokens = (GAUGE_PRESSURE, *GAUGE_TO_ABSOLUTE_UNIT)
    for package in ("domain", "application"):
        for path in (root / package).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert not any(f'"{token}"' in source for token in gauge_tokens), path
