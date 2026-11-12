# 計算模型與參考基準（Auto）工程指引

本文件說明本專案如何選擇**計算模型**（真實流體／理想氣體／濕空氣）與 **CoolProp reference state**（IIR／ASHRAE／NBP／DEF），以及如何正確對照外部蒸氣表。實作集中於 `domain/thermodynamics/thermo_policy.py`；實際數字可用 `scripts/coolprop_reference_report.py` 重新產生（範例輸出見 [reference-state-r717-validation.md](reference-state-r717-validation.md)）。

## 1. 四種 reference state

| 代碼 | 定義（零點） | 備註 |
|---|---|---|
| `IIR` | 0 °C 飽和液體 h = 200 kJ/kg、s = 1 kJ/(kg·K) | 冷凍工程 SI 表格慣例；ASHRAE Handbook 2025 SI 多數冷媒表亦採此慣例。CoolProp 代碼名稱 `ASHRAE` **不等於**所有 ASHRAE SI 表格的基準。 |
| `ASHRAE` | −40 °C 飽和液體 h = 0、s = 0 | 北美 IP 單位表格常見。 |
| `NBP` | 正常沸點飽和液體 h = 0、s = 0 | CoolProp 8.0.0 實測以 **101.325 kPa** 定義（`tests/test_thermo_policy.py` 鎖定此行為；升級 CoolProp 時請重新檢查）。 |
| `DEF` | CoolProp 該流體狀態方程的預設基準 | 各流體不同；Water 為 IAPWS-95 三相點飽和液 u = 0、s = 0。不是所有流體共用同一零點。 |

基準只改變焓、熵的**絕對值**。同一流體、同一狀態方程下，壓力、溫度、密度、乾度，以及**同一基準內**的焓差、潛熱、COP、質量流量、壓縮功都不變。不同基準（或不同模型）的焓、熵不可直接相減；`ThermoStatePoint` 與狀態比較會阻擋這類運算。

某些流體在物理上不支援某些基準（例如水的三相點 273.16 K 高於 0 °C，因此沒有 IIR／ASHRAE；CO₂ 的三相點壓力 518 kPa 高於 1 atm，因此沒有 NBP；氮、甲烷、乾空氣在 0 °C 沒有飽和液）。是否支援以**目前安裝的 CoolProp 實際行為**探測，不另外維護表格。

## 2. 解析順序：模型 → 基準

```
使用者選擇（模型、基準）＋ 流體 ＋ 是否帶濕度條件
        │
        ▼
① 模型層  Auto → Air 且有明確濕度條件？ 是 → 濕空氣；否 → CoolProp 真實流體（Air 為乾空氣）
          手動 → 真實流體／理想氣體（Air、Water）／濕空氣（只限 Air，且必須有濕度條件）
        │
        ▼
② 基準層  只有真實流體有 reference state；理想氣體與濕空氣標示「不適用」
          Auto：Water → DEF；Air（乾空氣）→ DEF；其他流體 → CoolProp 支援 IIR 時 IIR，否則 DEF（附備援原因）
          手動：CoolProp 不支援 → 明確錯誤（不靜默改 DEF）
        │
        ▼
ResolvedThermoPolicy（不可變快照）→ 計算、結果顯示、圖表、狀態點保存都用同一份
```

- **不維護冷媒白名單**：冷媒是否採 IIR 由 CoolProp 能力探測決定（0 °C 存在飽和液即可）。Water 與 Air 是唯二的明確規則，集中在 resolver。
- **別名**：以 CoolProp 本身解析（`R717`／`NH3`／`ammonia` → `Ammonia`，`R744` → `CarbonDioxide`，`R729` → `Air`）。process-global registry 以 canonical 名稱為 key，避免同一物質因別名分裂。混合物字串（含 `&`、`[...]`）不做別名解析並明確失敗，因為 CoolProp 對混合物字串只回傳第一成分名稱。
- **快取**：只快取與流體識別、能力與函式庫版本相關的 metadata（canonical 名稱、`(CoolProp 版本, 流體, 基準) → 是否支援`），不快取任何物性數值。暖快取下解析一次約 4 µs。
- **執行緒安全**：能力探測與每一次計算都在既有的 process-wide `RLock`（`ReferenceStateService.calculation_scope`）內執行；探測成功後會恢復 registry 原本記錄的基準。
- **工作流程**：`Workflow`（物性查詢、冷凍分析、圖表、批次、舊入口）記錄在快照中供追溯；Auto 基準規則在各工作流程**相同**，因此各頁的 Auto 一致。

