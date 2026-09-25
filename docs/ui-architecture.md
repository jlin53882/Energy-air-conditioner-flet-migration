# HVAC 工作區 UI 架構

## 用途與事實界線

本文記錄 Flet 工程工作區預期遵守的 UI 架構契約。可執行程式碼代表目前實際行為；本文記錄預期契約。兩者若不一致，即屬架構偏移，必須調查並修正，不可默默選擇其中一方當作正確答案。

目前遷移保留既有熱力學與 HVAC 計算服務及其應用程式／領域邊界。畫面可以收集、驗證輸入，透過轉接器呼叫既有服務並呈現其回傳值，但不得在畫面層重寫熱力方程式。

## 應用程式外殼

`Flet_ui/flet_app.py` 是組合根，負責建立既有服務，並掛載 `Flet_ui/ui/app_shell.py`。

`AppShell` 負責三個區域：

- **頂端列**：左側品牌區（導覽收合按鈕、標誌與名稱）；右側為「分類 › 路由」麵包屑、快捷鍵提示及全域結果輸出單位偏好。
- **側邊欄**：淺色、以穩定路由鍵值識別的分組導覽，不以翻譯後的顯示文字作為路由識別。寬版可由頂端列按鈕收合為圖示列（`AppShell.sidebar_collapsed`），讓計算頁取得更多寬度。選取樣式由 `Sidebar.set_selected()` 負責，外殼不得直接改寫導覽項目的內部控制項。
- **工作區**：頁首（路由圖示、路由標題與 `WorkspaceRoute.description`）及目前選取的畫面。

原本的右側情境面板已移除：常用冷媒捷徑移到首頁的「常用冷媒」卡片，快捷鍵提示位於頂端列。畫面不得顯示假造的計算歷史；歷史紀錄的存放方式決定前，不提供歷史入口。

外殼會將每個唯一畫面固定掛載於同一個 `Stack`，切換路由時只改變可見狀態。這可避免圖表等昂貴子控制項在導覽時被銷毀重建，並減少 Flet 控制項生命週期變動。PR #4（Analysis Workspace Migration）之後，每個分析路由對應各自獨立的 dedicated view 實例（`CompressorView` / `EvaporatorView` / `CondenserView` / `RefrigerationCycleView` / `PsychrometricsView` / `AirProcessView` / `PsychrometricChartView` / `ThermoDiagramView`），彼此互不共享父容器；`AppShell` 不需要知道任何 analysis category 的細節，只依 `route.key` 決定要顯示哪一個已掛載的 view。

## 導覽契約

`Flet_ui/ui/navigation.py` 定義語意路由識別碼與顯示文字。目前註冊的路由包括首頁、熱力狀態查詢、壓縮機、蒸發器、冷凝器、冷凍循環、濕空氣性質、空氣處理程序、P-h 圖、T-s 圖、濕空氣線圖及單位換算。每個分析路由都對應一個 dedicated view 及其註冊的分析定義。新增路由必須代表已實作工具，或明確標示為不可使用；規劃中的項目不得呈現得像可執行功能。

路由身分是資料（`route.key`），與顯示文字彼此獨立。導覽狀態由 `WorkspaceState` 保存，不得依賴標籤文字或 Flet 選取索引。`WorkspaceRoute.description` 只供頁首與首頁卡片顯示，不參與路由判斷。

## 設計權杖與共用元件

`Flet_ui/ui/theme.py` 集中管理間距、圓角、控制項尺寸、寬度建議、色彩、字體層級，以及共用的欄位、按鈕、膠囊按鈕、卡片陰影與等寬數字樣式（`style_text_field`、`style_dropdown`、`primary_button_style`、`secondary_button_style`、`chip_button_style`、`card_shadow`、`mono_style`）。配色為暖灰白底（`background`）、白色卡片細框線，搭配單一深青綠強調色（`primary`），圖表的目前狀態點使用 `highlight` 橘紅色；不再依導覽分類使用不同強調色。數值（關鍵數值、性質表、輸入欄位、公式與原始文字）一律使用 `TOKENS.mono_font`（IBM Plex Mono），由組合根以 `page.fonts` 從 `MONO_FONT_URL` 註冊；無法下載字型時由系統字型替代，不影響功能。新增工作區畫面應重用這些設計權杖與樣式函式，不應在各畫面另行建立局部色盤或間距常數。樣式函式只改變外觀，不得改變控制項的值或事件。

