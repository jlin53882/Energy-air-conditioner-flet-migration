"""將應用程式狀態與 Flet 控制項及計算結果分開保存。"""

from dataclasses import dataclass, field


@dataclass
class WorkspaceState:
    """保存導覽與顯示偏好，並避免改寫 Flet 控制項中的輸入選擇。"""

    route_key: str = "thermo_properties"
    output_unit_system: str = "SI"
    input_units: dict[str, str] = field(default_factory=dict)

    def set_input_unit(self, input_key: str, unit: str) -> None:
        """獨立記錄單一輸入欄位所選的單位。

參數：
    input_key: 輸入欄位的穩定識別鍵。
    unit: 此欄位所選的單位代碼。

回傳：
    無。"""
        self.input_units[input_key] = unit

    def set_output_unit_system(self, unit_system: str) -> None:
        """設定結果數量格式化時使用的全域輸出偏好。

參數：
    unit_system: 輸出單位系統代碼。

回傳：
    無。"""
        if unit_system not in {"SI", "Imperial"}:
            raise ValueError(f"Unsupported output unit system: {unit_system}")
        self.output_unit_system = unit_system
