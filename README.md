# Energy Air Conditioner

## 專案概覽

Energy Air Conditioner 是以 Flet 為基礎的 HVAC 與熱力學應用程式。它提供物性計算、HVAC 分析、濕空氣計算與熱力學圖表，且不含 Tkinter UI 進入點。

## 支援的介面

- **Flet：** 透過 `run.py` 啟動的互動式桌面應用程式。
- **Telegram：** 位於 `Telegram_bot/` 下的機器人介面。

兩個介面會在契約已完成整合的部分使用共用的應用程式與領域服務。通道專用的格式化邏輯仍保留在各自的轉接層中。

## 高階架構

```text
Flet / Telegram adapters
            ↓
       application
            ↓
          domain

infrastructure adapters ──┐
                           ↑
                    composition roots
```

詳細的相依性規則與所有權邊界記錄於 [`docs/architecture.md`](docs/architecture.md)。

## 執行／開發

使用 `uv` 安裝鎖定的環境，然後啟動 Flet 應用程式：

```bash
uv sync
uv run python run.py
```

Telegram bot 有自己的進入點與設定需求。不要讓 Flet 啟動器為了記錄或啟動而依賴 Telegram 設定。

## 設計草稿隔離

`sketches/` 僅供本機保存未正式採用的 UI 原型、比較圖與設計草稿，不屬於正式程式碼或文件。請勿將此資料夾加入 Git、commit、push 或上傳至 PR／其他遠端；需要參考時，請在本機工作區使用。正式 UI 行為以程式碼及 [`docs/ui-architecture.md`](docs/ui-architecture.md) 為準。

## 測試

使用以下命令執行完整測試套件：

```bash
uv run pytest -q
```

完整的驗證清單位於 [`docs/testing.md`](docs/testing.md)。

## 文件索引

- [架構](docs/architecture.md)
- [領域契約](docs/domain-contracts.md)
- [相容性邊界](docs/compatibility-boundaries.md)
- [測試策略](docs/testing.md)
- [維護指南](docs/maintenance.md)
- [UI 架構與呈現契約](docs/ui-architecture.md)

## 已知的相容性邊界

刻意保留的 Telegram 專用比容積（`V`）行為屬於轉接層邊界，而不是規範性的領域契約。其他目前的限制及其移除條件列於 [`docs/compatibility-boundaries.md`](docs/compatibility-boundaries.md) 與 [`docs/maintenance.md`](docs/maintenance.md)。

## 文件權威性

正式程式碼與可執行測試是可執行的真實依據。`docs/` 下的文件描述預期架構、領域契約、已接受的相容性邊界與維護規則。若程式碼與文件不一致，應將差異視為架構或契約漂移，並決定是否需要更新程式碼或文件；不要默默留下不一致。