`Flet_ui/ui/components/` 目前提供：

- `EngineeringCard`：共用的卡片底面、陰影與標題分組，可加上圖示底座與標題列右側操作。
- `QuantityInput`：語意上合併數值與單位的輸入元件，可在逐步遷移舊表單時沿用既有控制項。
- `ResultPanel`：以狀態橫幅明確呈現空白、載入中、成功、警告與錯誤狀態；指標卡只呈現計算轉接器實際提供的數值，中繼資料以標籤呈現。指標鍵值維持英文識別字，中文標籤與圖示只屬於呈現層。
- `MetricTile`：單一結果的標籤、主數值與單位；只拆分既有格式化文字的開頭數字與單位，不重新計算。
- `StatusBadge`：以圖示、文字與色彩同時表達狀態的膠囊標籤。
- `structured_result`（`Flet_ui/ui/structured_result.py`，不依賴 Flet）：`StructuredResult` 資料類別，以及把分析模組回傳的「名稱: 數值 單位」文字與 `--- 分組 ---` 標題轉成結構化結果的 `structured_from_text()`；只重新排版、不改寫數值，無法配對的文字保留為說明列。
- `KpiTile`、`PropertyTable`、`AnalysisResultView`：計算頁結果區的關鍵數值卡、分組性質表與整體結果版面。
- `Sidebar`：帶有分組、選取指示、精簡圖示列與工具提示的路由控制項。

`Flet_ui/ui/analysis_presentation.py` 以穩定 `analysis_id` 為鍵，提供分析項目的短標籤、說明與公式提示。此表只屬於呈現層，不得放入計算；公式文字必須與實際服務行為一致，實作與命名不一致的項目只保留文字說明。新增分析時應同步新增說明，測試會檢查註冊表與說明表的一致性。

輸入控制項包裝器負責畫面呈現及欄位層級驗證。單位換算由既有 `UnitConverter` 或領域／應用程式轉接器負責；畫面不得複製一套換算公式。

共用分析輸入列會將數值欄名及單位欄名分別顯示在 `TextField` 與 `Dropdown` 上方。不得把欄名塞進外框控制項，避免壓縮機、蒸發器、冷凝器及其他分析表單發生文字與外框碰撞。一般分析欄名描述量的意義，切換單位時保持不變；熱力圖欄名則刻意包含單位並隨單位更新。所有情況下，單位下拉選單的目前選取值才是該控制項單位的唯一來源。

## 畫面職責與遷移界線

