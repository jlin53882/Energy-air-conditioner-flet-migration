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

單位換算的權責：

- `domain.units.CanonicalUnitConverter` 是核心熱力性質（`P`、`T`、`H`、`S`、`D`、`V`、`U`）換算定義的唯一來源。
- Flet 的 `UnitConverter` 是通道層的顯示換算器：核心性質一律委派給 canonical converter；功率、流量、溫差、RH、效率、面積、風速、濕度比等非核心量由它註冊。它不是 domain authority，domain 程式碼不得依賴它。
- 通道層同樣必須 fail fast：未註冊的 property 或 unit 一律引發 `ValueError`，不得做恆等換算。新的顯示單位必須明確註冊並提供雙向換算；需要相同尺度時沿用既有定義（例如錶壓單位沿用對應絕對壓力單位的換算因子），不得在其他模組另建第三套換算常數。
- 溫差 `DeltaT` 沒有零點偏移（1 K = 1 °C 差 = 1.8 °F 差），不可用溫度 `T` 的換算處理。

### 錶壓力

錶壓力（相對大氣壓力的壓差）只存在於通道層。Flet 以獨立的 `PGauge` 量表示，單位標示為錶壓（`Pag`、`kPag`、`MPag`、`barg`、`psig`），與同尺度的絕對單位（`Pa`、`kPa`、`MPa`、`bar`、`psia`）一一對應；絕對壓力模式不得出現錶壓單位，錶壓模式不得出現 `psia` 等絕對單位。通道層以 `UnitConverter.gauge_to_absolute_pa()` 把錶壓 Pa 加上大氣絕對壓力，得到絕對 Pa 後才建立 application request；大氣壓力或換算後的絕對壓力不是正值時明確報錯。Application 與 domain 只接受絕對壓力 Pa，不認識錶壓單位。

## 3. Relative humidity semantics

`RH` 在 domain 內使用 `0.0` 至 `1.0` 的 fraction。Adapter 的 display unit `%` 使用 `0` 至 `100` 的 percentage；輸入必須透過 `convert_to_si("RH", value, "%")` 轉為 fraction，輸出必須透過 `convert_from_si("RH", value, "%")` 轉回 percentage。`Q` 的 quality semantics 不受此規則影響。

## 4. Specific volume / density semantics

`V` 代表 specific volume，canonical unit 為 `m³/kg`。

`D` 代表 density，canonical unit 為 `kg/m³`。

當 CoolProp 的 calculation 需要 density，而 input 是 specific volume 時，thermodynamic boundary 執行：

```text
D = 1 / V
```

Property code `V` 不得與 CoolProp viscosity code 或 density 混淆。Telegram 尚存的 legacy `V` behavior 是明確的 compatibility boundary，不是 canonical domain contract。

## 5. Thermodynamic property contract

`ThermodynamicStateService` 接受至少兩個 known property，將 input 轉為 canonical SI，並為設定的 property 加上 `phase` 回傳 neutral numeric result。Request 會選擇 CoolProp-backed calculation 或 ideal-gas calculation；channel adapter 負責 display conversion 與 error presentation。

Reference-state-sensitive calculation 必須攜帶明確的 request policy。一般 request 使用 `DEF`、`ASHRAE`、`IIR` 或 `NBP` 等 concrete policy。Internal operation 可以明確使用 `CURRENT`，表示該 scope 不修改 process reference state。一般 calculation 不得依賴前一個 request 留在 process 中的 state。`Water` 是一般 fluid request，使用明確的 `DEF` policy；backend 或 equation-model selection 與 reference-state policy 是不同責任。

## 6. Reference-state contract

CoolProp reference state 是 process-global。`ReferenceStateService` 提供唯一的 process-level synchronization mechanism 並控制 mutation。單一 request 的 mutation 與所有相依的 `PropsSI`/`PhaseSI` call，必須在同一個 synchronized transaction 中執行。

Mechanism 與 policy 必須分離：

