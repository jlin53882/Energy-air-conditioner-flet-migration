# 領域契約

本文件描述目前的 domain semantics。除非另有明確說明，display unit 與 channel formatting 都屬於 adapter 責任。

## 1. Canonical quantity

共享 domain 使用以下 canonical quantity：

- pressure `P`：`Pa`
- temperature `T`：`K`
- enthalpy `H`：`J/kg`
- entropy `S`：`J/(kg·K)`
- density `D`：`kg/m³`
- specific volume `V`：`m³/kg`
- internal energy `U`：`J/kg`
- mass：`kg`
- mass flow：`kg/s`
- power：`W`
- energy：`J`

Quality `Q` 為無因次量。`kPa`、`bar`、`psi`、`°C`、`°F`、`kJ/kg` 與其他 display unit 都是 adapter-facing unit，不是 domain 內部的 canonical unit。

## 2. Unit conversion 規則

Adapter 可以接受 display unit 並建立 request。Canonical unit converter 負責 consolidated core property 的 registered conversion definition。每個 conversion definition 都必須在兩個方向明確指出 property code 與 unit。

對已 canonicalized 的 core quantity，unknown unit 必須視為錯誤。系統必須明確回報 failure，不得假設 input 已是 SI，也不得默默回傳原值。

## 3. Specific volume / density semantics

`V` 代表 specific volume，canonical unit 為 `m³/kg`。

`D` 代表 density，canonical unit 為 `kg/m³`。

當 CoolProp 的 calculation 需要 density，而 input 是 specific volume 時，thermodynamic boundary 執行：

```text
D = 1 / V
```

Property code `V` 不得與 CoolProp viscosity code 或 density 混淆。Telegram 尚存的 legacy `V` behavior 是明確的 compatibility boundary，不是 canonical domain contract。

## 4. Thermodynamic property contract

`ThermodynamicStateService` 接受至少兩個 known property，將 input 轉為 canonical SI，並為設定的 property 加上 `phase` 回傳 neutral numeric result。Request 會選擇 CoolProp-backed calculation 或 ideal-gas calculation；channel adapter 負責 display conversion 與 error presentation。

Reference-state-sensitive calculation 必須攜帶明確的 request policy。一般 request 使用 `DEF`、`ASHRAE`、`IIR` 或 `NBP` 等 concrete policy。Internal operation 可以明確使用 `CURRENT`，表示該 scope 不修改 process reference state。一般 calculation 不得依賴前一個 request 留在 process 中的 state。`Water` 是一般 fluid request，使用明確的 `DEF` policy；backend 或 equation-model selection 與 reference-state policy 是不同責任。

## 5. Reference-state contract

CoolProp reference state 是 process-global。`ReferenceStateService` 提供唯一的 process-level synchronization mechanism 並控制 mutation。單一 request 的 mutation 與所有相依的 `PropsSI`/`PhaseSI` call，必須在同一個 synchronized transaction 中執行。

Mechanism 與 policy 必須分離：

- **Mechanism：** shared lock、controlled mutation 與 process-global observed registry 由 `ReferenceStateService` 擁有。
- **Policy：** caller/application 決定 request 所需的 reference state，並在 user flow 中保留 requested policy；`current()` 只能回報 observed process state，不是 user-preference store。

建立另一個 service instance 不得建立另一把 lock，也不得產生另一種 process-local `current()` 解讀方式。

## 6. HVAC calculation contract

`domain/hvac/` 下的 shared function 使用 canonical SI quantity。典型 contract 包含 `kg/s` 的 mass flow、`J/kg` 的 enthalpy、`W` 的 heat 與 power，以及 `Pa` 的 pressure。Flet 或 Telegram compatibility facade 可以接受 `kJ/kg`、`kW` 或其他 display unit，但只能在 adapter boundary 進行轉換。

Adapter conversion 或 architecture refactor 不得改變 physics formula。

## 7. Psychrometric contract

Shared psychrometric service 接受 numeric SI-oriented input 並回傳 neutral numeric result。特別是 temperature 使用 `K`、pressure 使用 `Pa`、enthalpy 使用 `J/kg`，result 使用 structured mapping。

Flet 與 Telegram 負責 label、display unit、string 以及 message/control rendering。Telegram display string 不是 domain output contract。

排除的 legacy model 透過 infrastructure adapter 存取；domain service 不得 import Flet-owned implementation。

## 8. Error contract

Invalid request shape、known property 不足、invalid fluid/policy 與 unknown canonical unit 都必須明確失敗。Compatibility facade 可以增加 channel-specific error presentation，但不得吞掉 canonical contract error，也不得默默替換成另一種 physical meaning。