- 首頁以橫幅、工具卡片格、建議工作流程與常用冷媒捷徑（點選即以該流體開啟狀態查詢）呈現已實作工具。卡片上的分析數量與總數只來自各 dedicated view 的 `AnalysisModuleAdapter.definitions`，不得寫死或推估。
- 性質查詢工作區將既有的模式、流體、參考狀態及性質控制項組合成全寬計算設定卡，下方左欄為已知條件與選用廣延性質、右欄為結果；窄視窗時依序堆疊。水模式的理想氣體選項必須實際出現在計算設定卡中。常用組合以膠囊按鈕呈現，並標示與前兩列性質相符的組合。
- 分析頁共用 `AnalysisWorkspace` 計算頁版型：左欄「輸入條件」卡（`ToolSelector` 分析項目下拉選單，只有一項分析時隱藏；分析名稱、說明與公式提示；模組輸入；全寬「計算」按鈕），右欄為 `AnalysisResultView` 結果區（關鍵數值列、圖表＋完整性質表、可展開的「顯示計算過程」、原始文字與複製）。欄寬固定為 `INPUT_COLUMN`／`RESULT_COLUMN`，窄視窗時上下堆疊。尚未計算或計算失敗時，結果區只顯示狀態卡；成功時狀態卡隱藏，由數值本身呈現結果。頁面標題與說明由 AppShell 頁首呈現，`AnalysisWorkspace.header` 預設隱藏。`AnalysisModuleAdapter` 保存模組回傳的原始 `result_text`；以「計算錯誤」或「計算失敗」開頭的文字以錯誤狀態呈現，不投影指標。
- 分析定義可選擇提供 `result_chart`（`PsychrometricChartPanel` 或 `FigurePanel`），由 `definitions_from_module()` 帶入 `AnalysisDefinition.result_chart`；成功計算後顯示在結果區的圖表卡，寬版時與完整性質表並排，重設、切換工具或錯誤時隱藏，且不得沿用前一個分析的圖表。濕空氣線圖（濕空氣性質、空氣處理程序、濕空氣線圖路由）使用 `PsychrometricChartPanel`：以 Flet 原生折線圖（`flet_charts.LineChart`）繪製飽和線、等相對濕度線、等焓虛線、過程線與狀態點，濕空氣性質另以橘紅虛線連到濕球溫度與露點（終點為空心點）；文字由介面繪製，不依賴系統中文字型，圖表不回應滑鼠（背景參考線橫跨整張圖，套件的滑鼠指示會在每條線上各標一點，並使標註點提示框無法顯示），讀值改為直接標在圖上：`LineChart.on_size_change` 回報繪圖尺寸後，`layout_labels()` 在疊加於圖表上的 `Stack` 中依重要性放置狀態點名稱、濕球／露點讀值、飽和線與等相對濕度線的百分比（線的末端）以及等焓線數值（靠飽和線一端），先估算文字範圍，依序嘗試候選位置、取第一個不重疊者：狀態點與濕球／露點是必要標籤，重疊時改放右上、左下等其他位置，全部重疊時仍放在首選位置，不會消失；曲線數值是次要標籤，重疊時略過；標註點的完整座標（乾球溫度、濕度比）另列在圖下方的圖例。P-h／T-s 圖需要對數座標，仍使用 `FigurePanel`（長期存在的 Matplotlib figure，繪圖程式必須清除並重畫同一個 figure，再呼叫 `refresh()`）。
- 分析定義可提供 `structured_result`：無參數函式，回傳最近一次成功計算的 `StructuredResult`（`Flet_ui/ui/structured_result.py`：`key_metrics` 關鍵數值、`groups` 完整性質表、`process_groups` 計算過程、圖表標題與圖例）。資料類別只存放已格式化的文字，不依賴 Flet；結果區只負責排版，不重新計算或換算。目前只有 `PsyModule`（濕空氣性質兩種模式）提供原生 `structured_result`；其他分析（壓縮機、蒸發器、冷凝器含 Exergy、冷凍循環、空氣處理、濕空氣線圖）未提供時由 `structured_from_text()` 轉換模組的格式化文字。`structured_from_text()` 只供顯示：它讀取的是已四捨五入、已換成輸出單位的文字，不得作為狀態點、批次計算或任何後續計算的資料來源；需要數值的功能必須改由 domain／application 服務的結構化結果取得。轉換規則：關鍵數值依 `analysis_presentation` 中該分析宣告的 `key_metrics`（結果名稱，依序挑選、找不到的略過；未宣告時取前四個）挑選，完整性質表列出全部結果（所有結果都已是關鍵數值時省略），圖表卡標題取自 `chart_title`。新增分析時應在說明表宣告 `key_metrics`，測試會檢查宣告的名稱確實出現在預設輸入的計算結果中。濕空氣性質的兩種模式由 `PsychrometricResultBuilder` 產生：四個關鍵數值（RH、露點、焓、濕度比）、帶濕球／露點輔助線的焓濕圖、分成「輸入值／計算結果」的完整性質表，以及飽和壓力、飽和濕度比等中間值；海拔欄位下方即時顯示推算的大氣壓力。結構化結果與文字結果必須來自同一份服務回傳的狀態。
- 分析模組的數值輸入列（`BaseAnalysisModule.create_input_row`）為「欄名在上、數值與單位合成同一外框」：單位選單位於欄位尾端，仍可逐欄切換；聚焦時外框以主要色加粗標示。
- 空氣處理程序路由（`AirProcessView` + `PsyProcessModule`）：氣流混合、顯熱加熱／冷卻、冷卻除濕盤管與送風量估算，計算委派給 `AirProcessService`，過程標示在濕空氣線圖上。濕空氣性質路由（`PsychrometricsView`）維持原本的兩種模式。
- 冷凍循環路由（`RefrigerationCycleView` + `RefrigerationCycleModule`）提供蒸氣壓縮循環（P-h 圖沿用 `generate_thermo_diagram`，並使用循環結果 `reference_state` 攜帶的、求解時實際使用的 policy，不重新解析 Auto）及過熱度／過冷度判讀：量測壓力在錶壓模式使用錶壓單位（`kPag`、`psig`…）並加上大氣壓力（預設 101.325 kPa，可選填海拔自動計算），在絕對壓力模式使用絕對單位；切換模式時換算數值以維持相同的實際壓力（契約見 `docs/hvac-ui-domain-contract.md`）。蒸氣壓縮循環與冷凝器 Exergy 各自提供 Reference State 選單（`BaseAnalysisModule.create_reference_state_row`，預設 Auto），不跟隨物性查詢頁。
- 濕空氣線圖路由（`PsychrometricChartView` + `PsychrometricChartModule`）以逗號分隔的乾球溫度與 RH 標示最多 8 點。線圖曲線與標註點（`ChartMarker`／`ChartGuide`）來自無頭的 `chart.psychrometric`。
- 單位換算路由（`UnitConverterView`）不是分析模組；換算完全委派給 `UnitConverter`，常用換算數值在執行時計算。
- 新分析模組應使用 `BaseAnalysisModule.read_si`／`read_si_list`／`read_text` 讀取輸入（無效值以欄名提示；需要自行換算單位的舊式計算以 `read_float` 讀取未換算的數值，同樣以欄名提示空白或無效輸入）、`bind_independent_unit_sync`／`bind_multi_value_unit_sync` 綁定單位換算，並以 `ResultFormatter` 輸出「名稱: 數值 單位」文字（SI 風量用 m³/h、英制用 ft³/min）。溫差使用 `DeltaT` 量，不得以溫度換算。可在錶壓／絕對壓間切換的壓力輸入使用 `switch_pressure_basis` 切換、`read_absolute_pressure_pa` 讀取（契約見 `docs/hvac-ui-domain-contract.md`）。新分析應以新的 `DedicatedAnalysisView` 子類別接上。
- 熱力圖路由由 `ThermoDiagramView` 直接呈現熱力圖模組自有的設定卡（工作流體、圖表、狀態點）與圖表卡，不套用共用結果卡。
- 通用狀態查詢求解器接受兩個獨立性質。在求解器支援第三條件限制前，必須隱藏第三列輸入及新增入口；支援的性質選單和值／單位控制項應排列於對齊的響應式欄位。
- HVAC 分析計算仍由既有 `analysis_modules` 註冊，改由各自 dedicated view 內的 `AnalysisModuleAdapter` 派送計算與結果呈現；adapter 只認得 `AnalysisDefinition`（`key` + `label` + `input_view` + `calculate` 契約），完全不知道特定分類的存在，因此新增一種既有分析工具不需修改 adapter，只需提供新的 `AnalysisDefinition` 清單。`AnalysisDefinition.calculate` 一律是統一簽章 `Callable[[bool], str]`；任何模組專屬的呼叫慣例（例如 `PsyModule` 需要的 `mode_key`）完全由該模組自己在 `get_analysis_definitions()` 回傳的 `calc_func` 建構時吸收完成（見 `PsyModule._calculate_tdb_twb` / `_calculate_tdb_rh`），`Flet_ui/ui/analysis_definition.py` 的 `definitions_from_module()` 這個 generic factory 本身不判斷、不 import、也不知道任何特定模組的計算模式或呼叫慣例——新增一種分析類別不需要修改這個 factory 或 adapter。`AnalysisModuleAdapter.__init__()` 會在彙整多個模組的定義時做全域 key 驗證：若不同模組間出現重複的 `analysis_id`，立即拋出 `ValueError`（fail fast），不允許 silent overwrite。畫面組成本身由共用的 `AnalysisWorkspace` presentation 殼負責（左側輸入卡含 ToolSelector 與計算按鈕、右側結果區），dedicated view 只負責把既有模組接上這個殼。目前選取的工具必須清楚標示（`ToolSelector` 下拉選單顯示目前項目，輸入卡顯示完整分析名稱）。
- 濕空氣計算的雙模式（乾濕球 / 乾球+RH）仍共用 `PsyModule` 同一組輸入容器並以 `configure_ui_for_mode` 切換欄位可見性；dispatch 只依賴穩定的 mode key（`PsyModule.MODE_TDB_TWB` / `MODE_TDB_RH`，對應 `AnalysisDefinition.key`），不依賴顯示 label —— 翻譯或改文案不會影響計算路徑或 UI 模式切換。`PsychrometricsView` 傳給 `configure_ui_for_mode` 的一律是 `definition.key`，模組不接受顯示 label。這個特例被限制在 `PsychrometricsView` / `PsyModule` 內部，不會外洩到共用的 `DedicatedAnalysisView` 基底或 `AnalysisModuleAdapter`。
- P-h／T-s 圖表路由（`ph_chart` / `ts_chart`）共用同一個 `ThermoDiagramView` 實例與底層 `ThermoDiagramModule`。`AppShell.navigate()` 提供 generic 的 route-activation 協定：若目標畫面實作了 `activate_route(route_key)`，導覽完成後會呼叫它，讓畫面自行處理 route-local 的啟用邏輯；`ThermoDiagramView.activate_route()` 內部持有自己的 `route → mode` 對照表並呼叫既有的 `set_mode("ph"|"ts")`。`flet_app.py`（組合根）及 `AppShell` 完全不知道 `ph_chart`/`ts_chart` 對應 `P-h`/`T-s`，也不會直接呼叫 `set_diagram_type()` 或 `set_mode()`。熱力圖使用專屬的「繪圖」按鈕（非共用 `AnalysisWorkspace` 的執行按鈕），因此其 view 不掛載 `AnalysisWorkspace`。
- 濕空氣計算與圖表產生仍留在既有轉接器／模組；dedicated view 一律透過既有模組實例呼叫，不得複製計算邏輯。
- 舊版 `AnalysisTab` 已移除；分析頁一律由 dedicated view 與 `AnalysisModuleAdapter` 組成，characterization tests 也改由正式進入點建構的工作區驗證。
- 切頁、切換輸出單位、Reference State 與錶壓／絕對壓切換時，輸入、結果與圖表的保留或失效規則見 [`state-invalidation.md`](state-invalidation.md)。`AnalysisModuleAdapter` 為每個分析的輸入加上失效處理：使用者修改會影響計算的輸入時結果立即失效；單位選單與模組登記在 `presentation_only_controls` 的控制項（錶壓／絕對壓切換）只改表示方式，不使結果失效。切換輸出單位時只重新計算仍有效的結果。
- `ThermoDiagramModule` 提供 public `perform_plot(event=None)` 作為唯一的繪圖執行入口；plot button 的 `on_click`（`_on_plot_click`）與 `ThermoDiagramView.perform_calculation()`（供 AppShell Ctrl+Enter 捷徑使用）都轉交給這個 public method，確保兩條觸發路徑最終走同一段邏輯。`_on_plot_click` 保留僅為與既有 Flet button 事件簽章相容，內部直接委派給 `perform_plot`，dedicated view 不再直接依賴 private API。