- **Mechanism：** shared lock、controlled mutation 與 process-global observed registry 由 `ReferenceStateService` 擁有。
- **Policy：** caller/application 決定 request 所需的 reference state，並在 user flow 中保留 requested policy；`current()` 只能回報 observed process state，不是 user-preference store。

建立另一個 service instance 不得建立另一把 lock，也不得產生另一種 process-local `current()` 解讀方式。

## 7. HVAC calculation contract

`domain/hvac/` 下的 shared function 使用 canonical SI quantity。典型 contract 包含 `kg/s` 的 mass flow、`J/kg` 的 enthalpy、`W` 的 heat 與 power，以及 `Pa` 的 pressure。Flet 或 Telegram compatibility facade 可以接受 `kJ/kg`、`kW` 或其他 display unit，但只能在 adapter boundary 進行轉換。

Adapter conversion 或 architecture refactor 不得改變 physics formula。

## 8. Psychrometric contract

Shared psychrometric service 接受 numeric SI-oriented input 並回傳 neutral numeric result。特別是 temperature 使用 `K`、pressure 使用 `Pa`、enthalpy 使用 `J/kg`，result 使用 structured mapping。`PsychrometricService` 的 `result["RH"]` 永遠是 `0.0–1.0` fraction，service input 也只接受同一 semantic；Flet 與 Telegram adapter 必須先將 display percentage 轉為 fraction，legacy model boundary 再將 fraction 轉回 percentage。

Flet 與 Telegram 負責 label、display unit、string 以及 message/control rendering。Telegram display string 不是 domain output contract。

排除的 legacy model 透過 infrastructure adapter 存取；domain service 不得 import Flet-owned implementation。

`PsychrometricService` 另提供 `calculate_from_tdb_w`、`humidity_ratio_from_rh`、`relative_humidity_from_w`、`enthalpy_at` 與 `dry_bulb_from_enthalpy`。這些方法只使用注入 model 的 primitive（`cal_p`、`cal_Pws`、`cal_Ws`、`cal_Pw`、`cal_h`）進行正規化、驗證與反解，不得另寫第二套濕空氣公式。超過飽和的 `(Tdb, W)` 狀態必須明確失敗，不得回傳 RH 大於 1 的結果。

`domain/psychrometrics/processes.py` 提供絕熱混合、顯熱加熱／冷卻、冷卻除濕與依顯熱負荷估算送風量。所有流量以乾空氣質量流率（kg/s）表示，熱量以 W 表示；過程只做質量／能量平衡，狀態一律由 `PsychrometricService` 取得。冷卻除濕以「入口乾球、出口濕度比」的中間點分解顯熱與潛熱，並忽略冷凝水焓。

## 9. Refrigeration cycle contract

`domain/refrigeration/` 透過 `ThermodynamicStateProvider` 協定（由 `ThermodynamicStateService.calculate_state_si` 實作）取得 canonical SI 狀態，不直接呼叫 CoolProp，也不自行修改 reference state。

- `solve_vapor_compression_cycle`：單級蒸氣壓縮循環。蒸發壓力取蒸發溫度的露點（Q = 1），冷凝壓力取冷凝溫度的泡點（Q = 0）；壓縮以等熵效率修正，節流為等焓。只有提供冷凍能力時才回傳質量流率、功率與吸入體積流量，不推估未提供的系統量。結果的 `reference_state` 是求解時實際使用的 policy code；reference-state policy 只在 application（`RefrigerationService`）解析一次，繪製同一循環的圖表必須使用這個值，不得再以 `Auto` 重新解析。
- `saturation_properties`：已知絕對壓力或飽和溫度（恰好一個，且為正值），回傳 `SaturationPropertiesResult`：飽和液體（泡點，Q = 0，`key="liquid"`）與飽和蒸氣（露點，Q = 1，`key="vapor"`）兩個 `ThermoStatePoint`（`source=saturation`）。已知壓力時兩者同壓、溫度差為溫度滑移；已知溫度時兩者同溫、`pressure_difference_pa` 為泡點與露點壓力差；純冷媒兩者皆約為 0。蒸發潛熱 `latent_heat_j_kg`：
  - 已知壓力：泡點與露點同壓，提供同壓下飽和液→飽和蒸氣的焓差 `enthalpy_difference(vapor, liquid)`，經基準防護相減，與 reference state 無關。
  - 已知溫度：泡點與露點壓力不同（非共沸冷媒尤其明顯），同溫不同壓兩個狀態的焓差不是潛熱，因此為 `None`；需要潛熱時以該溫度對應的壓力改用已知壓力查詢。
  高於臨界點等無法飽和的條件明確失敗。
