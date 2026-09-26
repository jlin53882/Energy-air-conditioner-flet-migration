"""批次計算與比較：參數掃描、冷媒比較、敏感度分析（龍捲風圖）。

計算委派給 `BatchService`（冷凍循環與冷凝器 Exergy 的結構化結果）；本模組只負責表單、
單位換算、結果文字與圖表。指標都與 reference state 無關，因此不提供 Reference State 選單。
無法計算的點不會中斷整批計算，列在結果最後並附原因；圖上以斷線表示。
"""

from __future__ import annotations

from math import nan

import flet as ft

from application.batch import (
    CONDENSER_EXERGY_TARGET,
    CYCLE_TARGET,
    FLUID_VARIABLE,
    BatchMetric,
    BatchService,
    BatchTarget,
    BatchVariable,
    ParameterSweepRequest,
    RefrigerantComparisonRequest,
    SensitivityOutcome,
    SensitivityRequest,
    SweepAxisRequest,
    SweepOutcome,
)
from application.models import CondenserExergyRequest, RefrigerationCycleRequest
from domain.batch import MAX_AXIS_POINTS, BatchPoint, linear_values

from ...ui.components.figure_panel import FigurePanel
from ...ui.theme import TOKENS, style_dropdown
from ..unit.UnitConverter import UnitConverter
from .base_analysis_module import BaseAnalysisModule
from .result_formatting import ResultFormatter

NO_AXIS = "none"
BOUNDARY_AMBIENT = "ambient"
BOUNDARY_CUSTOM = "custom"

# 基準條件：(欄位名稱, 輸入列名稱, 預設值, 性質代碼, 預設單位)。
CYCLE_BASE_ROWS = (
    ("evaporating_temperature_k", "蒸發溫度（飽和）", "5", "T", "°C"),
    ("condensing_temperature_k", "冷凝溫度（飽和）", "45", "T", "°C"),
    ("superheat_k", "過熱度", "5", "DeltaT", "K"),
    ("subcooling_k", "過冷度", "5", "DeltaT", "K"),
    ("isentropic_efficiency", "壓縮機等熵效率", "70", "Eff", "%"),
    ("refrigeration_capacity_w", "冷凍能力", "10", "Power", "kW"),
)
# 冷凝器預設值與冷凍循環共用的預設冷媒 R32 對應：2800 kPa 的飽和溫度約 45.6 °C，
# 入口 70 °C 為過熱蒸氣、出口 35 °C 為過冷液體。
CONDENSER_BASE_ROWS = (
    ("pressure_pa", "冷凝壓力（絕對）", "2800", "P", "kPa"),
    ("inlet_temperature_k", "冷媒入口溫度", "70", "T", "°C"),
    ("outlet_temperature_k", "冷媒出口溫度", "35", "T", "°C"),
    ("mass_flow_kg_s", "冷媒質量流率", "0.05", "MassFlow", "kg/s"),
    ("dead_state_temperature_k", "死狀態（環境）溫度 T0", "25", "T", "°C"),
    ("boundary_temperature_k", "等效傳熱邊界溫度 T_b", "35", "T", "°C"),
)
# 選擇掃描變數時帶入的預設範圍：(起點, 終點, 單位)。
AXIS_DEFAULTS = {
    "evaporating_temperature_k": ("-10", "15", "°C"),
    "condensing_temperature_k": ("30", "60", "°C"),
    "superheat_k": ("0", "15", "K"),
    "subcooling_k": ("0", "15", "K"),
    "isentropic_efficiency": ("50", "90", "%"),
    "refrigeration_capacity_w": ("5", "20", "kW"),
    "pressure_pa": ("2400", "3200", "kPa"),
    "inlet_temperature_k": ("55", "85", "°C"),
    "outlet_temperature_k": ("25", "38", "°C"),
    "mass_flow_kg_s": ("0.02", "0.1", "kg/s"),
    "dead_state_temperature_k": ("10", "30", "°C"),
    "boundary_temperature_k": ("30", "40", "°C"),
}
# 敏感度的預設變動量：(數值, 單位)。
DELTA_DEFAULTS = {
    "evaporating_temperature_k": ("2", "K"),
    "condensing_temperature_k": ("2", "K"),
    "superheat_k": ("2", "K"),
    "subcooling_k": ("2", "K"),
    "isentropic_efficiency": ("5", "%"),
    "refrigeration_capacity_w": ("1", "kW"),
    "pressure_pa": ("50", "kPa"),
    "inlet_temperature_k": ("2", "K"),
    "outlet_temperature_k": ("2", "K"),
    "mass_flow_kg_s": ("0.005", "kg/s"),
    "dead_state_temperature_k": ("2", "K"),
    "boundary_temperature_k": ("2", "K"),
}
# 各性質在結果中的小數位數；無因次指標（COP、壓縮比）使用 NO_UNIT_DIGITS。
DIGITS = {"T": 1, "DeltaT": 1, "H": 1, "Power": 3, "MassFlow": 4, "VolumeFlow": 2, "P": 1,
          "Eff": 1, "EntropyFlow": 5}
