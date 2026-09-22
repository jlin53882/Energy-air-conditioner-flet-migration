# Energy_air-conditioner：Flet-only 遷移前完整分析

- 分析日期：2026-09-22（以本機工具執行結果為準）
- 原始路徑：`C:\Users\admin\Desktop\Python_project\Energy_air-conditioner`
- 新工作區：`C:\Users\admin\workspace\Energy_air-conditioner_flet-migration`
- 原始專案未修改；本報告與備份均建立在 workspace。

## 1. 先給結論

這個專案已經有一套相對完整的 Flet UI，主功能入口在 `Flet_ui/flet_app.py`；Tkinter 只集中在 `Tkinter GUI/gui_app_tkinter.py` 與其計算器副本。要改成只保留 Flet，不能只刪 Tkinter 資料夾，還要同步清理啟動器、Nuitka 打包參數、重複計算核心與文件/測試缺口。

目前最重要的阻塞點不是 Tkinter 本身，而是：

1. `run.py` 仍保留 Tkinter/Telegram 的舊模式說明與未定義呼叫路徑。
2. `Flet_ui`、Telegram、Tkinter 各自存在計算邏輯；若直接刪舊 UI，需先確認 Flet 是否已涵蓋舊版功能。
3. 專案有一個確定的 Python 語法錯誤：`Flet_ui/ui_components/analysis_modules/123.py`。
4. 沒有收集到任何 pytest 測試；目前不能靠測試證明遷移沒有回歸。
5. workspace 備份來源包含大量產物/環境資料；備份保留可維護的原始碼與設定，但排除 `.venv`、`__pycache__`、`AutoPunch_Output`、`run.dist`。

## 2. 工具驗證的現況數字

| 項目 | 實測結果 |
|---|---:|
| 原始專案檔案總數（含環境與產物） | 9,393 |
| 原始專案目錄總數 | 833 |
| Python 原始碼（排除環境/產物） | 44 檔、386,445 bytes |
| 可維護備份檔案數 | 54 檔、69,016,226 bytes |
| 備份檔案/bytes 與來源（排除項後） | 54 / 69,016,226，完全相符 |
| AST 可解析 Python 檔 | 43 |
| AST 語法錯誤 | 1 |
| pytest 收集結果 | 0 tests collected |
| 目前虛擬環境匯入 flet | 成功 |
| 目前虛擬環境匯入 CoolProp / Telegram / dotenv / matplotlib | 全部成功 |

## 3. 專案結構與責任

### 3.1 Flet 主線（應保留）

- `Flet_ui/flet_app.py`：Flet page 入口，建立服務與兩個 Tab。
- `Flet_ui/ui_components/property_tab.py`：熱力性質查詢，568 行。
- `Flet_ui/ui_components/analysis_tab.py`：冷凍空調分析，229 行。
- `Flet_ui/ui_components/analysis_modules/`：分析模組；最大的是 `hvac_compressor_module.py` 925 行、`thermo_diagram_module.py` 526 行。
- `Flet_ui/ui_components/unit/`：單位轉換、狀態計算、HVAC 分析與熱力計算。
- `Flet_ui/PsychrometricChart/`：濕空氣/心理圖計算模型。

Flet 主線合計 30 個可維護檔案、243,579 bytes（含 `__init__.py` 與小型程式檔，不含 pyc）。

### 3.2 Tkinter 舊線（Flet-only 後候選移除）

- `Tkinter GUI/gui_app_tkinter.py`：356 行，含 `PropertyTab`、`AnalysisTab`、`MainApplication`、`start_gui`。
- `Tkinter GUI/thermo_calculator.py`：734 行的舊計算器。
- `Tkinter GUI/__init__.py`：空初始化檔。

這條線只被 `run.py` 的舊分支文字/呼叫提及；在現行 `run.py` 中，對應 import 已註解，但 `start_tkinter_gui()` 呼叫仍存在，因此舊模式一旦被選取會出現 `NameError`，不是可用的 fallback。

### 3.3 Telegram 線（與 UI 遷移分開處理）

- `Telegram_bot/` 共有 10 個可維護檔案、83,712 bytes。
- 它不是 Tkinter UI，但共用/複製了 `thermo_calculator.py`。
- `run.py` 仍保留 `bot` 模式；若需求是只保留 Flet UI，不應順手刪 Telegram，除非明確決定連 Bot 功能也移除。