## 狀態歸屬

`WorkspaceState` 保存目前語意路由、全域結果輸出單位偏好，以及每個輸入欄位各自的單位對應表；不得序列化或保存 Flet 控制項。

舊版性質與分析轉接器目前仍會直接讀寫部分 Flet 控制項狀態。後續遷移應逐步將可持續保存的查詢輸入及結果中繼資料移至具型別的應用程式狀態模型，再由控制項繫結該狀態。以下責任必須分開：

- **呈現狀態**：控制項的選取／可見狀態及欄位驗證。
- **導覽狀態**：穩定的路由鍵值。
- **單位狀態**：每個輸入列各自選取的單位，以及獨立的全域輸出偏好。全域輸出單位（SI / Imperial）只影響「結果如何呈現」，絕不覆寫任何 input 欄位既有的 value 或 unit；`AnalysisModuleAdapter.set_output_unit_system()` 只更新 `output_unit_system` 並在已有成功結果時以新偏好重新計算/呈現，不會呼叫任何會改寫 input 欄位的 hook。
- **熱力狀態**：以標準單位保存的計算結果。
- **分析狀態**：由個別分析模組持有的輸入及結果。

每一筆性質輸入單位都由其輸入列獨立擁有，`WorkspaceState.input_units` 使用 `condition_{row}_{property}` 鍵值（例如 `condition_0_T`）。改變一列的單位不得修改其他輸入列，即使兩列使用相同性質亦同。全域輸出偏好只影響結果呈現，不得覆寫輸入欄位選取的單位。