- `evaluate_superheat_subcooling`：以量測絕對壓力與管溫判斷過熱蒸氣、過冷液體或兩相，過熱度以露點、過冷度以泡點為基準，並回報非共沸冷媒的溫度滑移。結果附露點（`dew_state`）、泡點（`bubble_state`）狀態點，以及量測壓力與管溫對應的量測點（`measured_state`，`source=superheat_check`）。`measured_state` 只在兩種情況為 None，且都不影響判讀：量測點落在兩相區；或壓力與管溫落在飽和邊界、無法唯一決定狀態（`StateAmbiguityError`）。量測點查詢的其他失敗（一般 `StateQueryError`，例如與飽和邊界無關的 backend 失敗）與狀態資料不合法（缺少性質、乾度或密度無效、非有限值等，`ThermoStatePoint.from_state_mapping` 引發的 `ValueError`）都照常引發，不得降級為 None。reference state 只影響狀態點的焓、熵。
- `condenser_exergy_balance`／`analyze_condenser_exergy`：冷凝器的能量、熵與㶲平衡（忽略冷凝器壓降）。放熱量 `Q_H = ṁ·(h1 − h2)`，熱帶走的㶲 `Ex_Q = Q_H·(1 − T0/T_b)`，㶲破壞 `X_dest = ṁ·(ex1 − ex2) − Ex_Q = T0·S_gen`，㶲效率 `η = Ex_Q / [ṁ·(ex1 − ex2)]`。`T_b` 是熱量穿越所選分析控制邊界時的等效傳熱邊界溫度，不一定等於外部熱匯（外氣、熱水、室內空氣）的 bulk temperature：控制容積只涵蓋冷凝器本體時，`T_b` 應是該邊界對應的等效溫度，不可直接把外氣溫度當成冷凝器本體的 `T_b`；只有把分析邊界定義為「冷凝器直到最終向環境排熱的整體系統」時，`T_b = T0` 才代表熱最終排到環境（`η = 0`，冷媒減少的㶲在這個整體邊界內全部被破壞）。`T_b` 沒有預設值，必須由呼叫端依所選控制邊界明確指定。`T_b` 必須介於 `T0` 與冷媒平均放熱溫度 `(h1 − h2)/(s1 − s2)` 之間，超過上限時熵產生為負而拒絕；出口大量過冷時，平均放熱溫度可能低於飽和溫度，因此不得把飽和溫度當成預設邊界。`coolant_mean_temperature_k` 由冷卻介質（冷卻水、熱回收熱水或空冷空氣）進出口溫度計算熱力學平均溫度 `(T_out − T_in)/ln(T_out/T_in)`，可作為只涵蓋冷凝器本體時的 `T_b`；比熱視為定值時此 `T_b` 使 `Ex_Q` 等於冷卻介質獲得的㶲，`η` 即熱交換器㶲效率，且與冷卻介質流率、比熱無關；不適用於蒸發式冷凝器等有相變的冷卻介質。舊版 `condenser_heat.exergy_efficiency_condenser` 委派此函式，不再把 `T` 固定為 `T0`。

狀態服務無法計算的狀態（例如高於臨界壓力）必須轉為明確的 `ValueError`，不得回傳部分結果。

循環與冷凝器 Exergy 的狀態點是 `ThermoStatePoint`（見 §10），帶有流體、求解時實際使用的 reference state 與來源；冷凍效果與冷凝器㶲平衡的焓差、熵差都經基準防護後才相減。

## 10. State point contract

`domain/state_points/` 定義跨工具共用的狀態點，全部使用 canonical SI。

