# 架構

## 1. 系統概覽

應用程式包含兩個通道介面、中立的應用程式層、共用的領域服務，以及供舊版整合使用的基礎設施轉接器。

```text
Flet adapter -----------┐
                         ├──> application/ ───> domain/
Telegram adapter -------┘

組合根會建立 channel/application/domain services，並注入 infrastructure implementations；application 與 domain code 不會自行尋找 infrastructure。
chart/ 提供 chart adapter 使用的 headless chart state model 與 parser。
```

## 2. 相依方向

合法的方向如下：

```text
channel adapters / entrypoints
              ↓
       application services
              ↓
        domain services
```

基礎設施轉接器是在組合根注入的具體實作。`domain/` 與 `application/` 不得匯入通道套件或通道呈現型別。

## 3. 分層職責

### `domain/`

負責規範性的物理量、單位定義、熱力學計算、HVAC 方程式、濕空氣中立結果模型，以及程序全域的參考狀態政策。它不知道 Flet 控制項、Telegram 更新或顯示格式。

`domain/refrigeration/` 負責蒸氣壓縮循環、飽和性質、過熱度／過冷度判讀與冷凝器能量／熵／㶲平衡，透過 `ThermodynamicStateProvider` 協定取得 canonical SI 狀態；`domain/psychrometrics/processes.py` 負責空氣處理過程的質量／能量平衡。`domain/state_points/` 定義跨工具共用的 `ThermoStatePoint`／`AirStatePoint`、基準防護與序列化（契約見 `docs/domain-contracts.md` §10）；`domain/schema.py` 提供可保存文件共用的 schema 種類與版本檢查。

### `application/`

負責請求模型與 `PropertyQueryService`、`AirProcessService`（空氣處理過程）、`RefrigerationService`（冷凍循環、飽和性質、過熱度判讀與其 reference-state policy）等協調工作。它驗證請求形狀並協調領域服務。不負責呈現控制項或訊息。

`application/settings.py` 定義工作區基礎設定 `WorkspaceSettings`（預設冷媒、預設 Reference State、單位系統、大氣壓力／海拔、錶壓／絕對壓預設）與 `SettingsService`。保存透過 `DocumentStore` protocol，由組合根注入具體實作；application 不直接存取檔案系統。已保存的設定無效或版本不符時明確失敗，不以預設值覆蓋使用者的檔案。`application/state_library.py` 的 `StateLibraryService` 同樣透過 `DocumentStore` 保存使用者的狀態點（契約見 `docs/domain-contracts.md` §11）。

### `infrastructure/`

負責不屬於領域契約的具體整合。被排除的舊版濕空氣實作會在此透過 `LegacyPsychrometricModelAdapter` 存取。

`infrastructure/storage/JsonDocumentStore` 是 `DocumentStore` 的 JSON 檔實作：每份文件存成 `<name>.json`，名稱只允許小寫英數、底線與連字號；寫入先寫暫存檔再原子替換；讀寫都只接受標準 JSON，拒絕 NaN／Infinity，錯誤一律以 `ValueError` 回報。`infrastructure/storage/workspace.workspace_directory()` 回傳使用者工作區資料夾：預設為家目錄下的 `.hvac_workspace`，可由環境變數 `HVAC_WORKSPACE_DIR` 改用其他資料夾（測試由 `tests/conftest.py` 指向暫存資料夾，不寫入真正的家目錄）。`domain/` 與 `application/` 不得匯入 `infrastructure/`（由 `tests/test_settings_storage.py` 檢查）。

### `Flet_ui/`

負責控制項、Flet 輸入的解析、轉接格式化與 UI 生命週期。`PropertyTab` 跨越物性查詢的應用程式邊界，而不是自行實作熱力學政策。

### `Telegram_bot/`

負責 Telegram 處理器、回應格式化，以及舊版 Telegram 行為的相容性外觀。呼叫共用熱力學服務時，會使用明確的參考狀態政策。

### `chart/`

負責無頭圖表狀態模型與解析。現有的圖表呈現與取樣仍屬於通道／基礎設施職責。

`chart/psychrometric.py` 以 `PsychrometricService` 取樣濕空氣線圖的飽和線、等相對濕度線與等焓線，只產生曲線資料。

### 進入點

`run.py` 以中立的記錄設定組合並啟動 Flet 應用程式。Telegram 有自己的 bot 進入點與設定邊界。目前 repository 中沒有獨立的 `bootstrap/` 套件。

## 4. 組合根

