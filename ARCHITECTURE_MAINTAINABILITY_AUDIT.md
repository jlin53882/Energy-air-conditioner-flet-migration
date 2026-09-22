# Energy Air Conditioner Flet Migration
# 架構與可維護性完整分析報告

> 分析類型：read-only 架構／可維護性審查
> 基準 workspace：`C:\Users\admin\workspace\Energy_air-conditioner_flet-migration`
> 基準 commit：`a28fdda`（Flet migration verification）
> 分析範圍：除明確排除檔案外，納入專案內 Python、測試、入口、打包與設定邊界
> 狀態：本報告只提出分析與重構建議，不代表已完成重構

---

## 目錄

1. [執行摘要](#1-執行摘要)
2. [分析範圍與方法](#2-分析範圍與方法)
3. [目前專案架構](#3-目前專案架構)
4. [檔案規模與責任概覽](#4-檔案規模與責任概覽)
5. [Tier A：高優先架構問題](#5-tier-a高優先架構問題)
6. [Tier B：中優先維護性問題](#6-tier-b中優先維護性問題)
7. [Tier C：低優先整理事項](#7-tier-c低優先整理事項)
8. [目前做得好的架構基礎](#8-目前做得好的架構基礎)
9. [建議目標架構](#9-建議目標架構)
10. [分階段重構路線](#10-分階段重構路線)
11. [測試與安全重構策略](#11-測試與安全重構策略)
12. [不應立即修改的部分](#12-不應立即修改的部分)
13. [已知限制與未驗證項目](#13-已知限制與未驗證項目)
14. [最終結論](#14-最終結論)

---

## 1. 執行摘要

目前專案的主要問題不是單純「Python 檔案行數太多」，而是多個變更原因被集中在同一個 class 或 module：

- Flet UI 建構、事件處理、輸入解析、單位轉換、CoolProp 呼叫、物理計算、格式化與錯誤顯示混在一起。
- Flet 與 Telegram 各自維護一套熱力學、單位轉換、HVAC 公式與 Psychrometric 邏輯。
- 分析模組透過 `dict`、`**kwargs`、字串 display name 與動態 attribute 查找互相連接，缺乏明確的 typed contract。
- 圖表功能把狀態點解析、CoolProp 取樣、Matplotlib rendering 與 Flet lifecycle 放在同一條執行路徑。
- 測試目前主要保護 Flet migration regression，還不是完整的 repository-wide application test architecture。

最高風險集中在以下五項：

1. Flet／Telegram 兩套獨立熱力學與單位核心。
2. `hvac_compressor_module.py`（928 行）承擔多個分析功能與 UI／計算責任。
3. `property_tab.py`（564 行）同時是 View、Controller 與 calculation orchestrator。
4. Psychrometric adapter 在 Flet 與 Telegram 重複存在。
5. `thermo_diagram_module.py` 與 `coolprop_utils.py` 同時處理 UI、CoolProp、Matplotlib 與 chart data。

建議的核心策略是：

> 先建立共用 domain contract，再拆 UI；不要先把大型檔案機械切成多個檔案。

---

## 2. 分析範圍與方法

### 2.1 明確排除

使用者指定以下檔案不分析其內部實作：

```text
C:\Users\admin\workspace\Energy_air-conditioner_flet-migration\Flet_ui\PsychrometricChart\PsychrometricChart_01_ASHF_model.py
```

本報告只在需要判斷跨層依賴時，記錄其他檔案對該 model 的 import／呼叫關係；不對該檔案本身的架構、公式或品質下結論。

### 2.2 實際檢查項目

- Flet application bootstrap、tabs 與 analysis modules
- property、unit conversion、thermodynamic calculation
- HVAC pure calculation modules
- CoolProp／psychrometric／chart 邊界
- Telegram calculator、handlers、transport 與 config
- tests、entrypoints、packaging scripts、project metadata
- import／call relationship 與 GitNexus structural check
- Python 檔案行數、class／function 分布與責任集中度

### 2.3 證據分類

- **已驗證**：由原始碼、AST、GitNexus 或實際測試輸出直接確認。
- **架構推論**：根據已驗證的依賴與責任推導出的維護風險。
- **建議**：尚未實作的目標設計，不代表目前已有該模組。

### 2.4 已驗證基準

- GitNexus repository index：47 files、472 symbols、39 processes。
- GitNexus import-cycle check：`cycleCount: 0`、`componentCount: 0`。
- `uv run pytest -q`：`12 passed`。
- `uv lock --check`：PASS。
- `compileall`：PASS。
- `uv pip check`：PASS。

以上是既有基準驗證，不代表本報告建議的重構已完成。

---

## 3. 目前專案架構

### 3.1 現況架構圖

```text
run.py
├─ Flet_ui.flet_app.main
│  ├─ UnitConverter
│  ├─ ThermoStateCalculator
│  ├─ PropertyFormatter
│  ├─ HVACAnalyzer
│  ├─ PsychrometricCalculator
│  ├─ PropertyTab
│  └─ AnalysisTab
│     ├─ CompressorModule
│     ├─ EvaporatorModule
│     ├─ CondenserModule
│     ├─ PsyModule
│     └─ ThermoDiagramModule
│        └─ coolprop_utils
│
└─ Telegram_bot.config
   └─ logging/config side effects

Telegram_bot.bot_application
├─ property_handler
├─ analysis_handler
└─ ThermoCalculator
   └─ excluded PsychrometricChart model
```

### 3.2 現況分層判斷

目前目錄名稱看起來已有 UI、unit、HVAC calculation、Telegram 等區分，但實際責任邊界仍不完整：

- `Flet_ui/ui_components/unit` 不只放單位與 domain calculator，也放 UI 會直接呼叫的 facade。
- `analysis_modules` 不只是 UI adapter，還直接負責輸入轉換、計算呼叫與結果格式化。
- `Telegram_bot/thermo_calculator.py` 是另一個大型 domain／application／formatting 混合模組。
- `run.py` 為 Flet launcher，卻 import Telegram config 取得 logger／logging setup。
- Flet 的 composition root 有雛形，但 `AnalysisTab` 又在內部自行建立所有 analysis modules。

---

## 4. 檔案規模與責任概覽

### 4.1 Flet 目錄盤點

排除指定 model 後，`Flet_ui` 共盤點 29 個 Python 檔案。

| 檔案 | 行數 | 主要責任 | 評估 |
|---|---:|---|---|
| `Flet_ui/flet_app.py` | 81 | Flet bootstrap、service wiring、page layout | 尚可，但入口／logging 邊界需整理 |
| `Flet_ui/ui_components/analysis_tab.py` | 228 | module factory、registry、selection、dispatch、visibility | 多責任 |
| `Flet_ui/ui_components/property_tab.py` | 564 | property UI、validation、conversion、CoolProp、結果顯示 | 高風險多責任 |
| `analysis_modules/base_analysis_module.py` | 145 | UI base、service locator、unit sync、error display | 基礎邊界過寬 |
| `analysis_modules/hvac_compressor_module.py` | 928 | 11 個分析的 UI、輸入、轉換、計算、格式化 | 最高風險 hotspot |
| `analysis_modules/hvac_condenser_module.py` | 77 | condenser UI／calculation adapter | 與 evaporator 高度重複 |
| `analysis_modules/hvac_evaporator_module.py` | 72 | evaporator UI／calculation adapter | 與 condenser 高度重複 |
| `analysis_modules/psy_module.py` | 192 | psychrometric UI／calculation adapter | adapter 邊界需明確 |
| `analysis_modules/thermo_diagram_module.py` | 533 | chart UI、CoolProp、state parsing、render lifecycle | 高風險多責任 |
| `unit/HVACAnalyzer.py` | 91 | 多領域 calculation facade | 可保留相容層 |
| `unit/PropertyFormatter.py` | 119 | result formatting | 邊界相對清楚 |
| `unit/PsychrometricCalculator.py` | 104 | excluded model adapter、SI normalization | 有重複契約風險 |
| `unit/ThermoStateCalculator.py` | 196 | CoolProp property calculation、reference state | 應移往 domain service |
| `unit/UnitConverter.py` | 315 | unit registry、conversion map、轉換 API | 設定與邏輯混合 |
| `unit/hvac_calculations/common.py` | 221 | 共用 HVAC equations | 已有良好拆分基礎 |
| `unit/hvac_calculations/compressor.py` | 326 | compressor equations | domain 邊界可延續 |
| `unit/hvac_calculations/condenser_heat.py` | 274 | condenser equations | domain 邊界可延續 |
| `unit/hvac_calculations/exergy.py` | 86 | exergy equations | 相對集中 |
| `unit/hvac_calculations/heat_exchanger.py` | 23 | evaporator heat equation | 相對集中 |
| `unit/hvac_calculations/throttling.py` | 87 | throttling equations | 相對集中 |
| `unit/thermo_draw/coolprop_utils.py` | 443 | CoolProp、reference state、sampling、Matplotlib render | 高風險多責任 |

### 4.2 Telegram 與測試熱點

| 檔案 | 行數／狀態 | 主要責任 | 評估 |
|---|---:|---|---|
| `Telegram_bot/thermo_calculator.py` | 734 | property、unit、HVAC、psychrometric、formatting | 第二套大型 calculation core |
| `Telegram_bot/handlers/analysis_handler.py` | 約 438 | Telegram conversation、輸入狀態、計算、回覆 | adapter／application 混合 |
| `Telegram_bot/handlers/property_handler.py` | 約 300 | property conversation、calculator 呼叫、回覆 | 依賴 global calculator |
| `Telegram_bot/config.py` | — | env、logging、目錄與設定 side effect | 不應由 Flet launcher 擁有 |
| `tests/test_flet_compatibility.py` | — | Flet API／layout／entry regression | migration-focused |
| `tests/test_calculation_and_analysis_coverage.py` | — | Flet calculation／analysis coverage | 未涵蓋 Telegram |

---

## 5. Tier A：高優先架構問題

### A1. `CompressorModule` 是大型多責任物件

**嚴重度：🔴 高；信心：高**

檔案：

```text
Flet_ui/ui_components/analysis_modules/hvac_compressor_module.py
```

已驗證證據：

- class 約涵蓋第 18–928 行。
- constructor 建立多組 UI 與 unit synchronization（約第 38–58 行）。
- `get_analysis_definitions()` 註冊 11 個分析（約第 60–113 行）。
- 多個 `_build_*_ui()` method 建立輸入控制。
- `calculate_*()` method 直接讀取 Flet controls、轉換 unit、呼叫 analyzer、格式化結果。
- 第 858–908 行另有多組 hard-coded unit synchronization。

目前同一 class 同時涵蓋：

- 壓縮比
- 壓縮機功
- 等熵效率
- 冷凍能力／熱傳功
- 可逆功
- 㶲破壞
- 容積效率
- 㶲效率
- 綜合範例
- 多組 UI 建構與同步

**風險：** UI layout、輸入 key、unit semantics、calculation contract 與 output formatting 互相耦合。新增或修改一個共享欄位，可能影響多個不相關分析。

**建議邊界：**

```text
analysis/
├─ compressor/
│  ├─ compression_ratio.py
│  ├─ compressor_work.py
│  ├─ compressor_efficiency.py
│  ├─ compressor_exergy.py
│  └─ compressor_example.py
├─ schemas/
│  └─ compressor_inputs.py
└─ adapters/
   └─ compressor_flet_adapter.py
```

先抽出 input schema 與 pure calculation adapter，再拆 UI；不要直接用檔案大小做機械切割。

### A2. `PropertyTab` 同時是 View、Controller 與 calculation orchestrator

**嚴重度：🔴 高；信心：高**

檔案：

```text
Flet_ui/ui_components/property_tab.py
```

已驗證證據：

- 第 16–213 行主要建立 UI。
- `on_fluid_change()`（約第 232–273 行）同時驗證 fluid、修改 CoolProp reference state、改 UI error state 與更新頁面。
- `on_ref_state_change()`（約第 344–376 行）再次處理 reference state。
- 第 431–469 行自行實作 unit synchronization。
- `perform_calculation()`（約第 471–564 行）同時做輸入 parsing、validation、conversion、calculation、formatting、SnackBar error、progress 與 page update。
- 第 543–548 行有直接質量換算 literal factor，未完全委派給 `UnitConverter`。

**風險：** domain 行為只能透過 Flet controls 與 page state 測試，錯誤顯示與計算錯誤混在一起；Telegram 或其他入口無法自然重用。

**建議流程：**

```text
Flet controls
→ PropertyQueryRequest
→ PropertyQueryService
→ PropertyQueryResult
→ PropertyFormatter
→ Flet display
```

### A3. Flet 與 Telegram 維護兩套熱力學與單位核心

**嚴重度：🔴 高；信心：高**

Flet 端：

```text
Flet_ui/ui_components/unit/ThermoStateCalculator.py
Flet_ui/ui_components/unit/UnitConverter.py
Flet_ui/ui_components/unit/HVACAnalyzer.py
Flet_ui/ui_components/unit/PsychrometricCalculator.py
```

Telegram 端：

```text
Telegram_bot/thermo_calculator.py
```

已驗證證據：

- Flet 在 `flet_app.py` 建立 `UnitConverter`、`ThermoStateCalculator`、`HVACAnalyzer`、`PsychrometricCalculator`。
- Telegram 的 `ThermoCalculator` 在 `property_handler.py`／`analysis_handler.py` 以 module-global 方式建立。
- Telegram `thermo_calculator.py` 自己定義 property metadata、`conversion_map`、CoolProp calculation、HVAC calculation 與 output formatting。
- Flet 與 Telegram 沒有共用主要 calculation service。

**風險：** 同一物理輸入可能因入口不同而有不同 unit 支援、validation、exception、V／D 處理、kJ/kg／J/kg contract 或 output。

**建議：** 建立 UI-agnostic domain layer：

```text
domain/
├─ units/
│  ├─ property_codes.py
│  ├─ unit_registry.py
│  └─ converter.py
├─ thermodynamics/
│  ├─ state_service.py
│  ├─ property_models.py
│  └─ result_models.py
├─ hvac/
│  ├─ compressor.py
│  ├─ heat_exchangers.py
│  └─ exergy.py
└─ psychrometrics/
   └─ service.py
```

Flet／Telegram 僅保留 channel-specific input/output adapter。

### A4. Psychrometric adapter 在兩個 channel 重複

**嚴重度：🔴 高；信心：高**

排除 model 本身不在本 finding 範圍內；本 finding 只分析它外部的兩個使用邊界。

Flet：

```text
Flet_ui/ui_components/unit/PsychrometricCalculator.py
```

Telegram：

```text
Telegram_bot/thermo_calculator.py
```

已驗證證據：

- Flet adapter 將輸入轉為 SI，並將結果整理成 dict。
- Telegram 直接 import excluded model，另外組裝 Celsius／文字格式結果。
- 兩邊對輸入／輸出單位及 tuple shape 的解讀分散在不同程式路徑。

**風險：** excluded model 變更時需維護兩套 adapter；壓力、焓、RH、溫度語意可能逐步漂移。

**建議：** 不修改 excluded model，在其外部建立唯一：

```text
domain/psychrometrics/service.py
```

契約固定為 SI input 與 typed SI result；Flet／Telegram 各自負責顯示。

### A5. Thermodynamic chart 混合 UI、CoolProp、Matplotlib 與資料準備

**嚴重度：🔴 高；信心：高**

檔案：

```text
Flet_ui/ui_components/analysis_modules/thermo_diagram_module.py
Flet_ui/ui_components/unit/thermo_draw/coolprop_utils.py
```

`ThermoDiagramModule` 同時處理：

- Flet controls
- fluid validation
- comma-separated input parsing
- unit conversion
- CoolProp reference state
- state point dictionary
- chart rendering
- chart update
- user-facing error

`coolprop_utils.py` 同時處理：

- Matplotlib global state
- CoolProp query
- reference-state mutation
- saturation curve
- property sampling
- annotations、axis configuration、figure render

**風險：** 無法單獨測試 state-point preparation 或 chart data；載入／更新 Flet control 與 Matplotlib rendering 互相牽制；CoolProp process-global state 可能影響其他計算。

**建議拆分：**

```text
chart/
├─ state_point_parser.py
├─ saturation_data_service.py
├─ chart_data_builder.py
├─ matplotlib_renderer.py
└─ flet_chart_adapter.py
```

---

## 6. Tier B：中優先維護性問題

### B1. 三套以上 unit synchronization 邏輯並存

**嚴重度：🟡 中；信心：高**

已驗證位置：

- `base_analysis_module.py:95-138`
- `property_tab.py:431-469`
- `thermo_diagram_module.py:388-475`
- `hvac_compressor_module.py:858-908`

scalar、comma-separated vector、空值、old unit、invalid input、error handling 各自有不同路徑。

**建議：** 建立支援 scalar／vector 的 `UnitBinding`／`UnitGroup` abstraction；模組只提供 declarative configuration。

### B2. Evaporator 與 condenser adapter 高度重複

**嚴重度：🟡 中；信心：高**

檔案：

```text
hvac_evaporator_module.py
hvac_condenser_module.py
```

兩者皆建立三個輸入、執行相同的 read／convert／format／sync 流程，差異主要是 key、default、analyzer method 與 label。

**建議：** 使用 parameterized `HeatExchangerAnalysisModule` 或 declarative heat-exchanger spec。

### B3. Compressor exergy input pipeline 重複三次

**嚴重度：🟡 中；信心：高**

`hvac_compressor_module.py` 的 exergy destination、exergy efficiency loss、exergy efficiency ratio 都重複讀取與轉換：

- `T0`
- `h0`
- `s0`
- `h1`
- `h2`
- `s1`
- `s2`
- `m_dot`

**建議：** 建立 `ExergyInputSchema`、`extract_exergy_inputs()` 與 `convert_exergy_inputs_to_si()`。

### B4. CoolProp reference state 設定重複且具 process-global 狀態

**嚴重度：🟡 中至高；信心：高**

已驗證重複位置：

- `ThermoStateCalculator.set_coolprop_ref_state()`
- `coolprop_utils.safe_props()`
- `get_saturation_curve()`
- `generate_thermo_diagram()`

**風險：** 一個 UI flow 的 reference-state 設定可能影響後續其他計算；cache key 若沒有包含 reference state，也可能得到錯誤重用結果。

**建議：** 建立 `ReferenceStateService`，明確定義 request-local／global policy、cache key 及必要的 serialization。

### B5. `AnalysisTab` 同時是 registry、factory、view orchestrator 與 dispatcher

**嚴重度：🟡 中；信心：高**

已驗證位置：

- 第 30–42 行建立所有 module。
- 第 44–54 行建立 `analysis_map`。
- 第 129–137 行透過 `hasattr`／`callable` 找 optional behavior。
- 第 150–163 行管理 UI visibility。
- 第 166–172、200–204 行以 `PsyModule` 與 display-name prefix 特殊處理。

`"濕空氣性質"` 這類 display label 被用作 control flow，改名或 localization 可能改變程式行為。

**建議拆成：**

```text
AnalysisRegistry
AnalysisController
AnalysisView
AnalysisDefinition
```

每個 definition 使用穩定 ID 與 explicit mode，而不是 display name。

### B6. `BaseAnalysisModule` 是 service locator

**嚴重度：🟡 中；信心：高**

`base_analysis_module.py` 以 `**kwargs` 儲存任意 service，子類別再用字串 key 取值。

**風險：** 缺 dependency 或 typo 不會在初始化時失敗，而是延遲到按下 UI 操作才出錯。

**建議：** 使用 typed constructor dependency 或明確 service bundle。

### B7. `UnitConverter` 將 registry 與轉換演算法集中在一個 class

**嚴重度：🟡 中；信心：高**

檔案：

```text
Flet_ui/ui_components/unit/UnitConverter.py
```

`_build_conversion_map()` 約第 121–274 行同時維護 unit defaults、imperial defaults、ordering、conversion lambda、reverse inference 與 special temperature branches。

目前以 `convert_func(1.0) - convert_func(0.0)` 推估反向轉換，對 affine／nonlinear unit 的擴充不夠安全。

**建議：** 使用：

```text
UnitDefinition(
    property_code,
    unit_code,
    to_si,
    from_si,
    display_name,
    system,
)
```

初始化時驗證每個 unit 的雙向 contract。

### B8. Telegram transport helper 重複

**嚴重度：🟡 中；信心：高**

目前有：

```text
Telegram_bot/telegram_utils.py
telegeram_chatid.py
```

兩邊皆直接處理 Telegram HTTP、token、chat ID、parse mode 與 error handling，但設定來源與 response validation 不一致。

**建議：** 保留一個 transport service；`telegeram_chatid.py` 只做 CLI adapter。

### B9. Telegram handlers 以 module-global calculator 作為隱藏 service locator

**嚴重度：🟡 中；信心：高**

已驗證位置：

- `Telegram_bot/handlers/property_handler.py:9-11`
- `Telegram_bot/handlers/analysis_handler.py:9-15`

**風險：** import-time construction、測試難以注入 fake、handler lifecycle 與設定分散。

**建議：** 由 `create_application()` 建立 domain services，再明確注入 handlers。

---

## 7. Tier C：低優先整理事項

### C1. Flet 有兩個啟動契約

**嚴重度：🟢 至 🟡**

- `run.py` 是主要 launcher。
- `Flet_ui/flet_app.py:80-81` 也直接呼叫 `ft.run(main)`。

建議選定一個正式 entrypoint；另一個若保留，應成為明確且有測試的 wrapper。

### C2. Flet launcher 依賴 Telegram config side effect

**嚴重度：🟢 至 🟡**

`run.py` 只為 logger／logging setup import `Telegram_bot.config`，但該模組會載入 `.env`、建立 log directory 並初始化 logging。

建議將共用 logging／infrastructure 移到中立模組，避免 Flet 啟動依賴 Telegram-owned config。

### C3. Telegram 缺少清楚的 executable entrypoint

**嚴重度：🟢 至 🟡**

`Telegram_bot/bot_application.py` 有 `start_bot()`，但：

- 沒有 `if __name__ == "__main__"`。
- `pyproject.toml` 沒有 `project.scripts`。
- `run.py` 不會啟動 Bot。
- packaging script 卻以 Flet + Telegram 描述輸出。

應明確定義 Bot 是獨立 executable，或明確文件化為 library-only。

### C4. Packaging scripts scope 不一致且重複

**嚴重度：🟢 至 🟡**

檔案：

```text
packae_file.bat
packae_file2.bat
```

問題：

- 兩份 packaging logic 高度重複。
- 都宣稱 Flet + Telegram，但 root executable 是 `run.py`。
- `packae_file2.bat` 在 packaging 期間執行 `uv add sccache`，會產生 dependency metadata side effect。
- 兩份都使用 `uv sync --all-extras`，但 `pyproject.toml` 沒有 optional-dependencies。

建議改為明確的單一 build script，或拆成 `build-flet`／`build-telegram` 兩個明確 target；build 不應修改 dependency metadata。

### C5. 測試目前主要覆蓋 Flet migration surface

**嚴重度：🟡 中；信心：高**

現有 12 tests 主要驗證 Flet compatibility、calculation 與 analysis options。尚未涵蓋：

- Telegram handlers 與 conversation state transitions
- Telegram config／logging
- outbound Telegram requests
- `bot_application.create_application()`
- `telegeram_chatid.py`
- packaging script contract
- packaged executable behavior
- direct `Flet_ui.flet_app` entrypoint

建議拆成 domain、Flet adapter、Telegram adapter、integration、packaging smoke 五層。

### C6. `ANALYSIS.md` 混合歷史與 current state

**嚴重度：🟢 低**

同一文件包含 migration 前失敗狀態、修復過程與目前結果。雖然部分段落標示歷史，但開頭與早期結論仍容易被誤讀成目前狀態。

另外 `pyproject.toml` 宣告 `readme = "README.md"`，但目前 repository 缺少對應 README。

建議拆成：

```text
docs/
├─ architecture.md
├─ migration-history.md
├─ testing.md
└─ packaging.md
```

### C7. Metadata 與命名未完成

**嚴重度：🟢 低**

已確認：

- `pyproject.toml:4` 仍為 `description = "Add your description here"`。
- `packae_file.bat`、`packae_file2.bat` 疑似 typo。
- `telegeram_chatid.py` 的 `telegram` 拼字錯誤。

目前不一定直接造成 runtime failure，但降低 discoverability 與維護品質。

---

## 8. 目前做得好的架構基礎

### 8.1 沒有 import cycle

GitNexus structural check 實測：

```text
cycleCount: 0
componentCount: 0
```

因此目前主要問題是責任分層、重複 domain logic 與依賴注入，不是循環依賴。

### 8.2 Flet composition root 已有雛形

`flet_app.py` 已集中建立部分 shared services：

- `UnitConverter`
- `ThermoStateCalculator`
- `PropertyFormatter`
- `HVACAnalyzer`
- `PsychrometricCalculator`

這個方向應保留並延伸到 Telegram；目前的缺口是 `AnalysisTab` 又自行建立 modules，Telegram handlers 也在 import time 建 calculator。

### 8.3 HVAC pure calculation 已部分拆出

以下目錄已具備可延續的 domain extraction 基礎：

```text
Flet_ui/ui_components/unit/hvac_calculations/
├─ common.py
├─ compressor.py
├─ condenser_heat.py
├─ exergy.py
├─ heat_exchanger.py
└─ throttling.py
```

不需要從零重寫，應先建立穩定的 SI contract，再逐步讓 Telegram 共用。

### 8.4 Analysis module 已有 registry 雛形

`get_analysis_definitions()` 與 `analysis_map` 已形成 plugin-like registry 的雛形。建議把現有 dict metadata 正式化為 typed `AnalysisDefinition`，而非全部推翻。

---

## 9. 建議目標架構

```text
domain/
├─ units/
│  ├─ property_codes.py
│  ├─ unit_registry.py
│  └─ converter.py
│
├─ thermodynamics/
│  ├─ state_service.py
│  ├─ property_models.py
│  └─ result_models.py
│
├─ hvac/
│  ├─ compressor.py
│  ├─ heat_exchangers.py
│  ├─ exergy.py
│  └─ throttling.py
│
└─ psychrometrics/
   └─ service.py

application/
├─ property_queries.py
├─ analysis_catalog.py
└─ analysis_services.py

adapters/
├─ flet/
│  ├─ property_tab.py
│  ├─ analysis_tab.py
│  ├─ analysis_modules/
│  └─ chart_view.py
│
└─ telegram/
   ├─ property_handlers.py
   ├─ analysis_handlers.py
   ├─ telegram_formatters.py
   └─ transport.py

bootstrap/
├─ flet_main.py
└─ telegram_main.py
```

### 9.1 依賴方向

```text
Flet adapter ───────┐
                    ├─> application services ──> domain
Telegram adapter ───┘

bootstrap ──> adapters + application + domain

domain 不應 import Flet、Telegram、Matplotlib UI control 或 handler state。
```

### 9.2 主要 contract

#### Unit contract

- domain calculation 接受 canonical SI quantity。
- display unit conversion 只出現在 adapter／formatter。
- 每個 unit 明確提供 `to_si` 與 `from_si`。
- 不以 runtime probing 推導 affine／nonlinear unit 的 inverse。

#### Thermodynamic contract

```text
PropertyQueryRequest
→ ThermodynamicStateService
→ PropertyQueryResult
```

request／result 不應包含 Flet control、Telegram message 或 display string。

#### HVAC contract

- pure functions 或 typed service 接受 SI quantity。
- output 使用明確的 physical quantity 名稱。
- kW、kJ/kg 等 display unit 不應由 caller 以 magic `/1000` 或 `*1000` 處理。

#### Psychrometric contract

- 以一個 adapter 包住 excluded model。
- input／output contract 固定且文件化。
- Flet／Telegram 不直接解讀 model tuple shape。

---

## 10. 分階段重構路線

### Phase 0：建立現況基線

目標：不改行為，先鎖定目前 contract。

- 補 domain-level characterization tests。
- 建立 Flet／Telegram 對同一 inputs 的 parity fixtures。
- 記錄 unit、reference state、exception 與 output formatting 的差異。
- 確認 excluded model 的實際輸入／輸出 contract，但不修改它。

驗收：既有 `12 passed` 維持綠燈；新增測試能證明目前差異，而不是假設兩邊已相同。

### Phase 1：建立 canonical units 與 SI contract

範圍：

- Flet `UnitConverter`
- Telegram `conversion_map`
- property codes、unit registry、temperature／specific volume 等特殊規則

驗收：

- 每個公開 unit 有雙向測試。
- invalid unit／invalid numeric input 有明確錯誤。
- Flet 與 Telegram adapter 可共同呼叫 converter。

### Phase 2：建立共用 thermodynamic state service

範圍：

- Flet `ThermoStateCalculator`
- Telegram `ThermoCalculator` 的 property calculation 部分
- reference-state policy

驗收：

- property result 為 neutral model。
- 測試不需建立 Flet page 或 Telegram bot。
- Flet／Telegram 僅負責 request parsing 與 display formatting。

### Phase 3：合併 HVAC pure formulas

範圍：

- Flet `hvac_calculations/*`
- Telegram `ThermoCalculator` 的 compressor／heat exchanger／exergy methods
- `HVACAnalyzer` 先保留 compatibility facade

驗收：

- 每個公式有 boundary tests。
- 對單位 contract 有明確 assertion。
- Telegram 的重複公式改為呼叫共用 domain function。

### Phase 4：統一 Psychrometric adapter

範圍：

- 新增唯一的 `PsychrometricService`。
- Flet `PsychrometricCalculator` 改為薄 adapter。
- Telegram 改為透過 service，不直接解讀 excluded model。

驗收：

- Flet／Telegram 使用相同 neutral result。
- 不修改 excluded model。
- 加入輸入單位與結果單位 regression tests。

### Phase 5：整理 application services 與 composition roots

範圍：

- `PropertyQueryService`
- `AnalysisRegistry`／`AnalysisDefinition`
- Flet／Telegram explicit dependency injection
- 移除 module-global calculators

驗收：

- import 不再建立 calculator instance。
- 缺 dependency 在 construction time 失敗，而非 UI click 後才失敗。
- application service 可在 headless test 呼叫。

### Phase 6：拆大型 Flet UI modules

建議順序：

1. `PropertyTab`
2. `hvac_compressor_module.py`
3. `thermo_diagram_module.py`
4. `AnalysisTab`

拆分原則：

- 先保留既有 UI behavior。
- 每次只抽一個 contract。
- UI event handler 只做 bind／request／render。
- 新增 helper 若沒有實際 caller，不要保留 dead code。

### Phase 7：整理 chart pipeline

拆分：

- state point parser
- CoolProp sampling
- chart data model
- Matplotlib renderer
- Flet chart adapter

驗收：

- chart data 可在無 Flet UI 下測試。
- renderer error 不會直接污染 domain result。
- page 未掛載時不會呼叫不安全的 control update。

### Phase 8：整理 entrypoint、packaging、docs

- 明確 Flet／Telegram executable scope。
- 合併或重新命名 batch packaging scripts。
- 移除 build-time dependency mutation。
- 補齊 README 或修正 `pyproject.toml` metadata。
- 將 migration history 與 current architecture 分開。

---

## 11. 測試與安全重構策略

### 11.1 測試分層

```text
tests/
├─ domain/
│  ├─ test_units.py
│  ├─ test_thermodynamics.py
│  ├─ test_hvac.py
│  └─ test_psychrometrics.py
│
├─ adapters/
│  ├─ test_flet_property_tab.py
│  ├─ test_flet_analysis_tab.py
│  └─ test_telegram_handlers.py
│
├─ integration/
│  ├─ test_flet_startup.py
│  └─ test_telegram_application.py
│
└─ packaging/
   └─ test_build_contracts.py
```

### 11.2 每個行為重構的必要驗證

1. 先保留既有 test baseline。
2. 對純 calculation 抽出 pure function 後補 boundary tests。
3. 對已知 bug 補「bug 版會紅、修復版會綠」的 regression test。
4. 對 Flet lifecycle 保留 headless unit tests，另增加有限的 runtime smoke test。
5. Telegram HTTP 一律 mock transport，不使用真實 token 做一般測試。
6. 每階段執行 focused tests，再依修改範圍執行完整 suite。
7. 執行 `compileall`、`uv lock --check`、`uv pip check` 與 `git diff --check`。
8. 變更後檢查 import、entrypoint、script registration 與 docs contract 是否同步。

### 11.3 安全與資料邊界

未來抽 application service 時，應保留：

- 使用者輸入數量／字串／日期格式的明確驗證。
- 非法輸入回傳可預期的 validation error，而不是讓 UI 或 bot 產生 500。
- Telegram token、API key、password、connection string 不寫入報告、測試 fixture 或 log。
- 外部 HTTP transport 與 domain calculation 分離，方便 mock、timeout 與錯誤分類。

---

## 12. 不應立即修改的部分

### 12.1 不要直接機械切割大型檔案

先建立 input／output／unit contract，再拆檔。否則只是把相同耦合搬到更多檔案。

### 12.2 不要直接刪除 Telegram calculator

它目前是第二套實際 calculation path。應先做 parity／characterization tests，再逐步改為共用 domain service。

### 12.3 不要直接修改 excluded Psychrometric model

本輪範圍明確排除該檔案；應只建立外部 adapter 與 contract。

### 12.4 不要繼續擴充 display-name dispatch

不要再增加 `startswith()` 或中文 label 判斷。應先引入穩定 analysis ID 與 explicit metadata。

### 12.5 不要把所有轉換 lambda 搬到另一個大檔

那只是位置改變，不是架構改善。應使用可驗證的 `UnitDefinition` registry。

### 12.6 不要在沒有測試的情況下先改 reference-state policy

CoolProp reference state 具 process-global 特性，任何 policy 改變都應先有 characterization tests 與跨功能驗證。

---

## 13. 已知限制與未驗證項目

1. 本報告是靜態架構與既有測試基準分析，不是完整 production load／concurrency audit。
2. GitNexus 已確認目前 import-cycle check 為零，但 dynamic dispatch、runtime import 或外部 packaging 行為不能只靠 import graph 證明不存在所有循環。
3. 本報告沒有使用真實 Telegram token 執行外部 integration test。
4. packaging batch scripts 未進行完整產物啟動矩陣驗證；本報告只分析 script scope 與可見依賴。
5. excluded Psychrometric model 本身未分析；本報告只記錄其外部 callers／adapters。
6. Flet headless tests 使用 hand-written page doubles；它們不能完全取代實際 Flet runtime smoke test。
7. 行數是風險訊號，不是單獨的架構錯誤判定；本報告的高嚴重度 finding 同時有責任混合、耦合、重複或測試邊界證據。
8. 報告中的目標目錄與 class 名稱是建議設計，尚未建立，不應被視為已存在的程式碼。

---

## 14. 最終結論

這個專案目前最重要的架構債是：

> 相同 domain 邏輯分散在 Flet 與 Telegram 兩套實作，而 UI class 又直接承擔大量 application／domain 責任。

最安全且最有價值的改善順序是：

1. 先固定 canonical units 與 SI contracts。
2. 再建立共用 thermodynamic state service。
3. 再合併 HVAC pure functions。
4. 再統一 Psychrometric adapter。
5. 再建立明確的 application services 與 composition roots。
6. 最後拆 `PropertyTab`、`CompressorModule`、`ThermoDiagramModule` 與 `AnalysisTab`。

目前沒有 import cycle 是好的基礎；`hvac_calculations` 與 Flet service wiring 也提供了可延續的方向。重構時不應追求把每個檔案平均變小，而應讓每個模組只因一類變更而需要修改，並讓 domain calculation 能在沒有 Flet page 或 Telegram message 的情況下獨立測試。

**本報告結論：建議先做 domain contract／測試基線，不建議直接進行大型 UI 拆檔。**
