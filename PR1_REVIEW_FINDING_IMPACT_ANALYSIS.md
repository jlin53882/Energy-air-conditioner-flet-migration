# Energy Air Conditioner Flet Migration
# PR #1 Review Finding Pre-Fix Impact Analysis

> Repository: `jlin53882/Energy-air-conditioner-flet-migration`
>
> PR: [#1 — refactor: establish tkinter-free Flet migration](https://github.com/jlin53882/Energy-air-conditioner-flet-migration/pull/1)
>
> Review baseline HEAD: `62a0da95884ff541002d222305b1528c96a21a38`
>
> 本文件是修復 F1～F7 review findings 前的 impact analysis。這一輪只完成盤點與確認，尚未修改 production code、測試、文件或 commit。

---

## 1. Analysis Scope

本輪檢查的目標：

- ReferenceStateService
- ThermodynamicStateService
- `coolprop_utils`
- ThermoStateCalculator
- PropertyQueryService
- PropertyTab
- PsychrometricService
- CanonicalUnitConverter
- Flet UnitConverter
- Telegram ThermoCalculator
- AnalysisTab
- analysis definitions
- architecture guardrail tests
- `pyproject.toml`

明確不擴張至：

- 尚未遷移的其他 Compressor analyses
- Telegram 全量 constructor DI
- 完整 chart renderer / sampling decomposition
- packaging target 全面重寫
- Telegram specific-volume `V` contract migration

---

## 2. Repository / PR Identity Verification

實測確認：

```text
Repository: C:/Users/admin/workspace/Energy_air-conditioner_flet-migration
Branch: chore/update-flet-and-dependencies
PR: #1
Base: master
Base SHA: b97062315efdf3b228dd588d7b39bc32a58d4186
PR HEAD: 62a0da95884ff541002d222305b1528c96a21a38
Working tree: clean
```

GitNexus CLI 已重新索引至目前 HEAD；但目前長駐 MCP GitNexus 回報 `commitsBehind: 14`，因此 MCP graph 結果沒有被單獨當作證據，並以 repository source search 與逐檔讀取補足。

---

# 3. Answers to Required Questions

## 3.1 誰會 mutate CoolProp reference state？

### Shared mechanism

```text
domain/thermodynamics/reference_state.py:37-44
ReferenceStateService.set()
    → CP.set_reference_state(...)
```

上層呼叫路徑：

```text
domain/thermodynamics/state_service.py:42-44
ThermodynamicStateService.set_reference_state()

application/property_queries.py:26-28
PropertyQueryService.set_reference_state()

Flet_ui/ui_components/unit/ThermoStateCalculator.py:62-65
ThermoStateCalculator.set_coolprop_ref_state()
```

### Legacy chart direct mutation

`Flet_ui/ui_components/unit/thermo_draw/coolprop_utils.py` 仍直接呼叫：

```text
safe_props()                         line 65 / 67
get_saturation_curve()               line 91 / 93
generate_thermo_diagram()            line 165 / 167
```

這些路徑繞過 `ReferenceStateService`。

### Legacy HVAC direct mutation

以下函式也直接呼叫 `CP.set_reference_state()`：

```text
Flet_ui/ui_components/unit/hvac_calculations/compressor.py:237
Flet_ui/ui_components/unit/hvac_calculations/condenser_heat.py:218, 221
```

因此目前不只有 chart boundary 違反 contract，legacy HVAC calculation path 也有相同問題。

---

## 3.2 誰會在 reference-state mutation 後呼叫 PropsSI / PhaseSI？

### ThermodynamicStateService

```text
domain/thermodynamics/state_service.py:92-110
```

`_calculate_coolprop()` 會執行多次：

```python
CP.PropsSI(...)
CP.PhaseSI(...)
```

目前流程是：

```text
ReferenceStateService.set()
    lock mutation
    unlock

ThermodynamicStateService._calculate_coolprop()
    multiple PropsSI
    PhaseSI
```

所以 mutation 與完整 query transaction 沒有被同一個 synchronization boundary 保護。

### coolprop_utils

#### `safe_props()`

```text
coolprop_utils.py:54-77
```

可能先 mutation，接著執行：

```python
CP.PropsSI(...)
```

#### `get_saturation_curve()`

```text
coolprop_utils.py:82-142
```

可能先 mutation，接著執行：

```python
CP.PropsSI("Tcrit", fluid)
CP.PropsSI("Ttriple", fluid)
CP.PropsSI("pcrit", fluid)
CP.PropsSI("ptriple", fluid)
CP.PropsSI("P", "T", T, "Q", 0, fluid)
CP.PropsSI("P", "T", T, "Q", 1, fluid)
CP.PropsSI("T", "P", P, "Q", 0, fluid)
CP.PropsSI("T", "P", P, "Q", 1, fluid)
```

#### `generate_thermo_diagram()`

```text
coolprop_utils.py:150+
```

會先進行 reference-state mutation，再執行：

- 臨界點與三相點 PropsSI query
- `get_saturation_curve()`
- 多次 `safe_props()`
- 圖表 sampling query

### Legacy HVAC functions

以下函式會在 mutation 後連續執行多個 PropsSI：

```text
Flet_ui/ui_components/unit/hvac_calculations/compressor.py
Flet_ui/ui_components/unit/hvac_calculations/condenser_heat.py
```

這些路徑目前沒有使用 `ReferenceStateService`。

### Telegram thermodynamic path

```text
Telegram_bot/thermo_calculator.py:357-366
```

會執行：

```python
CP.PropsSI(...)
CP.PhaseSI(...)
```

Telegram 有自己的 `ThermodynamicStateService`，但尚未使用 process-level shared synchronization。

---

## 3.3 是否存在多個 ReferenceStateService / lock instance？

是。

### Flet production instance

```text
Flet_ui/ui_components/unit/ThermoStateCalculator.py:40
self._service = ThermodynamicStateService(unit_converter)
```

`ThermodynamicStateService` 預設會建立：

```text
ReferenceStateService
└─ RLock A
```

### Telegram production instance

```text
Telegram_bot/thermo_calculator.py:23
self._shared_state_service = ThermodynamicStateService(...)
```

因此 Telegram 另有：

```text
ReferenceStateService
└─ RLock B
```

### Flet PropertyQueryService

```text
Flet_ui/flet_app.py:27-29
```

PropertyQueryService 使用 `state_calculator.state_service`，因此 Flet PropertyTab 主路徑與 Flet ThermoStateCalculator 共用同一個 instance。

### Current conclusion

```text
Flet ThermodynamicStateService
    └─ ReferenceStateService / lock A

Telegram ThermodynamicStateService
    └─ ReferenceStateService / lock B

coolprop_utils
    └─ no shared lock

legacy HVAC calculations
    └─ no shared lock
```

目前沒有 process-level single synchronization mechanism。

---

## 3.4 domain/ currently imports 哪些 Flet_ui / Telegram_bot modules？

目前只有：

```text
domain/psychrometrics/service.py:7
from Flet_ui.PsychrometricChart import \
    PsychrometricChart_01_ASHF_model as legacy_model
```

目前沒有發現：

```text
domain/ → Telegram_bot
```

但這仍然違反 PR 自己宣告的 dependency direction：

```text
adapters
    ↓
application
    ↓
domain
```

目前實際依賴是：

```text
domain/psychrometrics/service.py
    → Flet_ui.PsychrometricChart
```

該 model 仍是明確排除的 legacy model，內部公式不應修改；本輪應只修正其 adapter 所在的 layer boundary。

---

## 3.5 哪些 conversion API 仍然會 silent fallback？

## Flet UnitConverter

```text
Flet_ui/ui_components/unit/UnitConverter.py:278-302
```

目前 canonical conversion path 會先呼叫：

```python
self._canonical_converter.convert_to_si(...)
```

但遇到 `ValueError` 後：

```python
except ValueError:
    pass
```

接著嘗試 legacy map，最後找不到時：

```python
return value
```

`convert_from_si()` 有相同問題，最後會：

```python
return value_si
```

對已納入 canonical core 的 quantity：

```text
P
T
H
S
D
U
```

unknown unit 可能被當成「已經是 SI」而繼續計算。

現有測試也仍固定這個舊行為：

```text
tests/test_calculation_and_analysis_coverage.py:68
assert converter.convert_to_si("P", 1.0, "not-a-unit") == 1.0
```

## Telegram ThermoCalculator

```text
Telegram_bot/thermo_calculator.py:192-255
```

`_convert_to_si()` 與 `_convert_from_si()` 對 canonical core 也會：

```python
try:
    canonical_converter.convert_...(…)
except ValueError:
    pass
```

找不到 legacy conversion 時分別回傳：

```python
return value
return value_si
```

## Intentional V boundary

Telegram `V` 目前保留 legacy specific-volume semantics：

```text
Telegram_bot/thermo_calculator.py:208-226
```

這是 Phase 0.5 已記錄的 intentional divergence，本輪不能偷偷統一或改變其 physics behavior。

---

## 3.6 analysis_id 目前由誰產生？

目前由 `AnalysisTab` 動態產生：

```text
Flet_ui/ui_components/analysis_tab.py:48-56
```

目前邏輯：

```python
for module in self.modules_to_load:
    definitions = module.get_analysis_definitions()

    for index, (name, raw_definition) in enumerate(definitions.items()):
        definition["analysis_id"] = (
            f"{module.__class__.__name__}.{index}"
        )
```

因此 ID 依賴：

- module class name
- definition ordering
- positional index

例如：

```text
CompressorModule.0
CompressorModule.1
```

目前各 analysis definition 沒有自己宣告 semantic stable ID。

---

## 3.7 PropertyTab 還有哪些 calculation / reference-state path 沒走 PropertyQueryService？

主要 property calculation 已經走：

```text
PropertyTab.perform_calculation()
    → PropertyQueryService.query()
    → ThermodynamicStateService
```

位置：

```text
Flet_ui/ui_components/property_tab.py:539-544
```

但仍有兩條 direct path。

### A. Constructor initialization

```text
Flet_ui/ui_components/property_tab.py:202-217
```

目前直接呼叫：

```python
state_calculator.set_coolprop_ref_state(
    default_fluid,
    default_ref_state,
)
```

應改成：

```python
self.query_service.set_reference_state(
    default_fluid,
    default_ref_state,
)
```

### B. perform_calculation() fluid validation

```text
Flet_ui/ui_components/property_tab.py:486-494
```

目前直接呼叫：

```python
self.state_calculator.is_fluid_valid(fluid)
```

應改成：

```python
self.query_service.is_fluid_valid(fluid)
```

### C. 已經走 PropertyQueryService 的 paths

以下 paths 已經符合預期：

```text
on_fluid_change()
    → query_service.is_fluid_valid()
    → query_service.set_reference_state()

on_ref_state_change()
    → query_service.set_reference_state()

perform_calculation() main query
    → query_service.query()
```

### D. Constructor dependency

目前 PropertyTab 仍保存：

```python
self.state_calculator = state_calculator
```

因為上述兩條 direct path 還存在，所以現在不能直接移除。正確順序是：

```text
先修正兩個 direct caller
→ 盤點所有 PropertyTab callers
→ 確認 state_calculator 不再被 PropertyTab 使用
→ 再決定是否移除 constructor dependency
```

---

# 4. Finding Matrix

| Finding | 已確認 root cause | 主要檔案 |
|---|---|---|
| F1 | mutation lock 只保護單次 mutation，沒有保護完整 CoolProp query transaction；chart/HVAC legacy paths 直接 mutation | `reference_state.py`, `state_service.py`, `coolprop_utils.py`, `hvac_calculations/compressor.py`, `condenser_heat.py` |
| F2 | `domain/psychrometrics/service.py` 直接 import Flet-owned excluded model | `domain/psychrometrics/service.py` |
| F3 | Flet/Telegram compatibility facades catch canonical `ValueError` 後 silent fallback | `UnitConverter.py`, `Telegram_bot/thermo_calculator.py` |
| F4 | `analysis_id` 由 class name + positional index 產生，不是 semantic stable ID | `analysis_tab.py` |
| F5 | PropertyTab constructor initialization 與 fluid validation 仍直接走 ThermoStateCalculator | `property_tab.py` |
| F6 | Architecture guardrail 沒禁止 `Flet_ui`/`Telegram_bot`，也沒檢查 direct reference-state mutation | `test_phase9_architecture_guardrails.py` |
| F7 | `pyproject.toml` 使用 placeholder description，repository HEAD 沒有 `README.md` | `pyproject.toml`, repository root |

---

# 5. Scope Confirmation

本輪 review finding closure 只處理：

- F1 reference-state synchronization boundary
- F2 psychrometric layer inversion
- F3 canonical unit validation
- F4 semantic stable analysis IDs
- F5 PropertyTab service boundary
- F6 architecture guardrails
- F7 README / project metadata

本輪不處理：

- 其他 Compressor analyses
- Telegram 全量 constructor DI
- 完整 chart renderer / sampling decomposition
- packaging target 全面重寫
- Telegram `V` divergence semantics

以上分析完成後才開始修改 production code。