- `ThermoStatePoint`（冷媒／工作流體）：`fluid`、`reference_state`、`pressure_pa`、`temperature_k`、`enthalpy_j_kg`、`entropy_j_kgk`、`density_kg_m3`、`quality`、`source`、`is_ideal_gas`，以及選填的 `key`、`label`。
  - `reference_state` 必須是求解時實際使用的明確 policy code（`DEF`、`ASHRAE`、`IIR`、`NBP`，別名會正規化）；不接受 `Auto` 或 `CURRENT`。
  - 乾度 `quality`：-1 為 CoolProp 單相標記（過冷液、過熱蒸氣或超臨界）；0–1 為合法乾度範圍；其他數值屬於無效狀態點資料，建立或讀取時一律拒絕。
  - 比容 `specific_volume_m3_kg` 與相態 `phase` 由其他欄位推導，不另外保存：乾度 0 為飽和液、1 為飽和蒸氣、介於兩者之間為兩相、-1 為單相。
  - 冷凍循環的冷凍效果、壓縮功與冷凝放熱，都以 `enthalpy_difference` 由循環狀態點相減。
  - 焓、熵的絕對值取決於 reference state。流體、reference state 或性質模型（CoolProp／理想氣體）不同的狀態點不得直接比較或相減；必須使用 `enthalpy_difference`／`entropy_difference`，基準不同時引發 `StateBasisMismatchError`。理想氣體模型不提供比熵，熵差明確失敗。
- `AirStatePoint`（濕空氣）：海拔、大氣壓力、乾球／濕球／露點溫度、相對濕度（0–1 分率）、濕度比、每公斤乾空氣的比焓與比容，以及 `source`、`label`。濕空氣使用濕空氣模型固定的基準，與冷媒狀態點是不同型別，兩者共用 `StatePoint` protocol（`source`、`label`、`to_dict()`）。
- `source` 是 `StateSource` 列舉（`property_query`、`refrigeration_cycle`、`condenser_exergy`、`saturation`、`superheat_check`、`psychrometrics`、`air_process`、`manual`），值會寫入保存的文件，不得任意更名。
- 序列化：`to_dict()` 產生含 `schema`（`thermo_state_point`／`air_state_point`）與整數 `schema_version` 的標準 JSON 相容 dict；`from_dict()` 與 `state_point_from_dict()` 在種類不符、版本較新或較舊、欄位缺漏或多出、數值無效時明確失敗，不猜測資料意義（`domain/schema.py`）。

## 11. State Library contract

`domain/state_library.py` 定義使用者保存的狀態清單，`domain/state_points/comparison.py` 定義兩個狀態的比較；兩者都不做 I/O。

- `SavedState`：穩定識別碼 `id`（改名不變）、使用者名稱 `name`（去除前後空白、不可空白、最多 80 字元）與狀態點 `point`（`ThermoStatePoint` 或 `AirStatePoint`，其他型別拒絕）。
- `StateLibrary`：依保存順序排列、識別碼不可重複。`with_added`／`renamed`／`duplicated`／`removed` 都回傳新清單；複本緊接在原項目之後，名稱加「（複本）」且不超過長度上限。
- 預設名稱：冷媒為「流體 · 顯示名稱」，濕空氣為「濕空氣 · 顯示名稱」。
- 序列化：`to_dict()` 帶 `schema = state_library`、`schema_version = 1`，每個項目內含狀態點自己的 schema 文件；`from_dict()` 在種類或版本不符、欄位缺漏或多出、狀態點無效或識別碼重複時明確失敗。
- 比較 `compare_states(a, b)`：差值一律為 B − A（canonical SI）。
  - 冷媒：溫度、壓力、密度、比容直接相減。焓、熵只在流體、reference state 與性質模型都相同時以 `enthalpy_difference`／`entropy_difference` 相減；基準不同時列出兩邊數值、差值為 None 並說明原因。理想氣體模型不提供比熵，熵列不比較。乾度只在兩邊都是兩相／飽和（0–1）時相減，單相標記 -1 不比較。
  - 濕空氣：乾球、濕球、露點溫度、相對濕度、濕度比、比焓與比容（每公斤乾空氣）、大氣壓力與海拔直接相減；濕空氣模型的基準固定。
  - 冷媒與濕空氣狀態不能互相比較（`StateBasisMismatchError`）。

