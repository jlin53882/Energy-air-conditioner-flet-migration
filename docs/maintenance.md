# 維護指南

## 1. 修改 production code 前

1. 搜尋 symbol 或 contract 的所有 caller 與 consumer。
2. 確認目前的 executable behavior 與 domain meaning。
3. 檢查 [`compatibility-boundaries.md`](compatibility-boundaries.md) 與 [`architecture.md`](architecture.md) 中的 dependency direction。
4. 檢查 repository 與 GitNexus index 的 freshness；不得將 stale graph 視為唯一 caller evidence。
5. 新增或更新表達預期行為的 regression test。
6. 以最小變更關閉 contract。
7. 執行 focused test，再執行 [`testing.md`](testing.md) 的完整驗證組合。

## 2. Domain change 規則

- 每一條規則只保留一個 domain implementation。
- Canonical quantity 與 unit semantics 必須位於 domain/application boundary，不得放在 UI 或 handler。
- Architecture-only refactor 不得修改 physics formula。
- Unknown canonical unit 必須明確失敗，不得默默假設為 SI。
- Process-global dependency 必須有明確 request policy，並測試 sequential、concurrent 與 cross-request isolation。
- 新增或修改的 Python function/class 使用 PEP 257 docstring，說明內容使用中文。

## 3. Architecture change 規則

- 維持 `channel adapter → application → domain` 的方向。
- Domain 不得 import Flet、Telegram 或 infrastructure implementation。
- Application 必須獨立於 channel control、update、context 與 rendering。
- 新 route、module、script 與 entrypoint 都必須同時檢查 import 與 registration/wiring。
- 新 production code 不得留下零引用 helper、被替換實作的 duplicate，或計算後未使用的 value。

## 4. Compatibility boundary 規則

Compatibility facade 只有在下列條件都成立時才能保留：

- 仍存在 legacy caller；
- target contract 已文件化；
- boundary 有 regression coverage；
- 允許範圍狹窄；
- removal criteria 明確。

Compatibility facade 不代表可以建立永久的第二份 core implementation。目前接受的 boundary 列在 [`compatibility-boundaries.md`](compatibility-boundaries.md)。

## 5. 文件更新規則

長期文件描述目前的 architecture、domain contract、接受的 compatibility boundary、testing strategy 與 maintenance rule。內容應使用現在式、以 contract 為中心的語言，並以中文說明。

不要把 PR number、commit SHA、phase label、一次性 audit count 或 review snapshot 放進 current documentation。歷史證據保留在 Git history 與 PR history。當 executable behavior 或 invariant 改變時，應在同一次變更同步更新對應 current-state document。

文件權威關係如下：

- production code 與 executable test 是 executable truth；
- `docs/architecture.md` 是 intended architecture；
- `docs/domain-contracts.md` 是 intended domain contract；
- `docs/compatibility-boundaries.md` 記錄接受的 temporary exception；
- `docs/testing.md` 記錄 testing strategy。

若兩者不一致，視為 architecture 或 contract drift。必須判斷應修改 code 還是文件，不得讓分歧靜默存在。

## 6. 驗證清單

在交接或 commit 前：

- focused regression test 通過；
- `uv run pytest -q` 通過；
- production entrypoint 與 package 的 compileall 通過；
- `uv lock --check` 通過；
- `uv pip check` 通過；
- 依 repository line-ending policy 執行 `git diff --check` 並通過；
- 已確認 worktree 與目標 branch；
- push 後讀回 external PR/branch state。

## 7. 目前維護限制

以下是目前的 technical constraint，不是 phase 或 PR history：

- Telegram specific-volume behavior 仍是 active compatibility boundary。
- Remaining compressor analysis 仍使用 legacy path，遷移前需要獨立 characterization。
- Telegram constructor dependency injection 尚未完全整合。
- Chart renderer 與 sampling responsibility 尚未完全分離。
- Packaging target 與 build-script cleanup 仍是後續維護工作。
- Packaging metadata 屬於 `pyproject.toml` 與 `uv.lock`；build script 必須針對明確 artifact，且不得以 build side effect 修改 dependency metadata。

這些限制不得被默默提升為 domain contract。未來若要移除或遷移，必須同步更新 compatibility/maintenance classification 並補上對應 test。
