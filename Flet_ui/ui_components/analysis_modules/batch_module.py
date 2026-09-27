"""批次計算與比較：參數掃描、冷媒比較、敏感度分析（龍捲風圖）。

計算委派給 `BatchService`（冷凍循環與冷凝器 Exergy 的結構化結果）；本模組負責表單、
輸入讀取與計算流程，結果文字與圖表由 `batch_presentation.BatchPresenter` 產生。每項分析以
兩段式計算註冊（``prepare_func``）：UI 執行緒讀取並驗證輸入、建立不可變的 request；背景
只呼叫 application service；結果仍屬於目前這一輪時才在 UI 執行緒畫圖與產生文字。
指標都與 reference state 無關，因此不提供 Reference State 選單。
無法計算的點不會中斷整批計算，列在結果最後並附原因；圖上以斷線表示。
"""

from __future__ import annotations

from functools import partial

import flet as ft

from application.batch import (
    CONDENSER_EXERGY_TARGET,
    CYCLE_TARGET,
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
from domain.batch import MAX_AXIS_POINTS, linear_values

from ...ui.analysis_definition import PreparedCalculation
from ...ui.components.figure_panel import FigurePanel
from ...ui.theme import TOKENS, style_dropdown
from ..unit.UnitConverter import UnitConverter
from .base_analysis_module import BaseAnalysisModule
from .batch_presentation import BatchPresenter

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
DEFAULT_METRIC = {CYCLE_TARGET.key: "cop_cooling", CONDENSER_EXERGY_TARGET.key: "exergy_efficiency"}


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
                "prepare_func": self.prepare_sweep,
                "result_chart": self.chart_panel,
            },
            "冷媒比較": {
                "analysis_id": "batch.refrigerant_comparison",
                "ui": self.compare_ui,
                "prepare_func": self.prepare_comparison,
                "result_chart": self.chart_panel,
            },
            "敏感度分析（龍捲風圖）": {
                "analysis_id": "batch.sensitivity",
                "ui": self.sensitivity_ui,
                "prepare_func": self.prepare_sensitivity,
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
    # 計算：prepare（UI 執行緒）→ compute（背景）→ publish（UI 執行緒）
    # ======================================================
    def prepare_sweep(self, use_imperial: bool) -> PreparedCalculation:
        """讀取並驗證參數掃描的輸入，建立不可變的 request。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    PreparedCalculation；compute 只呼叫 application service。

引發：
    ValueError：輸入無效時。"""
        prefix = "sw"
        axes = [self._read_axis(prefix, "x")]
        second = self._read_axis(prefix, "y")
        if second is not None:
            axes.append(second)
        target = self.target(prefix)
        request = ParameterSweepRequest(
            self._base_request(prefix), tuple(axes), self.dropdowns["sw_metric"].value,
            boundary_at_dead_state=target is CONDENSER_EXERGY_TARGET and self.boundary_at_dead_state(prefix))
        return PreparedCalculation(
            compute=partial(self.batch.sweep, request),
            publish=partial(self._publish_sweep, use_imperial=use_imperial),
        )

    def prepare_comparison(self, use_imperial: bool) -> PreparedCalculation:
        """讀取並驗證冷媒比較的輸入；清單中的空白項目（例如連續逗號）視為輸入錯誤。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    PreparedCalculation。

引發：
    ValueError：輸入無效時。"""
        names = [name.strip() for name in self.read_text("rc_fluids").split(",")]
        if any(not name for name in names):
            raise ValueError("「比較的冷媒」有空白項目（例如連續或結尾的逗號）；請刪除多餘的逗號。")
        fluids = tuple(names)
        request = RefrigerantComparisonRequest(
            self._cycle_request("rc", fluids[0]), fluids, self.dropdowns["rc_metric"].value,
            self._read_axis("rc", "x"))
        return PreparedCalculation(
            compute=partial(self.batch.compare_refrigerants, request),
            publish=partial(self._publish_sweep, use_imperial=use_imperial),
        )

    def prepare_sensitivity(self, use_imperial: bool) -> PreparedCalculation:
        """讀取並驗證敏感度分析的輸入；變動量 0 的輸入不分析。

參數：
    use_imperial: 是否以英制輸出。

回傳：
    PreparedCalculation。

引發：
    ValueError：輸入無效（例如變動量為負）時。"""
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
        request = SensitivityRequest(
            self._base_request(prefix), tuple(perturbations), self.dropdowns["se_metric"].value,
            boundary_at_dead_state=follows)
        return PreparedCalculation(
            compute=partial(self.batch.sensitivity, request),
            publish=partial(self._publish_sensitivity, use_imperial=use_imperial),
        )

    def _publish_sweep(self, outcome: SweepOutcome, *, use_imperial: bool) -> str:
        """在 UI 執行緒畫圖、保存結果並回傳文字；所有點都失敗時視為錯誤。

參數：
    outcome: 掃描結果。
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。

引發：
    ValueError：所有點都無法計算時（附第一個原因）。"""
        self.last_outcome = None
        result = outcome.result
        if not result.succeeded:
            raise ValueError(f"所有點都無法計算：{result.points[0].error}")
        presenter = BatchPresenter(self.unit_converter, use_imperial)
        presenter.plot_sweep(self.chart_panel.figure, outcome)
        self.chart_panel.refresh()
        self.last_outcome = outcome
        return presenter.sweep_text(outcome)

    def _publish_sensitivity(self, outcome: SensitivityOutcome, *, use_imperial: bool) -> str:
        """在 UI 執行緒畫龍捲風圖、保存結果並回傳文字。

參數：
    outcome: 敏感度結果。
    use_imperial: 是否以英制輸出。

回傳：
    格式化結果文字。"""
        presenter = BatchPresenter(self.unit_converter, use_imperial)
        presenter.plot_tornado(self.chart_panel.figure, outcome)
        self.chart_panel.refresh()
        self.last_outcome = outcome
        return presenter.sensitivity_text(outcome)