## 響應式行為

工作區外殼具有三種寬度模式：

- **寬版**（約 1200 px 以上）：完整側邊欄與工作區；側邊欄可收合為圖示列。
- **中版**（約 800–1200 px）：固定為精簡圖示導覽列。
- **窄版**（低於約 800 px）：工作區使用全寬、側邊導覽改為可切換的覆蓋式抽屜；頂端列只保留抽屜按鈕、標誌、目前路由名稱及輸出單位切換。

Flet `ResponsiveRow` 的斷點依頁面寬度判斷，而不是依父容器寬度；移除右側情境面板後，頁面寬度斷點與計算頁實際可用寬度更接近。計算頁的輸入欄與結果欄欄寬由 `AnalysisWorkspace` 的 `INPUT_COLUMN`／`RESULT_COLUMN` 統一決定；關鍵數值依數量排滿一列（最多四張），寬版時圖表與完整性質表並排。

捲動責任必須明確：工作區不得帶動整個外殼捲動；各計算畫面負責自己的捲動區域。性質查詢的底部操作列必須置於可捲動輸入／結果區域之外，讓使用者捲動時仍能操作「重設」及「執行計算」。

## 驗證與計算結果契約

驗證訊息應盡可能顯示在對應欄位旁；全域 Snackbar 只能作為輔助，不能是唯一錯誤訊號。計算狀態必須使用明確的空白、載入中、成功、警告或錯誤標示、圖示及文字，不得只依賴顏色。例外詳細資料不得直接顯示給使用者；領域驗證訊息則可在安全且可採取行動時呈現。