`application/state_library.StateLibraryService` 透過注入的 `DocumentStore` 保存文件 `state_library`：

- 每次變更先寫入、成功後才更新記憶體並通知訂閱者；寫入失敗以 `ValueError` 回報且清單不變。
- 讀取失敗：文件損壞、schema 種類或版本不支援，或檔案系統讀取錯誤（`OSError`，例如權限不足、路徑是資料夾）時，狀態庫視為不可用：記錄 `load_error`、清單為空、拒絕所有寫入，原始資料保留、不被覆蓋。只有儲存層回傳「文件不存在」（`None`）才視為空的新狀態庫，讀取錯誤不得當成不存在。狀態庫是附加功能，讀取失敗不影響應用程式啟動與其他計算工具。
- 批次保存 `save_many(points)`：在 `state_library` 文件層級全有或全無。先建立全部項目再寫入一次；任一狀態點無效或寫入失敗時一筆都不新增（檔案與記憶體不變、不通知訂閱者），成功時只寫入一次、通知一次。UI 的「儲存狀態點」（含「全部儲存」）一律經由此方法。
- 訂閱者（例如狀態庫畫面重新整理）在寫入成功後才被通知；訂閱者失敗只記錄在 log，不回滾也不使已完成的變更看起來失敗，並繼續通知其他訂閱者。
- 可保存的只有 `ThermoStatePoint` 與 `AirStatePoint`（`domain.state_library.SavedPoint`）；分析定義的 `state_points` 使用同一型別，回傳其他物件屬於程式錯誤，在顯示儲存選單時以 `TypeError` 立即失敗。

## 12. Error contract

Invalid request shape、known property 不足、invalid fluid/policy 與 unknown canonical unit 都必須明確失敗。狀態查詢失敗分為三類：

| 類別 | 產生處 | 例外 | 處理 |
|---|---|---|---|
| 已知性質無法唯一決定狀態（目前只有壓力與溫度落在飽和邊界） | `ThermodynamicStateService.calculate_state_si`，且兩個條件都要成立：(1) 失敗來自 CoolProp 狀態求解本身（`PropsSI`／`PhaseSI` 的 `ValueError`，服務內部包裝為 `CoolPropStateCalculationError`）；(2) 以物理條件確認 (P, T) 在飽和邊界：該溫度的泡點或露點飽和壓力與給定壓力的相對差不超過 `PT_SATURATION_RELATIVE_TOLERANCE`（1e-5；CoolProp 自身的拒絕門檻為 1e-6）。不解析 CoolProp 錯誤文字 | 服務層 `IndeterminateStateError`（`RuntimeError` 子類別）→ `query_state` 轉為 `StateAmbiguityError`（`StateQueryError` 子類別） | 只有過熱度判讀的量測點可以攔截並略過，其他流程照常失敗 |
| 一般狀態查詢失敗（超出適用範圍、流體無效、backend 異常、reference-state 設定失敗等） | 狀態服務的其他 `RuntimeError`，包括不屬於狀態求解的內部錯誤 | `query_state` 轉為 `StateQueryError`（`ValueError` 子類別，既有以 `ValueError` 處理的呼叫端不受影響） | 不得被吞掉 |
| 狀態資料不合法 | `ThermoStatePoint.from_state_mapping` | `ValueError`（不是 `StateQueryError`） | 屬於程式錯誤，不得被吞掉 |

「輸入接近飽和」本身不是失敗原因：reference-state 設定、backend 異常或程式錯誤即使發生在飽和邊界上的 (P, T)，也不得被重新分類為 `IndeterminateStateError`。不得以寬泛的 `ValueError`、`RuntimeError` 或 `StateQueryError` 攔截來處理「狀態無法唯一決定」。Compatibility facade 可以增加 channel-specific error presentation，但不得吞掉 canonical contract error，也不得默默替換成另一種 physical meaning。