## 4. Flet 與 Tkinter 交叉證據

- `tkinter` 實際出現在 1 個 Python 檔：`Tkinter GUI/gui_app_tkinter.py`。
- Flet 相關 import 出現在 10 個 Python 檔，主要集中於 `Flet_ui/` 與 `run.py`。
- `run.py` 第 2 行仍宣稱「Flet GUI、Tkinter GUI、Telegram Bot」三模式。
- `run.py` 第 9、10 行的 Tkinter/Bot import 已註解，但第 43-46、64-67 行仍呼叫 `start_tkinter_gui()`；第 47-50、69-71 行仍呼叫 `start_bot()`。
- `packae_file.bat` 與 `packae_file2.bat` 都仍以「Flet + Tkinter + Telegram」為打包目標，並啟用 Nuitka `tk-inter` plugin。

判定：Tkinter 在程式架構上已經是半移除狀態，不是完整可運作的第二 UI。這使得 Flet-only 清理的風險較低，但仍必須修正入口與打包配置，不能只刪檔案。

## 5. 重複計算核心與功能風險

`Telegram_bot/thermo_calculator.py` 與 `Tkinter GUI/thermo_calculator.py` 都是 734 行、19 個方法；兩者只有 2 個 diff 行（實測非完全相同）。Flet 另外使用：

- `Flet_ui/ui_components/unit/ThermoStateCalculator.py`：196 行、6 個方法、18 個 CoolProp 引用。
- `Flet_ui/ui_components/unit/HVACAnalyzer.py`：91 行。
- `Flet_ui/ui_components/unit/PsychrometricCalculator.py`：104 行。
- `Flet_ui/ui_components/unit/hvac_calculations/`：拆成多個計算模組。

因此遷移有兩種可能：

- 低風險方案：只移除 Tkinter UI，保留 Telegram 計算器與 Bot；先不合併計算核心。
- 較完整方案：建立單一 domain/service 計算層，讓 Flet 與 Telegram 共用；這不是單純 UI 清理，需另立 phase 與測試。

本輪建議採第一種，避免把「移除 Tkinter」與「重構計算核心」綁在同一個高風險變更中。

## 6. 已驗證問題（Tier A）

### A1. `123.py` 語法錯誤（🔴 高）

- 狀態：✅ 已工具驗證
- 檔案：`Flet_ui/ui_components/analysis_modules/123.py:1`
- 證據：AST 報 `IndentationError: unexpected indent`；全專案 44 個可維護 Python 檔中 43 個成功解析、1 個失敗。
- 衝擊：若被 import、被打包掃描或被自動檢查納入，會使流程失敗；目前檔名像暫存片段，且未被正常模組清單引用的可能性高，但不能在刪除前只靠檔名猜測。
- 建議：先確認是否有任何引用；若無引用，移出正式 Flet source 或刪除。這是 Flet-only 遷移前必須處理的壞檔案。

### A2. Flet-only 入口尚未成立（🔴 高）

- 狀態：✅ 已工具驗證
- 檔案：`run.py:2,9-11,19-27,32-75`
- 證據：使用說明仍列 `gui / tkinter`；舊 import 被註解，但舊分支仍呼叫未定義的 `start_tkinter_gui()`；Bot 分支同樣呼叫被註解的 `start_bot()`。
- 衝擊：使用者透過錯誤模式仍會得到 runtime `NameError`；入口語意與實際可用模式不一致。
- 建議：將入口收斂成明確的 Flet 啟動命令；Telegram 是否保留要獨立決定，不要讓未匯入的模式留在 help 或分支中。

### A3. 打包腳本仍把 Tkinter 當正式依賴（🟡 中）

- 狀態：✅ 已工具驗證
- 檔案：`packae_file.bat:3,6,48,57`、`packae_file2.bat:3,6,56,66`
- 證據：標題寫 Flet + Tkinter + Telegram，並使用 `--enable-plugin=tk-inter`。
- 衝擊：打包產物仍會保留/宣稱 Tkinter 支援，增加依賴與維護誤導；若 Tkinter source 移除，腳本也會與實際架構不一致。
- 建議：在確認 Bot/Matplotlib 的實際打包需求後，移除 tk-inter plugin 與相關文字；不要直接刪除所有 matplotlib 參數，Flet 的熱力圖模組仍可能需要它。