組合根建立通道轉接器並注入共用服務。組合根可以選擇通道政策、轉接器實作或格式化器，但領域程式碼不得透過向上匯入來自行發現這些實作。

## 5. 熱力學邊界

`ThermodynamicStateService` 在轉接器邊界接受顯示單位中的已知物性，將其轉換為 canonical SI，執行 CoolProp 或理想氣體計算，並回傳中立的數值結果。相容性外觀可以保留通道專用行為，但在契約已完成整合的地方，必須將 canonical quantities 委派給共用服務。

核心熱力性質的單位換算以 `domain.units.CanonicalUnitConverter` 為準；各通道的換算器（例如 Flet 的 `UnitConverter`）只負責顯示單位，核心性質必須委派給它，並對未註冊的性質或單位明確報錯。錶壓力等通道專屬語意在通道層換成絕對 SI 後才進入 application／domain（見 `docs/domain-contracts.md`）。

## 6. HVAC 邊界

共用的 HVAC 方程式位於 `domain/hvac/` 下，使用 canonical SI 輸入與輸出。Flet 與 Telegram 模組在該邊界周圍轉換通道值與呈現方式；不得為共用公式引入第二套實作。

## 7. 濕空氣邊界

`domain.psychrometrics.service.PsychrometricService` 使用注入的中立協定，並回傳數值結果。被排除的舊版模型 `Flet_ui/PsychrometricChart/PsychrometricChart_01_ASHF_model.py` 只有基礎設施轉接器會匯入。其內部實作位於一般領域重構邊界之外，不是領域相依項目。

## 8. 圖表邊界

`chart/` 提供無頭狀態點模型與解析。圖表轉接器可以使用 Flet 或 Matplotlib 進行呈現，但圖表呈現細節不得洩漏到領域計算。依賴參考狀態的圖表查詢使用共用的 CoolProp 同步機制。

## 9. 參考狀態所有權

CoolProp 參考狀態是程序全域的。`ReferenceStateService` 負責：

- 程序層級的同步原語；
- 受控的參考狀態變更；
- 共用的觀察狀態登錄表；
- `ReferenceStatePolicy` 詞彙。

變更與完整的相依 `PropsSI`／`PhaseSI` 交易會在同一個共用的 `calculation_scope` 中執行。同步與請求政策是不同的概念：應用程式服務負責一個使用者流程所要求的政策，而 `ReferenceStateService.current()` 只回報觀察到的程序狀態。一般進入點會選擇具體的政策（`DEF`、`ASHRAE`、`IIR`、`NBP`），只有明確標示為內部的操作可以使用 `CURRENT`。一般請求不會繼承前一個請求留下的狀態。

## 10. 分析註冊

每個分析定義都擁有穩定且具語意的 `analysis_id`。`definitions_from_module()` 會驗證並轉成 `AnalysisDefinition`、拒絕缺少或同一模組內重複的 ID；`AnalysisModuleAdapter` 再拒絕跨模組重複的 ID，並只以這些 ID 控制流程。顯示標籤、在地化名稱、清單位置，以及類別名稱加位置都不是識別身分。

## 11. 架構不變量

- `domain/` 不匯入 `Flet_ui`、`Telegram_bot`、`flet` 或 `telegram`。
- `application/` 不依賴 Flet 控制項、Telegram 更新／內容物件或通道呈現。
- UI 與處理器不負責 canonical unit rules、HVAC equations、thermodynamic formulas 或 reference-state mutation。
- 直接的 `CP.set_reference_state(...)` 只存在於 `domain/thermodynamics/reference_state.py`。
- 依賴參考狀態的 CoolProp 查詢使用共用的同步邊界。
- 被排除的濕空氣模型只能透過基礎設施存取。
- 分析控制流程使用具語意的 `analysis_id` 值。
- 相容性行為隔離於轉接器邊界，並有文件與測試覆蓋。

## 12. 防護機制

架構防護測試會掃描正式程式碼的匯入與直接的 CoolProp 變更。回歸測試覆蓋穩定的分析註冊、明確的單位錯誤、參考狀態交易隔離、跨實例狀態所有權，以及應用程式／UI 服務邊界。

領域契約定義於 [`domain-contracts.md`](domain-contracts.md)。已接受的暫時性行為邊界定義於 [`compatibility-boundaries.md`](compatibility-boundaries.md)。維護與驗證規則定義於 [`maintenance.md`](maintenance.md) 與 [`testing.md`](testing.md)。
