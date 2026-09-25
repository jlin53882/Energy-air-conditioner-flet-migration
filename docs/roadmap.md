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

以單一 PR 完成，依 commit 分段（docs → test → fix → refactor → docs）。

**結果**：失效矩陣見 [`state-invalidation.md`](state-invalidation.md)，回歸測試見
`tests/test_integration_hardening.py`。修正三個問題：切換單位時以計算後已修改的輸入
重算、熱力圖重新進入同一路由時清除已繪製的圖、壓縮比頁違反錶壓契約；並移除
legacy `AnalysisTab` 與其相容層。原規劃項目如下：

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
4. `StructuredResult` / `structured_from_text()` 邊界稽核：目前只有 `PsyModule` 提供原生
   `structured_result`，其餘分析（壓縮機、蒸發器、冷凝器含 Exergy、冷凍循環、空氣處理）
   都靠文字解析。明定 `structured_from_text` 只供顯示，不得作為資料來源。
5. 將 characterization tests 遷出 legacy `AnalysisTab` 後移除，連同
   `PsyModule._resolve_mode_key()` 相容層與零引用 helper。
6. 修正 `docs/architecture.md` 仍把 `AnalysisTab` 描述為現行架構的內容。

PR #6 已合併，以上項目皆可直接進行。PR #6 帶入的內容一併納入：

- 冷凝器 Exergy 頁（`condenser.exergy`）納入跨頁、單位切換與 Reference State 測試。
  其結果只取狀態差值（Δh、Δs），切換 ASHRAE / IIR 後數值應完全相同，可作為
  不變量測試。
- 冷凝器 Exergy 頁的壓力只接受絕對壓力，冷凍循環頁則可切換錶壓／絕對壓；
  在失效矩陣中記錄此差異，是否統一另行決定，不在 #7 內修改。
- 舊版 `hvac_calculations`（compressor／exergy／condenser_heat／throttling）仍有
  production caller，單位契約已由 `tests/test_legacy_hvac_unit_contract.py` 固定；
  死碼稽核不得移除它們。

### 階段 1 — #8 ThermoStatePoint 與基礎設施

- 由既有 `domain/refrigeration/states.py` 的 `CycleState` 推廣，不另建平行模型；
  目前的使用者 `vapor_compression.py`、`condenser_exergy.py` 一併遷移。
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
只包含不需要外部規範數值的計算：

- 新風負荷：焓差法，拆成顯熱與潛熱。
- 加濕負荷：ṁ × (W_目標 − W_入口)。
- 快速風量與冷量。

需要規範數值的換氣量計算（ASHRAE 62.1、台灣法規）暫緩，見〈範圍外〉。

### 階段 4 — #12 批次計算與比較

- 批次計算引擎：只接 domain / application 服務的結構化結果（冷凍循環、冷凝器 Exergy），
  不解析顯示文字，也不接舊版 `hvac_calculations`。
- Parameter Sweep / What-if / 敏感度分析。
- 冷媒比較（同一條件下在「冷媒」維度上 sweep；只比較 COP、壓縮比等與
  reference state 無關的量，或焓差，不比較絕對焓值）。
- 參數曲線圖（例如 COP 對冷凝溫度）。

## 3. 待確認事項

| 事項 | 影響 |
|---|---|
| 大氣壓力改變時，Gauge 輸入保留錶壓或保留絕對壓 | #7 已採用保留錶壓、計算時重算絕對壓，待確認 |
| 壓縮機分析跟隨物性查詢頁的 Reference State，冷凍循環不跟隨，是否統一 | #8 狀態點的 `reference_state` 來源 |
| 分析頁修改輸入時是否立即使結果失效（與物性查詢頁一致） | 分析頁的失效規則 |
| 冷凝器 Exergy 頁是否支援錶壓輸入 | 壓力輸入一致性 |
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
- 換氣量計算（需要時再做，屆時需先提供規範資料）。已確認的方向：
  - ASHRAE 62.1 通風率程序：`Vbz = Rp·Pz + Ra·Az`、`Voz = Vbz / Ez`，
    支援單區、100% 外氣與多區再循環系統（系統通風效率 Ev），並內建常用空間類型。
  - 台灣法規換氣量，與 62.1 結果並列。
  - 開始前需提供：62.1 版本、內建空間類型及其 Rp、Ra、預設人員密度、Ez 表數值、
    台灣法規適用條文與數值。
  - **數值來源規則**：規範數值一律依原文逐項提供並核對後才寫入程式，不得憑記憶填入；
    每個內建數值需註明規範版本與表號／條號，並有對應測試。