### A4. 全專案沒有測試保障（🔴 高）

- 狀態：✅ 已工具驗證
- 證據：`.venv/Scripts/python.exe -m pytest --collect-only -q` 回報 `no tests collected`。
- 衝擊：移除 Tkinter、修入口、處理語法錯誤後，沒有自動化回歸網；尤其計算結果與 Flet UI 初始化無法被現有測試保護。
- 建議：先補純計算函式測試與 Flet import/啟動 smoke test，再進行刪除。

## 7. 已驗證問題（Tier B）

### B1. 入口/架構文件不足（🟡 中）

- 狀態：✅ 已工具驗證
- 證據：可維護檔案盤點中未找到 `README.md`、`requirements.txt`、`pytest.ini`、`conftest.py` 或測試檔；`pyproject.toml` 的 `readme = "README.md"` 但實際盤點未找到該檔。
- 衝擊：新人無法知道 Flet-only 的正式啟動方式、Bot 是否保留、哪些資料夾是舊版/產物；打包與部署容易再把 Tkinter 加回來。
- 建議：在 workspace 建立 README、架構圖/啟動說明與遷移紀錄；完成後再考慮是否同步回原專案。

### B2. 來源樹混入產物與環境（🟡 中）

- 狀態：✅ 已工具驗證
- 證據：原始盤點 9,393 檔，其中 `.venv` 7,512 檔、`AutoPunch_Output` 1,788 檔；此外有 `run.dist.rar` 約 68 MB。
- 衝擊：搜尋、打包、分析與版本控制都容易誤把產物當 source；目前 AST/LOC 若未排除會失真。
- 建議：workspace 備份已排除環境與生成目錄；後續在工作區加入 `.gitignore`，並把產物另存為 release artifact，而不是 source。

### B3. `run.py` 有大量註解/三模式殘留（🟡 中）

- 狀態：✅ 已工具驗證
- 證據：第 34-75 行整段舊模式被三引號包住或保留為不可達程式；目前可執行主流程實際只在第 33 行 `ft.app(target=flet_main)`。
- 衝擊：讀者會誤以為三種模式仍支援；未來維護者可能重新啟用已失效分支。
- 建議：重寫成單一、短的 Flet entrypoint；不要在新檔保留無法執行的舊程式片段。

## 8. Tier C：移除 Tkinter 後可改善但非立即阻塞

### C1. `flet_app.py` 與元件缺少一致的長期文件註解（🟢 低）

目前多數 class/方法沒有依照長期工程規範補齊用途、參數、回傳與跨模組契約說明。這不阻塞 Flet-only，但在移除舊 UI 時應順便為新的正式入口與服務注入邊界補文件。

### C2. 最大 UI 模組過大（🟡 中）

`hvac_compressor_module.py` 925 行、`property_tab.py` 568 行、`thermo_diagram_module.py` 526 行。這不是此次移除 Tkinter 的直接必要條件；建議另開 phase，先抽純計算/格式化，再拆 UI，避免與刪除舊 UI 混在一個 diff。

### C3. `pyproject.toml` description 仍是模板文字（🟢 低）

`description = "Add your description here"`，與正式工具定位不符；可在 workspace 收尾時一併修正。

### C4. 兩個打包 bat 內容重疊（🟢 低）

`packae_file.bat` 與 `packae_file2.bat` 都是 Nuitka 打包腳本，差異包含 sccache 與顯示進度；應在後續確認哪一個是正式流程後保留一個，避免兩套漂移。

## 9. 建議的 Flet-only 遷移順序（只在 workspace 執行）

### Phase 0：保留與基準（必要）

1. 以目前 workspace 備份作為工作基線。
2. 建立 `.gitignore`，排除 `.venv`、`__pycache__`、打包輸出與 log 產物。
3. 確認 `123.py` 是否有引用；有引用先修正/改名，無引用才移除。
4. 記錄 Flet 現況可啟動基準與核心功能清單。

### Phase 1：入口收斂（低風險）

