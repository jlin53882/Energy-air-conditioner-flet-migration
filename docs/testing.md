# 測試策略

## 1. 測試層級

Repository 目前有許多 test 放在 `tests/characterization/`；以下是 logical layer，不代表每一個目錄都已存在：

- domain 與 equation test；
- adapter 與 compatibility test；
- application/service test；
- integration 與 Flet construction test；
- architecture guardrail test；
- compile、dependency 與 packaging check。

Test 應放在最接近的既有 layer，不得只為了命名一致而發明新的目錄結構。

## 2. Characterization test

Characterization test 用來記錄 consolidation 前或 consolidation 中的 boundary behavior。當 Flet 與 Telegram behavior 不同時，它很有價值；但 characterization 不自動等於長期 desired contract。若 contract 被刻意改變，應更新 characterization，或新增讓新決策明確化的 contract test。

## 3. Domain test

Domain test 覆蓋 canonical unit、thermodynamic state calculation、HVAC equation、psychrometric result shape、reference-state policy 與 explicit error behavior。Test 應使用 numeric canonical value，不應依賴 Flet control、Telegram transport 或 display formatting。

## 4. Adapter test

Adapter test 驗證 parsing、compatibility conversion、display conversion、error presentation 與 channel-specific output。必須證明 unknown canonical unit 會明確失敗，也必須證明 legacy compatibility behavior 不會默默變成 domain contract。

## 5. Integration test

Integration 與 smoke test 使用 minimal、faithful stub 建立真正的 production entrypoint 或 UI component。應涵蓋 Flet tab construction、代表性的 analysis selection、psychrometric Flet/Telegram path 與 application service boundary。

## 6. Architecture guardrail

Guardrail 驗證 dependency direction 與 ownership invariant：

- domain 不得 import Flet 或 Telegram package；
- application 不得 import channel rendering/runtime object；
- 只有 `ReferenceStateService` 可以直接修改 CoolProp reference state；
- reference-state transaction 使用 shared synchronization mechanism；
- analysis definition 提供唯一的 semantic ID；
- UI lifecycle code 使用 service boundary。

Guardrail 應檢查相關的 production tree，並在新增 boundary violation 時失敗，不得只檢查單一變更檔案。

## 7. Runtime smoke test

Runtime smoke coverage 應執行真正的 Flet composition path、property query path、analysis registration、psychrometric adapter 與 chart state pipeline。Static import check 不能取代 production entrypoint construction。

## 8. Regression workflow

行為 bug 使用以下流程：

```text
重現 → RED regression → 最小修復 → GREEN regression → 完整 suite
```

Process-global dependency 必須覆蓋 sequential isolation、concurrency/interleaving、cross-request isolation 與 explicit policy ownership。只有 lock test 不足以證明 request 不會繼承 ambient process state。

Architecture change 應先記錄 current behavior、建立 contract、進行最小 boundary change、驗證 caller，並只在沒有 reference 後移除 replaced path。

## 驗證命令

從 repository root 執行完整 local verification：

```bash
uv run pytest -q
uv lock --check
uv pip check
uv run python -m compileall -q Flet_ui Telegram_bot application domain chart infrastructure run.py telegeram_chatid.py
git diff --check
```

迭代期間先執行 focused test，最後一次 edit 後再執行完整 suite。回報必須使用工具實際輸出；pending external CI 不等於 local pass。
