# 開發路線圖

本文件記錄 PR #6 之後已確認的開發範圍與順序。範圍刻意收斂到「階段 4」；
列在〈範圍外〉的項目有需要時再另行規劃，不在目前路線內預留實作。

## 1. 共同基礎

後續功能共用三個基礎，先建立基礎可避免每個功能各自回頭改寫：

| 基礎 | 使用者 | 建立於 |
|---|---|---|
| 狀態點模型（`ThermoStatePoint` + 序列化） | 飽和性質、SH/SC、State Library、狀態比較 | #8 |
| 最小 JSON 儲存層（含 schema version 欄位） | 基礎 Settings、State Library | #8 |
| 批次計算引擎（同一計算跑多組輸入） | Parameter Sweep、冷媒比較 | #12 |

## 2. 階段與 PR

### 階段 0 — #7 Integration Hardening

以單一 PR 完成，依 commit 分段（docs → test → fix → refactor → docs）：

1. 失效矩陣：定義切頁、切 SI/Imperial、切 Reference State、切冷媒、大氣壓力改變時，
   輸入／結果／圖表各自保留或失效。
2. Integration regression tests：
   - 跨頁 `A → B → A` 的輸入保留與結果失效
   - SI / Imperial 切換只重繪結果，不改輸入
   - Gauge / Absolute 跨頁、切單位後實際壓力一致
   - R32/R134a、ASHRAE/IIR 來回切換不互相污染
   - P-h、T-s、冷凍循環 P-h、濕空氣線圖不殘留舊圖、不重複加入
   - 既有冷凍循環（`cycle.vapor_compression`、`cycle.superheat_subcooling`）一併納入
3. 修正測試抓到的問題。
4. `StructuredResult` / `structured_from_text()` 邊界稽核：列出仍靠文字解析的模組；
   明定 `structured_from_text` 只供顯示，不得作為資料來源。
5. 將 characterization tests 遷出 legacy `AnalysisTab` 後移除，連同
   `PsyModule._resolve_mode_key()` 相容層與零引用 helper。
6. 修正 `docs/architecture.md` 仍把 `AnalysisTab` 描述為現行架構的內容。

與 PR #6 重疊的模組（壓縮機、蒸發器、冷凝器、濕空氣計算、`base_analysis_module`）
在 #6 合併後再處理。

### 階段 1 — #8 ThermoStatePoint 與基礎設施

- 由既有 `domain/refrigeration/states.py` 的 `CycleState` 推廣，不另建平行模型。
- 欄位：`fluid`、`reference_state`（必填）、P、T、h、s、ρ、Q、`source`（enum）、
  理想氣體旗標；`v`、`phase` 由其他欄位推導。
- 不同 `reference_state` 的狀態點禁止直接比較或相減。
- 濕空氣使用獨立的 `AirStatePoint`，與冷媒狀態點共用 protocol。
- 序列化：`to_dict` / `from_dict` 附 schema version。
- 最小 JSON 儲存層。
- 基礎 Settings：預設冷媒、預設 reference state、單位系統、大氣壓力／海拔、
  錶壓／絕對壓預設。
- 只做 domain / application / infrastructure，不接 UI。

### 階段 2 — 狀態點工具

- **#9 飽和性質工具 + SH/SC 現場工具**：沿用 `domain/refrigeration/saturation.py`；
  SH/SC 由循環頁移為獨立入口並提供現場輸入（錶壓、常用冷媒）。兩者輸出
  `ThermoStatePoint`，作為狀態點模型的第一批使用者。
- **#10 State Library + 狀態比較**：Save / Rename / Duplicate / Delete，A vs B 比較。

### 階段 3 — #11 空調側計算

可與階段 1、2 並行（修改範圍為 `domain/psychrometrics/`、空氣處理模組）。
規模較大，建議拆為三個 PR：

- **#11a 加濕 / 新風負荷 / 快速風量與冷量**
  - 新風負荷：焓差法，拆成顯熱與潛熱。
  - 加濕負荷：ṁ × (W_目標 − W_入口)。
- **#11b ASHRAE 62.1 通風率程序**
  - `Vbz = Rp·Pz + Ra·Az`，`Voz = Vbz / Ez`。
  - 單區、100% 外氣系統與多區再循環系統（系統通風效率 Ev）。
  - 內建常用空間類型的 Rp、Ra、預設人員密度。
- **#11c 台灣法規換氣量**
  - 依建築技術規則等國內法規的換氣量規定計算，並與 62.1 結果並列。

> **數值來源規則**：62.1 Table 6-1、Ez 表與台灣法規的條文數值，一律依規範原文
> 逐項提供並核對後才寫入程式；不得憑記憶填入。每個內建數值需註明規範版本與
> 表號／條號，並有對應測試。

### 階段 4 — #12 批次計算與比較

- 批次計算引擎（以冷凍循環服務的結構化結果為輸入，不解析顯示文字）。
- Parameter Sweep / What-if / 敏感度分析。
- 冷媒比較（同一條件下在「冷媒」維度上 sweep；只比較 COP、壓縮比等與
  reference state 無關的量，或焓差，不比較絕對焓值）。
- 參數曲線圖（例如 COP 對冷凝溫度）。

## 3. 待確認事項

| 事項 | 影響 |
|---|---|
| ASHRAE 62.1 採用的版本（2019 / 2022 / 2025） | #11b 的內建數值 |
| 內建的空間類型清單與其 Rp、Ra、人員密度、Ez 數值（依規範原文） | #11b |
| 台灣法規的適用條文與數值 | #11c |
| 大氣壓力改變時，Gauge 輸入保留錶壓或保留絕對壓 | #7 失效矩陣；暫定保留錶壓、重算絕對壓 |
| 冷凍循環是否支援以狀態點作為輸入 | 階段 2 之後的跨工具傳遞 |

## 4. 範圍外（有需要再補）

- Sweep / 冷媒比較結果匯出（複製表格、CSV）
- 快速診斷規則
- 時間序列 Trend Chart
- History / Snapshot / 收藏
- Import / Export / Report
- Project / Equipment / Session
- 完整 Settings
- 跨工具傳遞（送到壓縮機入口、Cycle State 1、P-h 圖）
