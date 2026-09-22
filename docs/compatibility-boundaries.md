# 相容性邊界

本文件列出目前刻意保留的暫時性 production 行為與整合邊界。這不是遷移歷史或變更日誌；已完成的架構工作應記錄在目前架構與領域契約文件中。

## Telegram 比容相容性

**狀態：** 啟用中

### Telegram 正式契約

`V` 代表比容，單位為 `m³/kg`。當 CoolProp 需要密度時，canonical thermodynamic boundary 使用：

```text
D = 1 / V
```

### Telegram 舊有行為

Telegram 相容性路徑保留既有的比容換算與 legacy calculation semantics。其 `V` 路徑刻意不視為 canonical domain conversion。

### Telegram 保留原因

目前仍有 Telegram caller 依賴既有行為；改變其物理意義會成為行為遷移，而不是安全的 adapter-only change。

### Telegram 允許修改範圍

在不改變 `V` 意義的前提下，只能改善 reference-state ownership、synchronization、explicit error handling 與 adapter wiring。不得將此行為複製到 domain service，也不得默默重新解釋既有 Telegram request。

### Telegram 移除條件

只有在 Telegram caller 擁有獨立審查過的比容契約、characterization coverage，並完成所有受影響 handler 的明確遷移後，才能移除此邊界。

## 排除的舊有 Psychrometric 實作

**狀態：** 啟用中的 adapter 邊界

### Psychrometric 正式契約

Domain psychrometric service 回傳中立的 numeric SI-oriented result。

### Psychrometric 舊有行為

`Flet_ui/PsychrometricChart/PsychrometricChart_01_ASHF_model.py` 仍是實際 calculation provider，並透過 `infrastructure.psychrometrics.LegacyPsychrometricModelAdapter` 存取。

### Psychrometric 保留原因

現有 Flet 與 Telegram 行為仍依賴該 model；其內部公式與 tuple implementation 不屬於中立的 domain contract。

### Psychrometric 允許修改範圍

Adapter 可以轉換 input、result shape 與 display formatting。Domain code 不得 import 此排除 model，一般架構工作也不得修改其內部公式。

### Psychrometric 移除條件

只有在新的 neutral psychrometric implementation 已針對必要 input、output、invalid input 與 channel behavior 提供獨立 characterization parity evidence 後，才能替換此 adapter。