### 優先序

目前實作的優先序：**頁面上使用者明確選擇 > 模型／工作流程的 Auto 規則**。

- 各頁面擁有自己的選單，不跟隨其他頁面（既有契約）。
- `WorkspaceSettings.default_reference_state` 已可保存，但**目前尚未套用到任何頁面**（既有狀況，本次未變更；見待討論事項）。
- 尚未實作「資料來源 Profile」（例如 Siemens R717、ASHRAE 2025 SI）；若日後加入，Profile 只能選擇基準，不得覆寫 EOS 或加入常數焓修正，且須與計算模型／reference state 分開保存。

## 3. 三種「空氣」

| 模型 | 計算方式 | 基準 | 比性質 |
|---|---|---|---|
| 乾空氣真實流體 | CoolProp `PropsSI(..., 'Air')`（擬純流體） | Auto → `DEF`（沒有 IIR／ASHRAE） | 每 kg 乾空氣作為工質（kJ/kg） |
| 理想氣體 | `P = ρRT`、常數 cp；`h = cp·T`（0 K 外插 h = 0） | 不適用（狀態點記為 `IDEAL_GAS`） | kJ/kg；**不提供比熵**（不以 0 代替） |
| 濕空氣 | 既有 `PsychrometricService`（ASHRAE 公式 `h = 1.006 t + W(2501 + 1.86 t)`） | 不適用；焓零點為 0 °C 乾空氣與 0 °C 液態水 | 每 kg 乾空氣（kJ/kg_dry_air） |

- 只有 P、T 的 `Air` 一律視為乾空氣，不猜濕度。物性頁的「已知條件」列沒有濕度性質，因此 Auto 在物性頁不會自動切到濕空氣；請在「計算模型」選擇「濕空氣」，輸入乾球溫度＋ RH／濕球溫度／濕度比其中**一個**，總壓由海拔依標準大氣換算。
- 濕空氣焓（每 kg 乾空氣，含水蒸氣）與 `PropsSI('H', …, 'Air')`（乾空氣工質、DEF 基準）是不同性質，數值相差數百 kJ/kg，不可互比。
- 本次**沒有**更換濕空氣公式；CoolProp `HAPropsSI` 只作為交叉驗證（25 °C、RH 50 %、海拔 0 m：W、h 差異 < 0.5 %，見測試）。
- 理想氣體不處理飽和或兩相狀態（拒絕乾度輸入），也不得與真實流體的焓、熵比較。

## 4. 壓力語義

- domain／application 一律使用**絕對壓力 Pa**。`kPag`／`psig` 只存在於 UI 邊界，換算時加上大氣壓力（預設 101.325 kPa，或依海拔換算）。
- 切換 Gauge／Absolute 只改表示方式，不改實際壓力，也不會使結果失效。
- **152 kPa（abs）與 152 kPag 是不同狀態**：R717 前者飽和溫度約 −24.9 °C；後者為 253.325 kPa abs，約 −13.3 °C。對照蒸氣表時，請確認表格的壓力是絕對壓（Siemens Table 2-5 為 bar abs）。

## 5. 如何對照 Siemens R717 蒸氣表（h'' = 1429.6 kJ/kg）

1. 物性頁或「飽和性質」頁選流體 `R717`（或 `Ammonia`、`NH3`），參考基準 `Auto`（解析為 IIR）或手動 `IIR`；Siemens 表 0 °C h' = 200.0 kJ/kg，屬 IIR 慣例。
2. 以**溫度**查詢：−25 °C、Q = 1（或飽和性質頁「已知溫度」）。不要用 P、T 查飽和狀態（P、T 在飽和線上無法唯一決定狀態，系統會回報 `IndeterminateStateError`）。
3. CoolProp 8.0.0（Ammonia：Gao et al. JPCRD 2020）結果：P_sat = 151.42 kPa abs、h' = 86.04、h'' = 1430.51、r = 1344.47 kJ/kg。
4. 與 Siemens 表比較：Δp = −0.006 bar（表格解析度 0.01 bar）、Δh'' = +0.91、Δh' = −0.96、Δr = +1.77 kJ/kg。