結果由結構化指標及中繼資料組成，包括流體、引擎、參考慣例、輸入單位及輸出系統。原始文字只作為次要且由使用者選擇展開的詳細資料。不得合成計算器未回傳的數值。

成功計算快照分別保存標準 SI 結果、質量、中繼資料、當次輸入摘要及目前輸出單位下的格式化結果；`ResultPanel` 只呈現結構化指標與中繼資料。常駐摘要只顯示輸入條件與輸出單位，不得重複完整格式化詳細輸出；完整格式化輸出只在使用者展開詳細資料時顯示。複製表示則可組合輸入摘要與完整格式化輸出。呈現控制項是計算快照的投影，不得反過來充當快照本身；輸出單位切換時，從同一份 SI 快照更新指標、摘要與詳細文字，不得重新查詢；語意輸入失效或重設時，必須一併清除摘要、格式化文字與複製能力。

計算結果只對應產生它的語意輸入快照。語意輸入包括流體、計算模式、性質種類、數值、參考狀態、理想氣體選項、廣延性質啟用狀態、質量及質量單位所代表的物理量。任何此類輸入改變後，必須使舊結果失效或明確標示為過期；目前畫面不得繼續宣稱舊結果代表目前輸入。現行實作採清除舊快取並顯示「輸入已變更」警告，要求使用者重新計算。

表示方式改變不等於計算語意改變。全域輸出單位切換時，使用已保存的標準 SI 結果快照重新格式化；輸入值改用物理量相同的單位時，先將目前顯示值換算回標準 SI，再轉成新顯示單位。兩者都不得重跑查詢，也不得改寫其他輸入列的單位。結果快照必須同時保存廣延性質所需的標準質量；重新格式化時，須保留該次計算的所有結果類別，包括廣延性質。

廣延性質只在使用者明確啟用相應選項且提供有效質量後計算。隱藏欄位或舊質量值不得自行啟用廣延性質計算。重設會清除查詢數值、欄位錯誤、計算結果快照及可選區塊的呈現狀態，並恢復第三條件列隱藏、廣延性質關閉、原始結果隱藏及詳細結果按鈕的初始文字；流體、計算模式、參考狀態與全域輸出單位偏好則予以保留。

## 測試與維護

應以行為測試驗證單位更新、輸入值重設／換算、預設組合、路由選取、結果狀態及單位系統呈現。結構測試可以檢查外殼與共用控制項契約，但不能取代實際互動或執行階段檢查。新增或修改的函式必須撰寫 PEP 257 docstring；若修改本契約或跨檔行為，須在同一變更中同步更新本文。

## 目前擴充點與路線圖

路由註冊表支援後續新增熱力學、冷凍空調、空氣處理、圖表、工具、資料及設定區域。未來歷史紀錄應依賴 `HistoryRepository` 介面並保存應用程式資料，而不是控制項；JSON／SQLite 持久化方式尚未決定。冷凍循環與過熱度／過冷度工具已由 `domain/refrigeration/` 支援；多級壓縮、經濟器或熱交換器設計等延伸屬於獨立功能工作，應先在 domain 建立並測試再接到 UI。