NO_UNIT_DIGITS = 3
DEFAULT_METRIC = {CYCLE_TARGET.key: "cop_cooling", CONDENSER_EXERGY_TARGET.key: "exergy_efficiency"}
LOW_COLOR = "#2563EB"
HIGH_COLOR = "#EA580C"


class BatchModule(BaseAnalysisModule):
    """批次計算與比較的分析模組。"""

    def __init__(self, unit_converter: UnitConverter, page: ft.Page, batch_service: BatchService) -> None:
        """建立三種批次分析的表單與共用圖表。

參數：
    unit_converter: 共用單位轉換器。
    page: Flet 頁面。
    batch_service: 批次計算 application service。

回傳：
    無。"""
        super().__init__(unit_converter, page, batch_service=batch_service)
        self.batch = batch_service
        self.chart_panel = FigurePanel(height=480, placeholder="執行分析後顯示曲線或龍捲風圖")
        self.last_outcome: SweepOutcome | SensitivityOutcome | None = None
        self.targets: dict[str, ft.SegmentedButton] = {}
        self.boundaries: dict[str, ft.SegmentedButton] = {}
        self.dropdowns: dict[str, ft.Dropdown] = {}
        # 只屬於某計算對象的控制項（(表單前綴, 對象代碼) → 控制項），以及每個掃描軸的範圍欄位。
        self._target_groups: dict[tuple[str, str], list[ft.Control]] = {}
        self._axis_controls: dict[str, list[ft.Control]] = {}
        self.sweep_ui: ft.Container | None = None
        self.compare_ui: ft.Container | None = None
        self.sensitivity_ui: ft.Container | None = None
        self.sweep_ui = self._build_sweep_ui()
        self.compare_ui = self._build_compare_ui()
        self.sensitivity_ui = self._build_sensitivity_ui()

    # ======================================================
    # 註冊
    # ======================================================
    def get_analysis_definitions(self) -> dict:
        """回報此模組提供的批次分析。

回傳：
    以分析名稱為鍵的註冊定義。"""
        return {
            "參數掃描": {
                "analysis_id": "batch.parameter_sweep",
                "ui": self.sweep_ui,
                "calc_func": self.calculate_sweep,
                "result_chart": self.chart_panel,
            },
            "冷媒比較": {
                "analysis_id": "batch.refrigerant_comparison",
                "ui": self.compare_ui,
                "calc_func": self.calculate_comparison,
                "result_chart": self.chart_panel,
            },
            "敏感度分析（龍捲風圖）": {
                "analysis_id": "batch.sensitivity",
                "ui": self.sensitivity_ui,
                "calc_func": self.calculate_sensitivity,
                "result_chart": self.chart_panel,
            },
        }

    # ======================================================
    # 共用表單元件
    # ======================================================
    @staticmethod
    def _labelled(label: str, control: ft.Control) -> ft.Column:
        """在控制項上方加欄名。

參數：
    label: 欄名。
    control: 控制項。

回傳：
    欄位 Column。"""
        return ft.Column([ft.Text(label, size=TOKENS.body, weight=ft.FontWeight.W_500,
                                  color=TOKENS.text_primary), control], spacing=6)

    def _dropdown(self, key: str, options: list[tuple[str, str]], on_select=None) -> ft.Dropdown:
        """建立單選下拉選單並以 key 保存。

參數：
    key: 識別鍵。
    options: (值, 顯示文字) 清單；第一項為預設。
    on_select: 選用的變更處理器。

回傳：
    Dropdown。"""
        dropdown = style_dropdown(ft.Dropdown(
            options=[ft.dropdown.Option(value, text) for value, text in options],
            value=options[0][0], expand=True, on_select=on_select,
        ))
        self.dropdowns[key] = dropdown
        return dropdown

    @staticmethod
    def _segmented(options: list[tuple[str, str]], on_change) -> ft.SegmentedButton:
        """建立單選分段按鈕。

參數：
    options: (值, 顯示文字) 清單；第一項為預設。
    on_change: 變更處理器。

回傳：
    SegmentedButton。"""
        return ft.SegmentedButton(
            allow_empty_selection=False,
            show_selected_icon=False,
            segments=[ft.Segment(value=value, label=ft.Text(label)) for value, label in options],
            selected=[options[0][0]],
            on_change=on_change,
        )

    def _target_selector(self, prefix: str) -> ft.SegmentedButton:
        """建立計算對象選擇（冷凍循環／冷凝器 Exergy）。

參數：
    prefix: 表單識別鍵前綴。

回傳：
    SegmentedButton。"""
        selector = self._segmented(
            # 輸入欄較窄，使用短標籤避免折行；欄名說明冷凝器為 Exergy 分析。
            [(CYCLE_TARGET.key, "冷凍循環"), (CONDENSER_EXERGY_TARGET.key, "冷凝器")],
            lambda _event: self._refresh_target(prefix))
        self.targets[prefix] = selector
        return selector

    def target(self, prefix: str) -> BatchTarget:
        """目前選擇的計算對象。

參數：
    prefix: 表單識別鍵前綴。

回傳：
    BatchTarget；沒有對象選擇的表單（冷媒比較）固定為冷凍循環。"""
        selector = self.targets.get(prefix)
        if selector is not None and CONDENSER_EXERGY_TARGET.key in selector.selected:
            return CONDENSER_EXERGY_TARGET
        return CYCLE_TARGET

    def boundary_at_dead_state(self, prefix: str) -> bool:
        """冷凝器 Exergy 是否採「整體排熱至環境」（T_b = T0）。

參數：
    prefix: 表單識別鍵前綴。

回傳：
    bool。"""
        return BOUNDARY_AMBIENT in self.boundaries[prefix].selected

    def _base_rows(self, prefix: str, *, with_fluid: bool = True, condenser: bool = True) -> list[ft.Control]:
        """建立基準條件欄位：冷媒、冷凍循環條件與（選用的）冷凝器 Exergy 條件。

參數：
    prefix: 表單識別鍵前綴。
    with_fluid: 是否包含單一冷媒欄位。
    condenser: 是否包含冷凝器 Exergy 條件。

回傳：
    控制項清單。"""
        controls: list[ft.Control] = []
        if with_fluid:
            controls.append(self.create_fluid_row(f"{prefix}_fluid", "冷媒", "R32", "例如 R32、R410A、R134a"))
        controls.append(self.section_label("基準條件（冷凍循環）"))
        cycle_rows = [self.create_input_row(f"{prefix}_{key}", label, default, prop, unit)["ui_row"]
                      for key, label, default, prop, unit in CYCLE_BASE_ROWS]
        self._group(prefix, CYCLE_TARGET.key, [controls[-1], *cycle_rows])
        controls.extend(cycle_rows)
        if condenser:
            title = self.section_label("基準條件（冷凝器 Exergy，忽略壓降）")
            boundary = self._segmented(
                # 預設指定 T_b：整體排熱至環境時 T_b = T0，Exergy 效率恆為 0，不適合作為預設比較。
                [(BOUNDARY_CUSTOM, "指定 T_b"), (BOUNDARY_AMBIENT, "T_b = T0")],
                lambda _event: self._refresh_target(prefix))
            self.boundaries[prefix] = boundary
            condenser_rows = [self.create_input_row(f"{prefix}_{key}", label, default, prop, unit)["ui_row"]
                              for key, label, default, prop, unit in CONDENSER_BASE_ROWS]
            boundary_row = self._labelled("等效傳熱邊界溫度（T_b = T0 表示整體排熱至環境）", boundary)
            self._group(prefix, CONDENSER_EXERGY_TARGET.key, [title, *condenser_rows, boundary_row])
            controls.extend([title, *condenser_rows[:-1], boundary_row, condenser_rows[-1]])
        self.bind_independent_unit_sync([key for key in self.all_entries if key.startswith(f"{prefix}_")])
        return controls

    def _group(self, prefix: str, target_key: str, controls: list[ft.Control]) -> None:
        """記錄只屬於某計算對象的控制項，切換對象時一起顯示或隱藏。

參數：
    prefix: 表單識別鍵前綴。
    target_key: 計算對象代碼。
    controls: 控制項。

回傳：
    無。"""
        self._target_groups.setdefault((prefix, target_key), []).extend(controls)

    def _refresh_target(self, prefix: str) -> None:
        """依計算對象切換基準條件、變數與指標選項。

參數：
    prefix: 表單識別鍵前綴。

回傳：
    無。"""
        target = self.target(prefix)
        for (group_prefix, target_key), controls in self._target_groups.items():
            if group_prefix == prefix:
                for control in controls:
                    control.visible = target_key == target.key
        if prefix in self.boundaries and target is CONDENSER_EXERGY_TARGET:
            self.all_entries[f"{prefix}_boundary_temperature_k"]["ui_row"].visible = \
                not self.boundary_at_dead_state(prefix)
        refresher = {"sw": self._refresh_sweep_options, "se": self._refresh_sensitivity_rows}.get(prefix)
        if refresher is not None:
            refresher()
        container = {"sw": self.sweep_ui, "se": self.sensitivity_ui}.get(prefix)
        if container is not None:
            self._update_controls(container)

    def _variables(self, prefix: str) -> tuple[BatchVariable, ...]:
        """目前計算對象可變動的輸入（T_b 隨 T0 時不含 T_b）。

參數：
    prefix: 表單識別鍵前綴。

回傳：
    BatchVariable tuple。"""
        target = self.target(prefix)
        if target is CONDENSER_EXERGY_TARGET and self.boundary_at_dead_state(prefix):
            return tuple(variable for variable in target.variables if variable.key != "boundary_temperature_k")
        return target.variables

    @staticmethod
    def _metric_options(target: BatchTarget) -> list[tuple[str, str]]:
        """指標選單選項（預設指標排第一）。

參數：
    target: 計算對象。

回傳：
    (值, 顯示文字) 清單。"""
        default = DEFAULT_METRIC[target.key]
        metrics = sorted(target.metrics, key=lambda metric: metric.key != default)
        return [(metric.key, metric.label) for metric in metrics]

    @staticmethod
    def _set_options(dropdown: ft.Dropdown, options: list[tuple[str, str]], default: str | None = None) -> bool:
        """更新下拉選項；目前值不在新選項中時改為 default（未指定時為第一項）。

參數：
    dropdown: 下拉選單。
    options: (值, 顯示文字) 清單。
    default: 目前值失效時使用的值。

回傳：
    目前值是否因此改變。"""
        dropdown.options = [ft.dropdown.Option(value, text) for value, text in options]
        if dropdown.value in {value for value, _ in options}:
            return False
        dropdown.value = default if default is not None else options[0][0]
        return True

    # ------------------------------------------------------
    # 掃描軸
    # ------------------------------------------------------
    def _axis_rows(self, prefix: str, axis: str, label: str, *, optional: bool) -> list[ft.Control]:
        """建立一個掃描軸：變數選單、起點、終點與點數。

參數：
    prefix: 表單識別鍵前綴。
    axis: 軸代號（``x`` 或 ``y``）。
    label: 變數選單欄名。
    optional: 是否可選「不掃描」。

回傳：
    控制項清單。"""
        key = f"{prefix}_{axis}"
        dropdown = self._dropdown(key, [(NO_AXIS, "不掃描")] if optional else [("", "")],
                                  on_select=lambda _event: self._on_axis_change(prefix, axis))
        start = self.create_input_row(f"{key}_start", "起點", "0", "T", "°C")
        stop = self.create_input_row(f"{key}_stop", "終點", "0", "T", "°C")
        self.create_text_row(f"{key}_count", "點數", "7", f"2–{MAX_AXIS_POINTS}")
        self.bind_independent_unit_sync([f"{key}_start", f"{key}_stop"])
        count_row = self.text_entries[f"{key}_count"]["ui_row"]
        self._axis_controls[key] = [start["ui_row"], stop["ui_row"], count_row]
        return [self._labelled(label, dropdown), start["ui_row"], stop["ui_row"], count_row]

    def _axis_variable(self, prefix: str, axis: str) -> str | None:
        """掃描軸目前的變數；選「不掃描」時為 None。

參數：
    prefix: 表單識別鍵前綴。
    axis: 軸代號。

回傳：
    request 欄位名稱或 None。"""
        value = self.dropdowns[f"{prefix}_{axis}"].value
        return None if value in (None, "", NO_AXIS) else value

    def _on_axis_change(self, prefix: str, axis: str) -> None:
        """變更掃描變數：起終點改為該變數的物理量並帶入預設範圍。

參數：
    prefix: 表單識別鍵前綴。
    axis: 軸代號。

回傳：
    無。"""
        self._apply_axis(prefix, axis)
        container = {"sw": self.sweep_ui, "rc": self.compare_ui}[prefix]
        self._update_controls(container)

    def _apply_axis(self, prefix: str, axis: str) -> None:
        """依掃描變數設定起終點欄位（性質、單位與預設範圍）並切換顯示。

參數：
    prefix: 表單識別鍵前綴。
    axis: 軸代號。

回傳：
    無。"""
        key = f"{prefix}_{axis}"
        variable_key = self._axis_variable(prefix, axis)
        for control in self._axis_controls[key]:
            control.visible = variable_key is not None
        if variable_key is None:
            return
        variable = self.target(prefix).variable(variable_key)
        start, stop, unit = AXIS_DEFAULTS[variable_key]
        for suffix, value in (("start", start), ("stop", stop)):
            entry_key = f"{key}_{suffix}"
            self.retarget_input_row(entry_key, variable.prop_code, unit)
            self.all_entries[entry_key]["val"].value = value
        self.all_entries[f"{key}_start"]["label_control"].value = f"{variable.label}起點"
        self.all_entries[f"{key}_stop"]["label_control"].value = f"{variable.label}終點"

    def _read_axis(self, prefix: str, axis: str) -> SweepAxisRequest | None:
        """讀取掃描軸。

參數：
    prefix: 表單識別鍵前綴。
    axis: 軸代號。

回傳：
    SweepAxisRequest；選「不掃描」時為 None。

引發：
    ValueError：點數不是整數或範圍無效時。"""
        variable = self._axis_variable(prefix, axis)
        if variable is None:
            return None
        key = f"{prefix}_{axis}"
        raw_count = self.read_text(f"{key}_count")
        try:
            count = int(raw_count)
        except ValueError:
            raise ValueError(f"「點數」請輸入整數（目前為「{raw_count}」）。") from None
        values = linear_values(self.read_si(f"{key}_start"), self.read_si(f"{key}_stop"), count)
        return SweepAxisRequest(variable, values)

    # ------------------------------------------------------
    # 基準 request
    # ------------------------------------------------------
    def _cycle_request(self, prefix: str, fluid: str) -> RefrigerationCycleRequest:
        """讀取冷凍循環基準條件。

參數：
    prefix: 表單識別鍵前綴。
    fluid: 冷媒。

回傳：
    RefrigerationCycleRequest（reference state 由批次服務統一使用 Auto）。"""
        return RefrigerationCycleRequest(fluid=fluid, **{
            key: self.read_si(f"{prefix}_{key}") for key, *_ in CYCLE_BASE_ROWS})

    def _condenser_request(self, prefix: str) -> CondenserExergyRequest:
        """讀取冷凝器 Exergy 基準條件；T_b 隨 T0 時以 T0 作為 T_b。

參數：
    prefix: 表單識別鍵前綴。

回傳：
    CondenserExergyRequest。"""
        values = {key: self.read_si(f"{prefix}_{key}") for key, *_ in CONDENSER_BASE_ROWS
                  if key != "boundary_temperature_k"}
        values["boundary_temperature_k"] = (
            values["dead_state_temperature_k"] if self.boundary_at_dead_state(prefix)
            else self.read_si(f"{prefix}_boundary_temperature_k"))
        return CondenserExergyRequest(fluid=self.read_text(f"{prefix}_fluid"), **values)

    def _base_request(self, prefix: str):
        """依計算對象讀取基準 request。

參數：
    prefix: 表單識別鍵前綴。

回傳：
    RefrigerationCycleRequest 或 CondenserExergyRequest。"""
        if self.target(prefix) is CONDENSER_EXERGY_TARGET:
            return self._condenser_request(prefix)
        return self._cycle_request(prefix, self.read_text(f"{prefix}_fluid"))

    # ======================================================
    # 表單
    # ======================================================
    def _build_sweep_ui(self) -> ft.Container:
        """建立參數掃描表單。

回傳：
    預設隱藏的表單容器。"""
        prefix = "sw"
        controls: list[ft.Control] = [self._labelled("計算對象（冷凝器為 Exergy 分析）", self._target_selector(prefix))]
        controls.extend(self._base_rows(prefix))
        controls.append(self.section_label("掃描設定"))
        controls.extend(self._axis_rows(prefix, "x", "掃描變數（曲線橫軸）", optional=False))
        controls.extend(self._axis_rows(prefix, "y", "第二變數（選填，每個數值一條曲線）", optional=True))
        controls.append(self._labelled("輸出指標", self._dropdown(f"{prefix}_metric", [("", "")])))
        container = ft.Container(content=ft.Column(controls, spacing=12), visible=False)
        self.sweep_ui = container
        self._refresh_target(prefix)
        self._apply_axis(prefix, "y")
        return container

    def _refresh_sweep_options(self) -> None:
        """依計算對象更新掃描變數與指標選項。

回傳：
    無。"""
        target = self.target("sw")
        variables = [(variable.key, variable.label) for variable in self._variables("sw")]
        # 冷凍循環預設掃描冷凝溫度（最常見的 COP 對冷凝溫度曲線）；只有目前的變數失效時才重設範圍。
        if self._set_options(self.dropdowns["sw_x"], variables,
                             "condensing_temperature_k" if target is CYCLE_TARGET else None):
            self._apply_axis("sw", "x")
        if self._set_options(self.dropdowns["sw_y"], [(NO_AXIS, "不掃描"), *variables]):
            self._apply_axis("sw", "y")
        self._set_options(self.dropdowns["sw_metric"], self._metric_options(target))

    def _build_compare_ui(self) -> ft.Container:
        """建立冷媒比較表單（冷凍循環）。

回傳：
    預設隱藏的表單容器。"""
        prefix = "rc"
        self.create_text_row("rc_fluids", "比較的冷媒（以逗號分隔）", "R32, R410A, R134a, R290",
                             "至少兩種，例如 R32, R134a")
        controls: list[ft.Control] = [
            self.text_entries["rc_fluids"]["ui_row"],
            ft.Text("冷媒比較只用於冷凍循環：同一組飽和溫度、過熱、過冷與效率條件下換冷媒。"
                    "冷凝器 Exergy 的輸入是某一冷媒的量測壓力與溫度，換冷媒後不是同條件比較。",
                    size=TOKENS.caption, color=TOKENS.text_muted),
        ]
        controls.extend(self._base_rows(prefix, with_fluid=False, condenser=False))
        variables = [(variable.key, variable.label) for variable in CYCLE_TARGET.variables]
        controls.append(self.section_label("比較方式"))
        controls.extend(self._axis_rows(prefix, "x", "掃描變數（每種冷媒一條曲線，選填）", optional=True))
        self._set_options(self.dropdowns["rc_x"], [(NO_AXIS, "不掃描"), *variables])
        controls.append(self._labelled("輸出指標", self._dropdown("rc_metric", self._metric_options(CYCLE_TARGET))))
        container = ft.Container(content=ft.Column(controls, spacing=12), visible=False)
        self.compare_ui = container
        self._apply_axis(prefix, "x")
        return container

    def _build_sensitivity_ui(self) -> ft.Container:
        """建立敏感度分析表單：每個輸入一個變動量（0 表示不分析）。

回傳：
    預設隱藏的表單容器。"""
        prefix = "se"
        controls: list[ft.Control] = [self._labelled("計算對象（冷凝器為 Exergy 分析）", self._target_selector(prefix))]
        controls.extend(self._base_rows(prefix))
        controls.append(self.section_label("變動量（基準值 ± 變動量；0 表示不分析此輸入）"))
        self.delta_keys: dict[str, str] = {}
        for target in (CYCLE_TARGET, CONDENSER_EXERGY_TARGET):
            rows = []
            for variable in target.variables:
                value, unit = DELTA_DEFAULTS[variable.key]
                key = f"se_{target.key}_d_{variable.key}"
                self.delta_keys[f"{target.key}:{variable.key}"] = key
                rows.append(self.create_input_row(key, f"{variable.label} ±", value, variable.delta_prop_code,
                                                  unit)["ui_row"])
            self._group(prefix, target.key, rows)
            controls.extend(rows)
        self.bind_independent_unit_sync(list(self.delta_keys.values()))
        controls.append(self._labelled("比較指標", self._dropdown("se_metric", [("", "")])))
        container = ft.Container(content=ft.Column(controls, spacing=12), visible=False)
        self.sensitivity_ui = container
        self._refresh_target(prefix)
        return container

    def _refresh_sensitivity_rows(self) -> None:
        """依計算對象更新指標選項，並在 T_b 隨 T0 時隱藏 T_b 的變動量。

回傳：
    無。"""
        target = self.target("se")
        self._set_options(self.dropdowns["se_metric"], self._metric_options(target))
        if target is CONDENSER_EXERGY_TARGET:
            key = self.delta_keys[f"{target.key}:boundary_temperature_k"]
            self.all_entries[key]["ui_row"].visible = not self.boundary_at_dead_state("se")

    # ======================================================
    # 格式化
    # ======================================================
    def _format_quantity(self, formatter: ResultFormatter, prop_code: str | None, value: float) -> str:
        """把 SI 數值格式化為目前輸出單位的「數值 單位」。

參數：
    formatter: 結果格式化器。
    prop_code: 性質代碼；None 表示無因次。
    value: SI 數值。

回傳：
    文字。"""
        if prop_code is None:
            return f"{value:.{NO_UNIT_DIGITS}f}"
        return formatter.quantity(prop_code, value, DIGITS.get(prop_code, 2))

    def _format_input(self, formatter: ResultFormatter, target: BatchTarget, variable: str, value) -> str:
        """格式化一個輸入值（冷媒名稱原樣輸出）。

參數：
    formatter: 結果格式化器。
    target: 計算對象。
    variable: 輸入欄位名稱。
    value: 輸入值。

回傳：
    文字。"""
        if variable == FLUID_VARIABLE:
            return str(value)
        return self._format_quantity(formatter, target.variable(variable).prop_code, value)

    def _position(self, formatter: ResultFormatter, target: BatchTarget, point: BatchPoint,
                  variables: list[str]) -> str:
        """以簡短符號描述一個點的位置（只含非中文字元，供數值欄位使用）。

參數：
    formatter: 結果格式化器。
    target: 計算對象。
    point: 批次點。
    variables: 掃描變數。

回傳：
    例如 ``T_c = 45.0 °C, R32``。"""
        parts = []
        for variable in variables:
            value = self._format_input(formatter, target, variable, point.inputs[variable])
            parts.append(value if variable == FLUID_VARIABLE else f"{target.variable(variable).symbol} = {value}")
        return ", ".join(parts)

    def _chart_value(self, formatter: ResultFormatter, prop_code: str | None, value: float | None) -> float:
        """把 SI 數值換成圖表使用的輸出單位數值；失敗點為 NaN（圖上斷線）。

參數：
    formatter: 結果格式化器。
    prop_code: 性質代碼；None 表示無因次。
    value: SI 數值或 None。

回傳：
    數值。"""
        if value is None:
            return nan
        if prop_code is None:
            return value
        return self.unit_converter.convert_from_si(prop_code, value, formatter.unit(prop_code))

    def _axis_title(self, formatter: ResultFormatter, label: str, prop_code: str | None) -> str:
        """圖表座標軸標題。

參數：
    formatter: 結果格式化器。
    label: 名稱。
    prop_code: 性質代碼；None 表示無因次。

回傳：
    例如「冷凝溫度 [°C]」。"""
        return label if prop_code is None else f"{label} [{formatter.unit(prop_code)}]"

    def _sweep_text(self, outcome: SweepOutcome, metric: BatchMetric, formatter: ResultFormatter) -> str:
        """把掃描結果寫成「名稱: 數值」文字：摘要、每條曲線的數值與無法計算的點。

參數：
    outcome: 掃描結果。
    metric: 指標。
    formatter: 結果格式化器。

回傳：
    結果文字。"""
        target, result = outcome.target, outcome.result
        variables = [axis.variable for axis in result.axes]
        succeeded = result.succeeded
        formatter.section("摘要")
        formatter.add_text("計算點數", f"{len(succeeded)} / {len(result.points)}")
        if succeeded:
            best = max(succeeded, key=lambda point: point.metrics[metric.key])
            worst = min(succeeded, key=lambda point: point.metrics[metric.key])
            formatter.add_text("最大值", self._format_quantity(formatter, metric.prop_code, best.metrics[metric.key]))
            formatter.add_text("最大值位置", self._position(formatter, target, best, variables))
            formatter.add_text("最小值", self._format_quantity(formatter, metric.prop_code, worst.metrics[metric.key]))
            formatter.add_text("最小值位置", self._position(formatter, target, worst, variables))
        x_variable = variables[0]
        for group, values in result.series(metric.key):
            if group is None:
                formatter.section(metric.label)
            elif len(variables) > 1 and variables[1] == FLUID_VARIABLE:
                formatter.section(f"{metric.label}（{group}）")
            else:
                name = target.variable(variables[1]).label
                formatter.section(f"{metric.label}（{name} {self._format_input(formatter, target, variables[1], group)}）")
            for x_value, value in values:
                x_text = self._format_input(formatter, target, x_variable, x_value)
                label = x_text if x_variable == FLUID_VARIABLE else f"{target.variable(x_variable).label} {x_text}"
                formatter.add_text(label, "-" if value is None else
                                   self._format_quantity(formatter, metric.prop_code, value))
        if result.failed:
            formatter.section("無法計算的點")
            for point in result.failed:
                where = "、".join(
                    self._format_input(formatter, target, variable, point.inputs[variable])
                    if variable == FLUID_VARIABLE else
                    f"{target.variable(variable).label} {self._format_input(formatter, target, variable, point.inputs[variable])}"
                    for variable in variables)
                formatter.lines.append(f"{where}：{point.error}")
        return formatter.text()

    # ======================================================
    # 圖表
    # ======================================================
    def _plot_sweep(self, outcome: SweepOutcome, metric: BatchMetric, formatter: ResultFormatter) -> None:
        """畫掃描曲線（橫軸為第一軸）；第一軸是冷媒時畫長條圖。

參數：
    outcome: 掃描結果。
    metric: 指標。
    formatter: 結果格式化器。

回傳：
    無。"""
        target, result = outcome.target, outcome.result
        variables = [axis.variable for axis in result.axes]
        figure = self.chart_panel.figure
        figure.clear()
        # 圖表面板會依畫面寬度調整 figure 尺寸；constrained layout 在每次重繪時重新配置，座標軸標題不會被裁掉。
        figure.set_layout_engine("constrained")
        axes = figure.add_subplot(111)
        series = result.series(metric.key)
        if variables[0] == FLUID_VARIABLE:
            (_, values), = series
            names = [str(name) for name, _ in values]
            heights = [self._chart_value(formatter, metric.prop_code, value) for _, value in values]
            axes.bar(names, heights, color=TOKENS.primary)
            for index, height in enumerate(heights):
                if height == height:  # NaN 不標示
                    axes.annotate(self._format_quantity(formatter, metric.prop_code, values[index][1]),
                                  (index, height), ha="center", va="bottom", fontsize=9)
            axes.set_xlabel("冷媒")
        else:
            x_variable = target.variable(variables[0])
            for group, values in series:
                xs = [self._chart_value(formatter, x_variable.prop_code, x) for x, _ in values]
                ys = [self._chart_value(formatter, metric.prop_code, value) for _, value in values]
                if group is None:
                    label = None
                elif variables[1] == FLUID_VARIABLE:
                    label = str(group)
                else:
                    label = f"{target.variable(variables[1]).symbol} = " \
                            f"{self._format_input(formatter, target, variables[1], group)}"
                axes.plot(xs, ys, marker="o", markersize=4, linewidth=1.6, label=label)
            axes.set_xlabel(self._axis_title(formatter, x_variable.label, x_variable.prop_code))
            if len(series) > 1:
                axes.legend(fontsize=8)
        axes.set_ylabel(self._axis_title(formatter, metric.label, metric.prop_code))
        axes.grid(True, alpha=0.3)
        self.chart_panel.refresh()

    def _plot_tornado(self, outcome: SensitivityOutcome, metric: BatchMetric, formatter: ResultFormatter) -> None:
        """畫龍捲風圖：每個輸入一列，由基準值畫到 −Δ 與 +Δ 時的指標值；影響最大者在最上方。

參數：
    outcome: 敏感度結果。
    metric: 指標。
    formatter: 結果格式化器。

回傳：
    無。"""
        target, result = outcome.target, outcome.result
        base = self._chart_value(formatter, metric.prop_code, result.base_value)
        figure = self.chart_panel.figure
        figure.clear()
        # 圖表面板會依畫面寬度調整 figure 尺寸；constrained layout 在每次重繪時重新配置，座標軸標題不會被裁掉。
        figure.set_layout_engine("constrained")
        axes = figure.add_subplot(111)
        rows = list(reversed(result.rows))
        labels = []
        for index, row in enumerate(rows):
            variable = target.variable(row.variable)
            delta = self._format_quantity(formatter, variable.delta_prop_code, row.delta)
            labels.append(f"{variable.label} ± {delta}")
            for point, color, name in ((row.low, LOW_COLOR, "−Δ"), (row.high, HIGH_COLOR, "+Δ")):
                value = self._chart_value(formatter, metric.prop_code, row.metric(point, metric.key))
                if value == value:
                    axes.barh(index, value - base, left=base, color=color, height=0.6,
                              label=name if index == 0 else None)
        axes.axvline(base, color="#374151", linewidth=1)
        axes.set_yticks(range(len(rows)), labels)
        axes.set_xlabel(self._axis_title(formatter, metric.label, metric.prop_code))
        axes.legend(fontsize=8, loc="lower right")
        axes.grid(True, axis="x", alpha=0.3)
        self.chart_panel.refresh()

    # ======================================================
    # 計算
    # ======================================================
    def calculate_sweep(self, use_imperial: bool) -> str:
        """執行參數掃描並畫曲線。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。

引發：
    ValueError：輸入無效時。"""
        self.last_outcome = None
        prefix = "sw"
        axes = [self._read_axis(prefix, "x")]
        second = self._read_axis(prefix, "y")
        if second is not None:
            axes.append(second)
        target = self.target(prefix)
        outcome = self.batch.sweep(ParameterSweepRequest(
            self._base_request(prefix), tuple(axes),
            boundary_at_dead_state=target is CONDENSER_EXERGY_TARGET and self.boundary_at_dead_state(prefix)))
        return self._finish_sweep(outcome, self.dropdowns["sw_metric"].value, use_imperial)

    def calculate_comparison(self, use_imperial: bool) -> str:
        """執行冷媒比較（可另掃描一個輸入）並畫長條圖或曲線。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。

引發：
    ValueError：輸入無效時。"""
        self.last_outcome = None
        fluids = tuple(name.strip() for name in self.read_text("rc_fluids").split(",") if name.strip())
        outcome = self.batch.compare_refrigerants(RefrigerantComparisonRequest(
            self._cycle_request("rc", fluids[0] if fluids else ""), fluids, self._read_axis("rc", "x")))
        return self._finish_sweep(outcome, self.dropdowns["rc_metric"].value, use_imperial)

    def _finish_sweep(self, outcome: SweepOutcome, metric_key: str, use_imperial: bool) -> str:
        """保存結果、畫圖並回傳文字；所有點都失敗時視為錯誤。

參數：
    outcome: 掃描結果。
    metric_key: 指標名稱。
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。

引發：
    ValueError：所有點都無法計算時（附第一個原因）。"""
        result = outcome.result
        if not result.succeeded:
            raise ValueError(f"所有點都無法計算：{result.points[0].error}")
        metric = outcome.target.metric(metric_key)
        formatter = ResultFormatter(self.unit_converter, use_imperial)
        self._plot_sweep(outcome, metric, formatter)
        self.last_outcome = outcome
        return self._sweep_text(outcome, metric, formatter)

    def calculate_sensitivity(self, use_imperial: bool) -> str:
        """執行單因子敏感度分析並畫龍捲風圖。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。

引發：
    ValueError：輸入無效、沒有任何變動量或基準條件無法計算時。"""
        self.last_outcome = None
        prefix = "se"
        target = self.target(prefix)
        follows = target is CONDENSER_EXERGY_TARGET and self.boundary_at_dead_state(prefix)
        perturbations = []
        for variable in self._variables(prefix):
            key = self.delta_keys[f"{target.key}:{variable.key}"]
            delta = self.read_si(key)
            if delta < 0:
                raise ValueError(f"「{variable.label} ±」不可為負值。")
            if delta > 0:
                perturbations.append((variable.key, delta))
        outcome = self.batch.sensitivity(SensitivityRequest(
            self._base_request(prefix), tuple(perturbations), self.dropdowns["se_metric"].value,
            boundary_at_dead_state=follows))
        metric = target.metric(outcome.result.metric)
        formatter = ResultFormatter(self.unit_converter, use_imperial)
        self._plot_tornado(outcome, metric, formatter)
        self.last_outcome = outcome
        return self._sensitivity_text(outcome, metric, formatter)

    def _sensitivity_text(self, outcome: SensitivityOutcome, metric: BatchMetric,
                          formatter: ResultFormatter) -> str:
        """敏感度結果文字：基準值、影響最大的輸入，以及每個輸入 ±Δ 時的指標值與變化量。

參數：
    outcome: 敏感度結果。
    metric: 指標。
    formatter: 結果格式化器。

回傳：
    結果文字。"""
        target, result = outcome.target, outcome.result
        formatter.section("摘要")
        formatter.add_text("基準值", self._format_quantity(formatter, metric.prop_code, result.base_value))
        top = result.rows[0]
        formatter.add_text("影響最大", target.variable(top.variable).symbol)
        formatter.add_text("最大變化幅度", self._format_quantity(formatter, metric.prop_code, result.swing(top))
                           if metric.prop_code != "T" else formatter.quantity("DeltaT", result.swing(top), 1))
        failures = []
        for row in result.rows:
            variable = target.variable(row.variable)
            delta = self._format_quantity(formatter, variable.delta_prop_code, row.delta)
            formatter.section(f"{variable.label}（± {delta}）")
            for point, sign in ((row.low, "−"), (row.high, "+")):
                value = row.metric(point, metric.key)
                if value is None:
                    formatter.add_text(f"{sign}Δ 時的{metric.label}", "-")
                    failures.append(f"{variable.label} {sign}{delta}：{point.error}")
                    continue
                formatter.add_text(f"{sign}Δ 時的{metric.label}",
                                   self._format_quantity(formatter, metric.prop_code, value))
        if failures:
            formatter.section("無法計算的變動")
            formatter.lines.extend(failures)
        return formatter.text()