1. 將 `run.py` 改成只負責 Flet 啟動。
2. 明確決定 Telegram Bot 是「保留為獨立命令」還是「本次一併移除」；本分析不替家豪做這個範圍決定。
3. 若保留 Bot，將 Bot 入口移出 GUI launcher，建立明確的獨立啟動方式；不要保留未匯入的假分支。
4. 同步修正使用說明與打包腳本。

### Phase 2：測試與驗證（刪除前）

1. 對 `Flet_ui/ui_components/unit/` 的純轉換/計算補測試。
2. 加 Flet 模組 import smoke test。
3. 加入口 smoke test（驗證 `run.py` 的 target wiring，不啟動永久 GUI）。
4. 對 `123.py` 的處理補一個「檔案不存在/已移除」的防回歸檢查，避免暫存檔復活。

### Phase 3：移除 Tkinter（最後）

1. 確認無 source/test/import/打包引用後，移除 `Tkinter GUI/`。
2. 移除 Tkinter 專用 Nuitka plugin 與文件文字。
3. 不刪 `Telegram_bot/thermo_calculator.py`，除非 Telegram 也確定退出；它不是 Tkinter UI。
4. 執行 AST、import、focused tests、Flet smoke test。

### Phase 4：收尾

1. 更新 README、pyproject description、打包說明。
2. 做 dead code pass：檢查 `run.py` 舊符號、Tkinter 字串、未使用 import、重複打包腳本。
3. 檢查 workspace diff，確認沒有把 `.venv`/產物帶入變更。

## 10. 備份內容與排除項目

workspace 備份目錄：`C:\Users\admin\workspace\Energy_air-conditioner_flet-migration`

保留：Python source、Flet/Tkinter/Telegram source、設定、bat、pyproject、uv.lock、現有壓縮檔與 log。

排除：`.venv/`、`__pycache__/`、`AutoPunch_Output/`、`run.dist/`、`.git/`（若未來存在）、`.pytest_cache/`。

備份驗證：來源排除後 54 檔 / 69,016,226 bytes；備份同樣是 54 檔 / 69,016,226 bytes。

## 11. 初始分析階段未做的事（歷史快照）

以下是初始分析完成時的狀態，不代表目前 workspace 狀態：

- 當時沒有修改 Desktop 原始專案。
- 當時沒有刪除 Tkinter。
- 當時沒有修改 workspace 內的 source code。
- 當時沒有把 Telegram Bot 自行判定為要刪除。
- 當時沒有把 `123.py` 自行刪除，因為需要先做引用確認。

## 12. Flet 1.0.0 與依賴更新結果（2026-09-22）

本次更新在 workspace 分支 `chore/update-flet-and-dependencies` 執行，未修改 Desktop 原始專案。

### 版本

- `flet[all]`: `0.28.3` → `1.0.0`
- 新增 `flet-charts>=1.0.0`：Flet 1.0 將 `MatplotlibChart` 移至獨立套件
- `coolprop`: `7.1.0` → `8.0.0`
- `matplotlib`: `3.10.7` → `3.11.2`
- `nuitka`: `2.8.4` → `4.2.1`
- `pytest`: `8.4.2` → `9.1.1`
- `python-telegram-bot`: `22.5` → `22.8`
- `requests`: `2.32.5` → `2.34.2`
- `sccache`: `0.10.0` → `0.16.0`
- 其餘 lock 依賴也由 `uv lock --upgrade` 更新

### Flet 1.0 遷移修正

- `ft.app()` 啟動器改用 `ft.run()`。
- 舊版 `ft.Tabs(tabs=[ft.Tab(content=...)])` 改為 `TabBar` + `TabBarView`。
- `Tab(text=...)` 改為 `Tab(label=...)`。
- `ft.ElevatedButton` 改為 `ft.Button(content=...)`。
- `ft.border.all` / `ft.border_radius.all` 改為 `ft.Border.all` / `ft.BorderRadius.all`。
- `ft.padding.all/only` 改為 `ft.Padding.all/only`。
- `ft.alignment.*` 改為 `ft.Alignment.*`。
- `Dropdown(on_change=...)` 改為 Flet 1.0 的 `on_select=...`；`SegmentedButton` 保留 `on_change`。
- `flet.matplotlib_chart.MatplotlibChart` 改為 `flet_charts.MatplotlibChart`。
- 移除未被其他檔案引用且無法解析的 `Flet_ui/ui_components/analysis_modules/123.py`。
- 移除 launcher 的 Tkinter 分支與失效模式呼叫，並刪除 `Tkinter GUI/` 舊 UI；Telegram Bot package 仍保留為獨立功能。
- 更新兩個 Nuitka bat，移除 Tkinter plugin 與 Flet + Tkinter 宣稱。
- 修正 Flet 1.0 中未掛載到 Page 前讀取 `control.page` 會拋 `RuntimeError` 的初始化路徑。

