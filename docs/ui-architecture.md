# HVAC 工作區 UI 架構

## 用途與事實界線

本文記錄 Flet 工程工作區預期遵守的 UI 架構契約。可執行程式碼代表目前實際行為；本文記錄預期契約。兩者若不一致，即屬架構偏移，必須調查並修正，不可默默選擇其中一方當作正確答案。

目前遷移保留既有熱力學與 HVAC 計算服務及其應用程式／領域邊界。畫面可以收集、驗證輸入，透過轉接器呼叫既有服務並呈現其回傳值，但不得在畫面層重寫熱力方程式。

## 應用程式外殼

`Flet_ui/flet_app.py` 是組合根，負責建立既有服務，並掛載 `Flet_ui/ui/app_shell.py`。

`AppShell` 負責四個區域：

- **頂端列**：應用程式識別資訊與全域結果輸出單位偏好。
- **側邊欄**：以穩定路由鍵值識別的分組導覽，不以翻譯後的顯示文字作為路由識別。
- **工作區**：目前選取的畫面及其路由標題。
- **情境面板**：桌面版選用區域。不得自行假造計算歷史；在歷史資料儲存介面尚未接通前，只能呈現明確的空狀態及冷媒捷徑。

外殼會將每個唯一畫面固定掛載於同一個 `Stack`，切換路由時只改變可見狀態。這可避免圖表等昂貴子控制項在導覽時被銷毀重建，並減少 Flet 控制項生命週期變動。PR #4（Analysis Workspace Migration）之後，每個分析路由對應各自獨立的 dedicated view 實例（`CompressorView` / `EvaporatorView` / `CondenserView` / `PsychrometricsView` / `ThermoDiagramView`），彼此互不共享父容器；`AppShell` 不需要知道任何 analysis category 的細節，只依 `route.key` 決定要顯示哪一個已掛載的 view。

## 導覽契約

`Flet_ui/ui/navigation.py` 定義語意路由識別碼與顯示文字。目前註冊的路由包括首頁、熱力狀態查詢、壓縮機、蒸發器、冷凝器、濕空氣性質、P-h 圖及 T-s 圖。每個分析路由都對應既有分析註冊表中的分類。新增路由必須代表已實作工具，或明確標示為不可使用；規劃中的項目不得呈現得像可執行功能。

路由身分是資料（`route.key`），與顯示文字彼此獨立。導覽狀態由 `WorkspaceState` 保存，不得依賴標籤文字或 Flet 選取索引。

## 設計權杖與共用元件

`Flet_ui/ui/theme.py` 集中管理間距、圓角、控制項尺寸、寬度建議、顏色及字體。新增工作區畫面應重用這些設計權杖，不應在各畫面另行建立局部色盤或間距常數。

`Flet_ui/ui/components/` 目前提供：

- `EngineeringCard`：共用的卡片底面與標題分組。
- `QuantityInput`：語意上合併數值與單位的輸入元件，可在逐步遷移舊表單時沿用既有控制項。
- `ResultPanel`：明確呈現空白、載入中、成功、警告與錯誤狀態；指標卡只呈現計算轉接器實際提供的數值。
- `Sidebar`：帶有分組及工具提示的路由控制項。

輸入控制項包裝器負責畫面呈現及欄位層級驗證。單位換算由既有 `UnitConverter` 或領域／應用程式轉接器負責；畫面不得複製一套換算公式。

共用分析輸入列會將數值欄名及單位欄名分別顯示在 `TextField` 與 `Dropdown` 上方。不得把欄名塞進外框控制項，避免壓縮機、蒸發器、冷凝器及其他分析表單發生文字與外框碰撞。一般分析欄名描述量的意義，切換單位時保持不變；熱力圖欄名則刻意包含單位並隨單位更新。所有情況下，單位下拉選單的目前選取值才是該控制項單位的唯一來源。

## 畫面職責與遷移界線