差異來源是**狀態方程不同**（Siemens 表的臨界點 132.35 °C／113.53 bar 與 Gao 2020 的 132.41 °C／113.63 bar 不同）加上表格四捨五入：壓力全表在 0.01 bar 內一致；焓在 0 °C 錨點完全相同，越遠離錨點差異越大，近臨界點可達 10 kJ/kg 以上。**本專案不會以常數修正 CoolProp 的焓去對齊任何表格。** 回歸測試對 −40…0 °C 使用跨來源容差：壓力 0.01 bar、焓 1.5 kJ/kg、潛熱 2.5 kJ/kg（由全表實測差異決定）；同一 CoolProp 版本、同一基準下的比較則要求數值一致（相對誤差 1e-12）。

若以表格**壓力** 152 kPa 查詢，得到的是 −24.92 °C 的飽和狀態，與 −25 °C 不是逐位相同的狀態（表格壓力已四捨五入），不應要求逐位相等。

## 6. 結果顯示與保存

- 結果卡片、匯出文字與分析頁的「模型與基準」分組顯示：實際計算模型、實際基準（例如 `IIR（Auto）`、`ASHRAE（手動）`、`不適用`）、焓／熵零點、比性質基準（kJ/kg 或 kJ/kg_dry_air）、決策原因、備援說明、CoolProp 版本。
- 改變模型、基準、流體或濕度條件會使舊結果與儲存選單失效；單純的單位或 Gauge／Absolute 切換不會。
- 物性頁切換模型**不會**把物質改成 R32。只有切到「濕空氣」時會把物質設為 `Air`，並提示與暫存原輸入；切回其他模型時還原。
- 物性頁不再於選單變更時呼叫 process-global `set_reference_state()`；每次計算都在 `calculation_scope` 內使用當次解析的 concrete 基準。

## 7. Schema 與相容性

| 項目 | 變更 | 相容性 |
|---|---|---|
| `ThermoStatePoint` schema | v1 → **v2**：理想氣體狀態點 `reference_state = "IDEAL_GAS"`、`entropy_j_kgk = null` | 讀取 v1：冷媒狀態點內容不變；v1 理想氣體（S = 0、記錄任意基準）轉為 `IDEAL_GAS`／`null`。v1 理想氣體若 S ≠ 0（非本程式寫入）則明確拒絕。**舊版程式無法讀取 v2 文件。** |
| Auto 基準 | 冷媒 **ASHRAE → IIR**（水、乾空氣維持 DEF） | 舊的已保存狀態點保留原本的 concrete 基準（例如 ASHRAE）；與新計算的 IIR 狀態點比較時，焓、熵會標示「基準不同，不相減」，需重新計算或手動選 ASHRAE。COP、潛熱、Exergy、批次指標不受影響。 |
| 手動不支援的基準 | 舊：`Water` + `ASHRAE`/`IIR` 靜默改用 DEF；新：明確錯誤 | 呼叫端需改用 Auto 或 DEF。 |
| 理想氣體結果 | 共用 domain 服務不再包含 `S`（舊為 0）；乾度輸入明確拒絕 | Flet 文字輸出顯示「不提供（理想氣體模型）」。 |
| `PropertyQueryRequest` | 新增選填 `model`；新增 `HumidAirQueryRequest`、`PropertyQueryService.query_with_policy()`／`query_humid_air()` | `query()` 介面不變；`reference_state` 預設仍為 `DEF`。 |
| 物性頁 UI | 「計算模式（CoolProp／Water）」＋「理想氣體」勾選 → 「計算模型」選單；基準選單加入 Auto 並以 `DEF` 取代 `Default` | 依 UI 控制項名稱撰寫的外部腳本需更新。 |
| Telegram | **不在本次範圍**：`Telegram_bot/` 未修改，物性查詢仍固定使用 `DEF`、不導入 Auto，舊比容（V）路徑的理想氣體仍回傳 `S = 0`。 | 連帶影響：Telegram 非 V 輸入的查詢本來就委派共用 domain 服務，因此理想氣體結果不再列出熵（原為 0）；其他數值不變。 |