### 驗證結果

- `uv lock --check`: 通過
- `uv run pytest -q`: 初期基線 `3 passed`（歷史快照；收尾後已補測試，見第 14 節）
- `uv run pytest --collect-only -q`: 初期基線 `3 tests collected`（歷史快照）
- `uv run python -m compileall -q Flet_ui Telegram_bot run.py telegeram_chatid.py`: 通過
- Flet 1.0 控件 smoke test：`PropertyTab` 與 `AnalysisTab` 成功建立，控制項數量分別為 11、7
- `uv run` environment import：`flet 1.0.0`、`flet-charts 1.0.0`、`CoolProp 8.0.0` 成功
- 舊 API 靜態掃描：`ft.ElevatedButton`、`ft.border.all`、`ft.border_radius.all`、`ft.padding.all/only`、`ft.alignment.*`、`flet.matplotlib_chart` 均為 0

（本段為遷移中期歷史快照；真人 UI 驗收結果見第 13 節。）

## 13. Flet 1.0 大面積灰色區塊修復（2026-09-22）

### 根因

原始 Flet 0.28.3 畫面有完整的熱力學輸入表單；Flet 1.0 畫面只顯示上方三個欄位，下面被大面積灰色區塊取代。交叉測試確認問題不是 `PropertyTab` 控制項未建立，而是 Flet 1.0 的 `Text` API 參數遷移錯誤：

- `Text(style=ft.TextThemeStyle.TITLE_MEDIUM)` 把 `TextThemeStyle` enum 傳給了 `style`（`TextStyle` 參數）。
- Flet 1.0 正確參數是 `theme_style=ft.TextThemeStyle.TITLE_MEDIUM`。
- 第一個錯誤用法位於分隔線後的「熱力學性質輸入」標題，因此後續控制項全部被推離可視範圍，形成大面積灰色區塊。
- `analysis_tab.py` 也有相同的兩處錯誤，會造成冷凍空調分析頁面相同回歸。

### 修復

- `property_tab.py` 3 處 `style=ft.TextThemeStyle.*` 改為 `theme_style=ft.TextThemeStyle.*`。
- `analysis_tab.py` 2 處 `style=ft.TextThemeStyle.*` 改為 `theme_style=ft.TextThemeStyle.*`。
- 移除結果容器在 Flet 1.0 中不應使用的 `expand=True`，避免結果面板搶占可視高度。
- `flet_app.py` 的兩個 `TabBarView` 子頁面以 `ft.Container(expand=True)` 包裝，明確建立 Flet 1.0 的頁面 layout boundary。

### 實際 UI 驗證

使用乾淨、單一 listener 的 Flet Web runtime：

```text
uv run flet run --web --port 8550 run.py
```

實際瀏覽器驗證結果：

- 「熱力性質查詢」：完整顯示熱力學性質輸入標題、3 組性質／數值／單位、廣延性質、總質量、執行計算。
- 「冷凍空調分析」：可切換分頁，顯示分析項目、參數輸入、入口／出口壓力、執行分析、分析結果與 SI／Imperial 切換。
- 原本大面積灰色區塊：已消失。
- 啟動端點：HTTP 200。
- Flet server log：正常啟動，無 traceback。

### 回歸測試

- 新增 TabBarView layout boundary assertion。
- 新增 Flet 1.0 `theme_style` 參數 assertion。
- 原始 bug 測試先得到 RED；修正後得到 GREEN。
- 中期修復後曾達到 `5 passed`；收尾補測試後最終結果見第 14 節。

## 14. 收尾驗證、問題教訓與可重複規則（2026-09-22）

### 14.1 本輪真正驗證的範圍