- 性質查詢工作區將既有的模式、流體、參考狀態及性質控制項組合成計算設定、已知條件、選用廣延性質、結果與操作區域。
- 通用狀態查詢求解器接受兩個獨立性質。在求解器支援第三條件限制前，必須隱藏第三列輸入及新增入口；支援的性質選單和值／單位控制項應排列於對齊的響應式欄位。
- HVAC 分析計算仍由既有 `analysis_modules` 註冊，改由各自 dedicated view 內的 `AnalysisModuleAdapter` 派送計算與結果呈現；adapter 只認得 `AnalysisDefinition`（`key` + `label` + `input_view` + `calculate` 契約），完全不知道特定分類的存在，因此新增一種既有分析工具不需修改 adapter，只需提供新的 `AnalysisDefinition` 清單。`AnalysisDefinition.calculate` 一律是統一簽章 `Callable[[bool], str]`；任何模組專屬的呼叫慣例（例如 `PsyModule` 需要的 `mode_key`）完全由該模組自己在 `get_analysis_definitions()` 回傳的 `calc_func` 建構時吸收完成（見 `PsyModule._calculate_tdb_twb` / `_calculate_tdb_rh`），`Flet_ui/ui/analysis_definition.py` 的 `definitions_from_module()` 這個 generic factory 本身不判斷、不 import、也不知道任何特定模組的計算模式或呼叫慣例——新增一種分析類別不需要修改這個 factory 或 adapter。`AnalysisModuleAdapter.__init__()` 會在彙整多個模組的定義時做全域 key 驗證：若不同模組間出現重複的 `analysis_id`，立即拋出 `ValueError`（fail fast），不允許 silent overwrite。畫面組成本身由共用的 `AnalysisWorkspace` presentation 殼負責（Header + ToolSelector + Input/Result 並排 + ActionBar），dedicated view 只負責把既有模組接上這個殼。已選取的工具必須有明顯的視覺狀態（`ToolSelector`）。
- 濕空氣計算的雙模式（乾濕球 / 乾球+RH）仍共用 `PsyModule` 同一組輸入容器並以 `configure_ui_for_mode` 切換欄位可見性；dispatch 只依賴穩定的 mode key（`PsyModule.MODE_TDB_TWB` / `MODE_TDB_RH`，對應 `AnalysisDefinition.key`），不依賴顯示 label —— 翻譯或改文案不會影響計算路徑或 UI 模式切換。`PsychrometricsView` 傳給 `configure_ui_for_mode` 的一律是 `definition.key`；legacy `AnalysisTab` 仍可能傳入顯示 label，`PsyModule._resolve_mode_key()` 會將其正規化為穩定 key 後才判斷，只是相容層，不影響新架構的 key/label 分離。這個特例被限制在 `PsychrometricsView` / `PsyModule` 內部，不會外洩到共用的 `DedicatedAnalysisView` 基底或 `AnalysisModuleAdapter`。
- P-h／T-s 圖表路由（`ph_chart` / `ts_chart`）共用同一個 `ThermoDiagramView` 實例與底層 `ThermoDiagramModule`。`AppShell.navigate()` 提供 generic 的 route-activation 協定：若目標畫面實作了 `activate_route(route_key)`，導覽完成後會呼叫它，讓畫面自行處理 route-local 的啟用邏輯；`ThermoDiagramView.activate_route()` 內部持有自己的 `route → mode` 對照表並呼叫既有的 `set_mode("ph"|"ts")`。`flet_app.py`（組合根）及 `AppShell` 完全不知道 `ph_chart`/`ts_chart` 對應 `P-h`/`T-s`，也不會直接呼叫 `set_diagram_type()` 或 `set_mode()`。熱力圖使用專屬的「繪圖」按鈕（非共用 `AnalysisWorkspace` 的執行按鈕），因此其 view 不掛載 `AnalysisWorkspace`。
- 濕空氣計算與圖表產生仍留在既有轉接器／模組；dedicated view 一律透過既有模組實例呼叫，不得複製計算邏輯。
- `Flet_ui/ui_components/analysis_tab.py` 內的舊版 `AnalysisTab` 已標示為 LEGACY／COMPATIBILITY，production route 不再使用它；僅因既有 characterization tests 仍直接建構並驗證其行為而保留，待這些測試遷移完成後計畫一併移除。
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

- **寬版**（約 1200 px 以上）：完整側邊欄、工作區與情境面板。
- **中版**（約 800–1200 px）：精簡圖示導覽列並隱藏情境面板。
- **窄版**（低於約 800 px）：工作區使用全寬、側邊導覽改為可切換的覆蓋式抽屜，且不顯示情境面板。

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

路由註冊表支援後續新增熱力學、冷凍空調、空氣處理、圖表、工具、資料及設定區域。未來歷史紀錄應依賴 `HistoryRepository` 介面並保存應用程式資料，而不是控制項；JSON／SQLite 持久化方式尚未決定。狀態點／循環工作區及過熱度／過冷度／飽和工具，除非既有領域服務已支援，否則都屬於獨立功能工作。