- Flet UI 兩個正式頁面均以乾淨 Web runtime 實際啟動並截圖交叉比對原始 Flet 0.28.3 畫面。
- `AnalysisTab` 的 16 個分析選項逐一切換並執行預設計算路徑；最終 `16/16` 完成，沒有未捕捉例外。
- 熱力學性質頁的控制項建構、單位／狀態計算、CoolProp 流體驗證與結果容器均有測試。
- 冷凍空調分析頁的 HVAC 基礎方程式、濕空氣兩條計算路徑、圖表計算路徑均有測試或 smoke coverage。
- Telegram Bot 僅保留架構與 import／compile 驗證；需要真實 Telegram token 的外部連線未在本機執行，不能宣稱已完成真人 Bot 整合測試。

### 14.2 維護者指出的問題與本次回應

1. 「大面積灰色圖塊不一定是正常 placeholder」：建立原始／新版 screenshot baseline，確認是內容消失的 UI regression，不能只看 control tree。
2. 「要自己測試 UI」：實際啟動 Flet Web、切換兩頁、檢查表單／分析結果區與 server HTTP 200；compile/import 不再作為 UI 完成的唯一證據。
3. 「只保留 Flet，但不要誤刪 Bot」：移除 Tkinter UI 與 launcher 分支，Telegram Bot package 保留。
4. 「Flet 升級前要看 Obsidian 文件」：本次先讀既有 Flet migration／API 對照文件，再進行 API 變更。
5. 「所有頁面與功能要測試後才補測試」：先做兩頁 runtime 驗證與 16 選項 smoke，再補計算與頁面回歸測試。

### 14.3 做得不好的地方（禁止重犯）

- 早期只驗證 control 建構、pytest 與 compile，沒有立即做原始／新版畫面差異，因此錯誤 layout 一度被誤判為可接受灰色區域。
- Flet 1.0 的 `Text` 參數只做了名稱替換，沒有逐一核對 enum 型別語意；`style` 與 `theme_style` 的差異直接造成畫面內容消失。
- headless 測試物件沒有模擬 Flet control 的 page attachment 行為，先後暴露 `self.parent`、`control.page`、`chart.update()` 的 runtime 假設。
- 初期測試數量過少，沒有涵蓋所有分析選項、CoolProp 查詢、Psychrometric 路徑與圖表計算。
- 中期 `ANALYSIS.md` 曾保留「尚未真人驗收」及 `5 passed` 的舊結論；收尾已改成歷史快照並補上最終數字，避免報告自相矛盾。

### 14.4 下次可直接重複使用的規則

1. Major UI framework upgrade 前，先讀 migration 文件，再建立 baseline screenshot。
2. UI 驗證必須三層並行：source/API、control tree、實際 runtime screenshot；三者不能互相取代。
3. 看到大片均勻灰色區塊時，先和原始畫面比對；原始有內容而新版沒有，就列為 regression。
4. Flet control 的 `.page` 在未掛載時可能拋 `RuntimeError`；初始化與 headless 測試路徑必須安全檢查 attachment。
5. 分析 registry 新增或遷移後，逐一列舉所有選項，測試切換、可見性與預設計算，不只測第一個選項。
6. 行為修復先做 bug-RED，再做修復-GREEN；測試應固定真正的 API 契約，而不是把錯誤畫面固定成基準。
7. UI、計算核心、外部 Bot 分開驗證；沒有 token／外部服務時，明確標示未做 integration test，不夸大完成度。
8. 收尾報告中的中期數字要標為歷史快照，最終測試數字只從最後一次工具輸出填入。

### 14.5 最終工具證據

- `uv lock --check`: 通過。
- `uv run pytest -q`: `12 passed in 1.57s`.
- 新增 coverage 測試檔：`tests/test_calculation_and_analysis_coverage.py`，7 tests；原有 Flet compatibility tests 5 tests。
- `uv run python -m compileall -q Flet_ui Telegram_bot run.py telegeram_chatid.py`: 通過。
- `uv pip check`: `All installed packages are compatible`。
- `git diff --check`: 通過。
- Flet runtime：HTTP 200；兩個頁面 screenshot 均顯示完整內容，無大面積灰色遮蔽。
- 暫時診斷檔 `ui_probe_temp.py` 已刪除，沒有納入正式專案。
