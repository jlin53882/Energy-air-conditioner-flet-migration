"""多元取熱雙效熱泵動態模擬頁（系統示意圖動畫、即時數值、趨勢圖與 P-h 圖）。

計算全部委派給 :class:`application.heat_pump_simulation.HeatPumpSimulationService`
（domain 的 :class:`~domain.heat_pump.HeatPumpSimulation`）；本頁只負責控制項、
動畫節拍與呈現。性質表建立約需數秒，以 ``CalculationRunner`` 在背景執行。

動畫節拍：每 ``TICK_S`` 秒（實際時間）推進 ``speed × TICK_S`` 秒的模擬時間，
以不超過 5 秒的步長分段；流動點與葉片的速度依冷媒流量、頻率與 GPM 在實際時間中前進。
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import replace

import flet as ft
import flet_charts as fch

from application.heat_pump_simulation import HeatPumpSimulationService, SaturationDome
from domain.heat_pump import (
    SCENARIOS,
    CoolingControlMode,
    FrequencyMode,
    HeatPumpSimulation,
    OperationMode,
    PumpMode,
    ReheatMode,
    SimulationEvent,
    StepRecord,
    celsius,
    default_settings,
)

from ..calculation_runner import CalculationOutcome, CalculationRunner
from ..components.engineering_card import EngineeringCard
from ..components.heat_pump_schematic import HeatPumpSchematic
from ..components.kpi_tile import KpiTile
from ..heat_pump_presentation import (
    MODE_LABELS,
    MODE_SHORT_LABELS,
    WARNING_LABELS,
    TEMPERATURE_LEGEND,
    control_band,
    downsample,
    room_series,
    time_axis,
    format_clock,
    format_power,
    format_pressure,
    format_temperature,
    instant_cop,
    ph_cycle,
    ts_cycle,
)
from ..theme import TOKENS, mono_style, primary_button_style, secondary_button_style, style_dropdown

TICK_S = 0.2
MAX_STEP_S = 5.0
SPEEDS = (1, 10, 30, 60, 120, 600, 1200)
DEFAULT_SPEED = 60
HISTORY_LIMIT_S = 3 * 3600.0
ROOM_HISTORY_LIMIT_S = 26 * 3600.0  # 房間模式看一整天
ROOM_COLOR = "#1F7A6D"
RH_COLOR = "#2F6FB5"
BAND_COLOR = "#8A9A95"
# 冷房模式可選的再熱方式（預設關閉）；協調除濕屬於除濕模式，不在此列。
REHEAT_MODE_LABELS = {ReheatMode.OFF: "關閉", ReheatMode.DEMAND: "按需", ReheatMode.FIXED: "固定 20 %"}
MODE_NAMES = {"cooling": "冷房", "heating": "暖房", "dehumidify": "除濕"}
MODE_CAPTIONS = {
    "cooling": "冷房：維持室溫；冰水盤管冷卻，再熱預設關閉（過程中仍會自然除濕）",
    "heating": "暖房：維持室溫；熱水供暖房盤管，再熱支路關閉（目前為固定室溫模型）",
    "dehumidify": "除濕：降低含濕量並避免過冷；又熱又濕先冷卻除濕、溫度合適但太濕時依室溫再熱、"
                  "濕度回到目標帶即退出除濕（房間溫濕度模型＋協調除濕，§8.12.8）",
}
TREND_POINTS = 360
EVENT_ROWS = 30
COLD_COLOR = "#1F4E89"
HOT_COLOR = "#C2410C"
FREQ_COLOR = "#7A5195"
QE_COLOR = "#2F6FB5"
QC_COLOR = "#C2410C"
POWER_COLOR = "#5E6764"
REHEAT_COLOR = "#D08C1F"
COP_COLOR = "#2E7D4F"
PID_REQUEST_COLOR = "#C4A3D6"
THRESHOLD_COLORS = {"target": "#2E7D4F", "stop": "#B42318", "restart": "#D08C1F"}
CONTROL_MODE_LABELS = {
    CoolingControlMode.LEGACY: "舊控制：PID 目標＝停機 7 °C、8 °C 重啟（§4 結果依此）",
    CoolingControlMode.SPLIT: "目標分離：PID 目標 7.5 °C、7 °C 停機、8 °C 重啟（§8.12）",
}

LoopStarter = Callable[[Callable[[], Awaitable[None]]], None]


def _segmented(options: list[tuple[str, str]], selected: str, on_change) -> ft.SegmentedButton:
    """單選分段按鈕。

參數：
    options: (值, 標籤)。
    selected: 預設值。
    on_change: 事件。

回傳：
    SegmentedButton。"""
    return ft.SegmentedButton(
        allow_empty_selection=False,
        segments=[ft.Segment(value=value, label=ft.Text(label)) for value, label in options],
        selected=[selected],
        on_change=on_change,
    )


def _selected(button: ft.SegmentedButton) -> str:
    """分段按鈕目前值。

參數：
    button: 分段按鈕。

回傳：
    值。"""
    return next(iter(button.selected))


class _LabeledSlider(ft.Column):
    """標題、數值與滑桿。"""

    def __init__(self, label: str, unit: str, minimum: float, maximum: float, value: float,
                 divisions: int, digits: int, on_change: Callable[[float], None]) -> None:
        """建立滑桿。

參數：
    label: 標題。
    unit: 單位。
    minimum: 最小值。
    maximum: 最大值。
    value: 預設值。
    divisions: 刻度數。
    digits: 小數位數。
    on_change: 值改變（放開滑桿時）回呼。

回傳：
    無。"""
        self.unit = unit
        self.digits = digits
        self._callback = on_change
        self.value_text = ft.Text("", style=mono_style(size=TOKENS.body, color=TOKENS.text_primary))
        self.slider = ft.Slider(min=minimum, max=maximum, value=value, divisions=divisions,
                                on_change=self._on_drag, on_change_end=self._on_end)
        super().__init__(
            [ft.Row([ft.Text(label, size=TOKENS.caption, color=TOKENS.text_secondary, expand=True), self.value_text]),
             self.slider],
            spacing=0,
        )
        self._show(value)

    @property
    def value(self) -> float:
        """目前值。

回傳：
            float。"""
        return float(self.slider.value)

    def set_value(self, value: float) -> None:
        """以程式設定值（不觸發回呼）。

參數：
            value: 值。

回傳：
            無。"""
        self.slider.value = value
        self._show(value)

    def _show(self, value: float) -> None:
        """更新數值文字。

參數：
            value: 值。

回傳：
            無。"""
        self.value_text.value = f"{value:.{self.digits}f} {self.unit}"

    def _on_drag(self, event: ft.ControlEvent) -> None:
        """拖曳中只更新文字。

參數：
            event: 事件。

回傳：
            無。"""
        self._show(float(event.control.value))
        try:
            self.value_text.update()
        except RuntimeError:
            pass

    def _on_end(self, event: ft.ControlEvent) -> None:
        """放開時套用。

參數：
            event: 事件。

回傳：
            無。"""
        value = round(float(event.control.value), self.digits)
        self._show(value)
        self._callback(value)


class _StepSelector(ft.Column):
    """階梯頻率選擇（30／40／50／60 Hz）與對應的換算說明。"""

    def __init__(self, label: str, steps: tuple[float, ...], value: float, describe: Callable[[float], str],
                 on_change: Callable[[float], None]) -> None:
        """建立選擇器。

參數：
    label: 標題。
    steps: 可選頻率。
    value: 預設頻率。
    describe: 由頻率產生說明文字（例如流量、耗電）。
    on_change: 選擇改變回呼（參數為 Hz）。

回傳：
    無。"""
        self._describe = describe
        self._callback = on_change
        self.dropdown = style_dropdown(ft.Dropdown(
            options=[ft.dropdown.Option(f"{step:g}", f"{step:g} Hz") for step in steps],
            value=f"{value:g}", on_select=self._on_select, expand=True,
        ))
        self.info = ft.Text(describe(value), size=TOKENS.caption, color=TOKENS.text_muted)
        super().__init__(
            [ft.Text(label, size=TOKENS.caption, color=TOKENS.text_secondary), ft.Row([self.dropdown]), self.info],
            spacing=4,
        )

    @property
    def value(self) -> float:
        """目前頻率。

回傳：
            Hz。"""
        return float(self.dropdown.value)

    def set_value(self, value: float) -> None:
        """以程式設定頻率（不觸發回呼）。

參數：
            value: Hz。

回傳：
            無。"""
        self.dropdown.value = f"{value:g}"
        self.info.value = self._describe(value)

    def _on_select(self, _event: ft.ControlEvent) -> None:
        """使用者選擇。

參數：
            _event: 事件。

回傳：
            無。"""
        self.info.value = self._describe(self.value)
        try:
            self.info.update()
        except RuntimeError:
            pass
        self._callback(self.value)


class HeatPumpSimulationView(ft.Column):
    """熱泵動態模擬工作區。"""

    def __init__(
        self,
        service: HeatPumpSimulationService,
        *,
        runner: CalculationRunner | None = None,
        start_loop: LoopStarter | None = None,
    ) -> None:
        """建立畫面。

參數：
    service: 熱泵模擬 application service。
    runner: 背景計算執行器（建性質表）；None 時於呼叫 :meth:`prepare` 時同步建立。
    start_loop: 啟動動畫協程的函式（通常為 ``page.run_task``）；None 時不自動播放，
        可由測試呼叫 :meth:`tick`。

回傳：
    無。"""
        self.service = service
        self.runner = runner
        self.start_loop = start_loop
        self.sim: HeatPumpSimulation | None = None
        self.records: list[StepRecord] = []
        self.latest: StepRecord | None = None
        self.running = False
        self.speed = DEFAULT_SPEED
        self._loop_active = False
        self._preparing = False
        self._refrigerant_phase = 0.0
        self._water_phase = 0.0
        self._rotor_angle = 0.0
        self._event_count = 0
        # 冷房預設不再熱（§8.12.8；§4 的 20 % 只保留作歷史基準）。
        self._settings = replace(default_settings(OperationMode.COOLING), reheat_fraction=0.0)
        self._mode = "cooling"
        self._control_mode = self.service.params.control.cooling_control_mode
        self._room_mode = False
        self._axis = time_axis(0.0, 600.0)
        self._scenario = "hot"
        self._reheat_mode = ReheatMode.OFF
        self._chw_reset = False

        self.status_text = ft.Text("尚未載入", size=TOKENS.caption, color=TOKENS.text_muted)
        self.clock_text = ft.Text("00:00:00", style=mono_style(size=TOKENS.metric, weight=ft.FontWeight.W_700,
                                                                color=TOKENS.text_primary))
        self.play_button = ft.FilledButton("載入模型", icon=ft.Icons.PLAY_ARROW, on_click=self._on_play,
                                           style=primary_button_style())
        self.reset_button = ft.OutlinedButton("重設", icon=ft.Icons.RESTART_ALT, on_click=self._on_reset,
                                              style=secondary_button_style(), disabled=True)
        self.trip_button = ft.OutlinedButton("復歸安全停機", icon=ft.Icons.REPORT_PROBLEM_OUTLINED,
                                             on_click=self._on_reset_trip, visible=False,
                                             style=secondary_button_style())
        self.speed_dropdown = style_dropdown(ft.Dropdown(
            options=[ft.dropdown.Option(str(s), f"{s}× （1 秒 = {s} 秒模擬）") for s in SPEEDS],
            value=str(DEFAULT_SPEED), on_select=self._on_speed, expand=True,
        ))
        self.operation_button = _segmented([("cooling", "冷房"), ("heating", "暖房"), ("dehumidify", "除濕")],
                                           "cooling", self._on_operation)
        self.operation_label = ft.Text("運轉模式", size=TOKENS.caption, color=TOKENS.text_secondary)
        self.mode_caption = ft.Text(MODE_CAPTIONS["cooling"], size=TOKENS.caption, color=TOKENS.text_muted)
        self.fan_a = ft.Checkbox(label="送風機 A（3.5 kW）", value=True, on_change=self._on_fans)
        self.fan_b = ft.Checkbox(label="送風機 B（5.3 kW）", value=True, on_change=self._on_fans)
        params = self.service.params
        self.freq_mode_button = _segmented([("auto", "自動 PID"), ("manual", "手動")], "auto", self._on_freq_mode)
        self.freq_step = _StepSelector(
            "手動頻率（階梯）", params.compressor.frequency_steps_hz, 60.0,
            lambda hz: f"{hz:g} Hz" + ("（低於原廠 50–60 Hz 工作範圍）" if hz < params.compressor.manufacturer_min_frequency_hz else ""),
            self._on_manual_freq)
        self.freq_step.disabled = True
        self.control_mode_button = _segmented(
            [(CoolingControlMode.LEGACY.value, "舊控制"), (CoolingControlMode.SPLIT.value, "目標分離")],
            self._control_mode.value, self._on_control_mode)
        self.control_mode_text = ft.Text(self._control_mode_caption(), size=TOKENS.caption,
                                         color=TOKENS.text_muted)
        self.pump_mode_button = _segmented([("manual", "手動"), ("auto", "自動（水側溫差）")], "manual",
                                           self._on_pump_mode)
        self.cold_pump = _StepSelector(
            "冰水泵頻率", params.cold_pump.frequency_steps_hz, 60.0,
            lambda hz: f"{params.cold_pump.flow_gpm(hz):.2f} GPM · {params.cold_pump.power_w(hz):.0f} W", self._on_pumps)
        self.hot_pump = _StepSelector(
            "熱水泵頻率", params.hot_pump.frequency_steps_hz, 60.0,
            lambda hz: f"{params.hot_pump.flow_gpm(hz):.2f} GPM · {params.hot_pump.power_w(hz):.0f} W", self._on_pumps)
        self.room_mode_button = _segmented([("fixed", "固定室溫"), ("room", "房間溫濕度（§8）")], "fixed",
                                           self._on_room_mode)
        self.scenario_dropdown = style_dropdown(ft.Dropdown(
            options=[ft.dropdown.Option(key, f"{sc.name}（外氣 {sc.outdoor_mean_c - sc.outdoor_amplitude_k:g}–"
                                             f"{sc.outdoor_mean_c + sc.outdoor_amplitude_k:g} °C）")
                     for key, sc in SCENARIOS.items()],
            value=self._scenario, on_select=self._on_room_option, expand=True,
        ))
        self.reheat_mode_button = _segmented([(m.value, label) for m, label in REHEAT_MODE_LABELS.items()],
                                             self._reheat_mode.value, self._on_room_option)
        self.reheat_mode_label = ft.Text("除濕後再熱方式（冷房）", size=TOKENS.caption, color=TOKENS.text_secondary)
        self.chw_reset_box = ft.Checkbox(label="冰水溫度重設 7–10 °C（快降慢升）", value=False,
                                         on_change=self._on_room_option)
        self.room_controls = ft.Column([
            ft.Text("日負載情境", size=TOKENS.caption, color=TOKENS.text_secondary),
            ft.Row([self.scenario_dropdown]),
            self.reheat_mode_label,
            self.reheat_mode_button,
            self.chw_reset_box,
            ft.Text("在室 08–18 時、07:00 起預冷，其餘時段系統停機；室溫、外氣、送風機台數與再熱由情境和室內控制器決定。"
                    "起始 06:00、室內 28.5 °C／65 %、冰水 12 °C，不是週期穩態，第一天數字只供觀察（比較結果見 §8.7）。"
                    "改這些選項會重設模擬。", size=TOKENS.caption, color=TOKENS.text_muted),
        ], spacing=TOKENS.spacing_sm, visible=False)
        self.reheat_slider = _LabeledSlider("除濕後再熱（占盤管負荷）", "%", 0, params.reheat.max_fraction * 100,
                                            self._settings.reheat_fraction * 100, 12, 0, self._on_reheat)
        self.room_slider = _LabeledSlider("室溫", "°C", 10, 35, 27, 50, 1, self._on_environment)
        self.outdoor_slider = _LabeledSlider("外氣", "°C", -10, 45, 30, 110, 1, self._on_environment)
        self.error_text = ft.Text("", size=TOKENS.caption, color=TOKENS.error, visible=False)

        self.schematic = HeatPumpSchematic()
        self.kpis: dict[str, KpiTile] = {
            key: KpiTile(label, col={"xs": 6, "sm": 4, "md": 3, "xl": 2})
            for key, label in (
                ("cold", "冰水溫度"), ("hot", "熱水溫度"), ("freq", "壓縮機頻率"), ("mode", "冷媒模式"),
                ("te", "蒸發溫度"), ("tc", "冷凝溫度"), ("pe", "低壓（絕對）"), ("pc", "高壓（絕對）"),
                ("cooling", "冷量"), ("heating", "熱量"), ("power", "壓縮機耗電"), ("fan_load", "送風機負荷"),
                ("total_power", "總耗電（含水泵）"), ("cop", "累計系統 COP"), ("discharge", "排氣溫度"),
                ("flow", "冷媒流量"), ("pr", "壓縮比"), ("aux", "送風機＋水泵"),
                ("reheat", "再熱熱量"), ("net_cooling", "淨冷卻量（扣再熱）"),
                ("room_t", "室溫"), ("room_rh", "室內 RH"), ("room_w", "室內含濕量"),
                ("coil_split", "盤管顯冷／潛冷"), ("outdoor", "外氣"), ("chw_set", "冰水設定（停機）"),
                ("supply", "送風溫度"), ("condensate", "凝結水量"), ("dehum_state", "除濕狀態"),
            )
        }
        self._room_tiles = ("room_t", "room_rh", "room_w", "coil_split", "outdoor", "chw_set", "supply", "condensate",
                            "dehum_state")
        for key in self._room_tiles:
            self.kpis[key].visible = False
        self.warning_row = ft.Row(wrap=True, spacing=TOKENS.spacing_xs)
        self.event_list = ft.ListView(height=160, spacing=2)
        self.trend_chart = self._make_trend_chart()
        # 0–65：標籤每 10 一格，不顯示 65（否則「60、65」擠在一起）。
        self.trend_chart.left_axis.label_spacing = 10
        self.trend_chart.left_axis.show_max = False
        self.ph_chart = self._make_ph_chart()
        self.ts_chart = self._make_ts_chart()
        self.response_chart = self._make_trend_chart(max_y=20, title="kW／COP")
        self.control_chart = self._make_trend_chart(max_y=12, title="°C")
        self.control_chart.height = 220
        self.control_legend = ft.Row(spacing=TOKENS.spacing_md, wrap=True)
        self.control_note = ft.Text("", size=TOKENS.caption, color=TOKENS.text_muted)
        self.pid_legend = self._legend_item(PID_REQUEST_COLOR, "PID 要求頻率 Hz（量化前）")
        self.room_temp_chart = self._make_trend_chart(max_y=30, title="°C")
        self.room_temp_chart.min_y = 22
        self.room_temp_chart.height = 220
        self.room_rh_chart = self._make_trend_chart(max_y=90, title="%RH")
        self.room_rh_chart.min_y = 30
        self.room_rh_chart.height = 220
        self.room_note = ft.Text("", size=TOKENS.caption, color=TOKENS.text_muted)
        self._dome: SaturationDome | None = None

        legend = ft.Row([
            ft.Text("冷媒溫度", size=TOKENS.caption, color=TOKENS.text_secondary),
            ft.Column([
                ft.Container(width=220, height=8, border_radius=4, gradient=ft.LinearGradient(
                    begin=ft.Alignment(-1, 0), end=ft.Alignment(1, 0), colors=[c for _t, c in TEMPERATURE_LEGEND])),
                ft.Row([ft.Text(f"{t:g}", size=TOKENS.overline, color=TOKENS.text_muted) for t, _c in TEMPERATURE_LEGEND],
                       width=220, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ], spacing=2, tight=True),
            ft.Text("°C", size=TOKENS.caption, color=TOKENS.text_muted),
            self._legend_item("#CDCDC4", "虛線：未使用"),
            self._legend_item(TOKENS.success, "綠色閥：開啟"),
        ], wrap=True, spacing=TOKENS.spacing_md, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        controls_card = EngineeringCard(
            "模擬控制",
            ft.Column([
                ft.Row([self.play_button, self.reset_button, self.trip_button], wrap=True, spacing=TOKENS.spacing_sm),
                ft.Row([ft.Text("模擬時間", size=TOKENS.caption, color=TOKENS.text_muted), self.clock_text,
                        self.status_text], spacing=TOKENS.spacing_sm, wrap=True,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Text("播放速度", size=TOKENS.caption, color=TOKENS.text_secondary),
                ft.Row([self.speed_dropdown]),
                ft.Divider(height=8, color=TOKENS.border),
                self.operation_label,
                self.operation_button,
                self.mode_caption,
                ft.Text("室溫模型（暖房固定室溫；除濕必須用房間模型）", size=TOKENS.caption,
                        color=TOKENS.text_secondary),
                self.room_mode_button,
                self.room_controls,
                ft.Divider(height=8, color=TOKENS.border),
                ft.Row([self.fan_a, self.fan_b], wrap=True),
                ft.Text("壓縮機頻率（日立 E505DH-49A2W，變頻器階梯）", size=TOKENS.caption,
                        color=TOKENS.text_secondary),
                self.freq_mode_button,
                self.freq_step,
                ft.Text("冷房控制架構（切換會重設模擬）", size=TOKENS.caption, color=TOKENS.text_secondary),
                self.control_mode_button,
                self.control_mode_text,
                ft.Divider(height=8, color=TOKENS.border),
                ft.Text("水泵頻率（變頻器階梯）", size=TOKENS.caption, color=TOKENS.text_secondary),
                self.pump_mode_button,
                self.cold_pump,
                self.hot_pump,
                self.reheat_slider,
                self.room_slider,
                self.outdoor_slider,
                self.error_text,
                ft.Text("初始水溫 30 °C；兩桶各 160 L。規格見 docs/simulation-model.md。",
                        size=TOKENS.caption, color=TOKENS.text_muted),
            ], spacing=TOKENS.spacing_sm),
            icon=ft.Icons.TUNE,
        )
        controls_card.col = {"xs": 12, "lg": 4, "xl": 3}
        schematic_card = EngineeringCard(
            "系統示意圖",
            ft.Column([self.schematic, legend, self.warning_row], spacing=TOKENS.spacing_sm),
            subtitle="簡化邏輯流路；電磁閥綠色為開啟",
            icon=ft.Icons.ACCOUNT_TREE_OUTLINED,
        )
        schematic_card.col = {"xs": 12, "lg": 8, "xl": 9}
        room_temp_box = ft.Column([
            self.room_temp_chart,
            ft.Row([self._legend_item(ROOM_COLOR, "室溫 °C"), self._legend_item(BAND_COLOR, "舒適帶 25.5–26.5 °C")],
                   spacing=TOKENS.spacing_md, wrap=True),
        ], col={"xs": 12, "md": 6})
        room_rh_box = ft.Column([
            self.room_rh_chart,
            ft.Row([self._legend_item(RH_COLOR, "室內 RH %"), self._legend_item(BAND_COLOR, "50–60 %RH")],
                   spacing=TOKENS.spacing_md, wrap=True),
        ], col={"xs": 12, "md": 6})
        self.room_card = EngineeringCard("室內溫濕度（§8 房間模型）", ft.Column([
            ft.ResponsiveRow([room_temp_box, room_rh_box], spacing=TOKENS.spacing_md),
            self.room_note,
        ]), subtitle="50 m² 假設房間；在室時段才計入舒適度", icon=ft.Icons.WATER_DROP_OUTLINED)
        self.room_card.visible = False
        self.control_card = EngineeringCard("受控水桶與啟停門檻", ft.Column([
            self.control_chart, self.control_legend, self.control_note,
        ]), subtitle="縱軸放大到門檻附近；趨勢圖的 0–65 刻度看不出 0.5 K 的差異", icon=ft.Icons.THERMOSTAT)
        trend_card = EngineeringCard("水溫與頻率趨勢", ft.Column([
            self.trend_chart,
            ft.Row([self._legend_item(COLD_COLOR, "冰水 °C"), self._legend_item(HOT_COLOR, "熱水 °C"),
                    self._legend_item(FREQ_COLOR, "壓縮機頻率 Hz（實際階梯）"), self.pid_legend],
                   spacing=TOKENS.spacing_md, wrap=True),
        ]), icon=ft.Icons.SHOW_CHART)
        trend_card.col = {"xs": 12, "lg": 6}
        response_card = EngineeringCard("時間響應", ft.Column([
            self.response_chart,
            ft.Row([self._legend_item(QE_COLOR, "冷量 kW"), self._legend_item(QC_COLOR, "熱量 kW"),
                    self._legend_item(POWER_COLOR, "總耗電 kW"), self._legend_item(COP_COLOR, "瞬時系統 COP"),
                    self._legend_item(REHEAT_COLOR, "再熱 kW")],
                   spacing=TOKENS.spacing_md, wrap=True),
        ]), icon=ft.Icons.TIMELINE)
        response_card.col = {"xs": 12, "lg": 6}
        ts_card = EngineeringCard("T-s 圖（R410A）", self.ts_chart, subtitle="目前運轉點的循環；熵基準 ASHRAE",
                                  icon=ft.Icons.STACKED_LINE_CHART)
        ts_card.col = {"xs": 12, "lg": 6}
        ph_card = EngineeringCard("P-h 圖（R410A）", self.ph_chart, subtitle="目前運轉點的循環；焓基準 ASHRAE",
                                  icon=ft.Icons.STACKED_LINE_CHART)
        ph_card.col = {"xs": 12, "lg": 6}
        events_card = EngineeringCard("事件記錄", self.event_list, icon=ft.Icons.LIST_ALT)

        super().__init__(
            [
                ft.ResponsiveRow([controls_card, schematic_card], spacing=TOKENS.spacing_md,
                                 run_spacing=TOKENS.spacing_md),
                ft.ResponsiveRow(list(self.kpis.values()), spacing=TOKENS.spacing_sm, run_spacing=TOKENS.spacing_sm),
                self.room_card,
                self.control_card,
                ft.ResponsiveRow([trend_card, response_card], spacing=TOKENS.spacing_md,
                                 run_spacing=TOKENS.spacing_md),
                ft.ResponsiveRow([ph_card, ts_card], spacing=TOKENS.spacing_md, run_spacing=TOKENS.spacing_md),
                events_card,
            ],
            spacing=TOKENS.spacing_md,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self._show_record(None)

    # ---- 建構 ----

    @staticmethod
    def _legend_item(color: str, label: str) -> ft.Row:
        """圖例項目。

參數：
            color: 顏色。
            label: 文字。

回傳：
            Row。"""
        return ft.Row([ft.Container(width=18, height=4, bgcolor=color, border_radius=2),
                       ft.Text(label, size=TOKENS.caption, color=TOKENS.text_secondary)], spacing=6, tight=True)

    @staticmethod
    def _make_trend_chart(max_y: float = 65, title: str = "°C／Hz") -> fch.LineChart:
        """時間軸折線圖。

參數：
            max_y: 縱軸上限。
            title: 縱軸標題。

回傳：
            LineChart。"""
        return fch.LineChart(
            data_series=[], height=260, min_y=0, max_y=max_y, min_x=0, max_x=60,
            interactive=False,
            horizontal_grid_lines=fch.ChartGridLines(interval=10 if max_y > 30 else 4, color=TOKENS.border, width=0.6),
            left_axis=fch.ChartAxis(label_size=36, title=ft.Text(title, size=TOKENS.caption)),
            bottom_axis=fch.ChartAxis(label_size=24, title=ft.Text("模擬時間 (min)", size=TOKENS.caption)),
            top_axis=fch.ChartAxis(show_labels=False, label_size=0),
            right_axis=fch.ChartAxis(show_labels=False, label_size=0),
        )

    @staticmethod
    def _make_ph_chart() -> fch.LineChart:
        """P-h 圖（線性壓力軸，bar）。

回傳：
            LineChart。"""
        return fch.LineChart(
            data_series=[], height=300, min_x=100, max_x=480, min_y=0, max_y=45, interactive=False,
            vertical_grid_lines=fch.ChartGridLines(interval=50, color=TOKENS.border, width=0.6),
            horizontal_grid_lines=fch.ChartGridLines(interval=5, color=TOKENS.border, width=0.6),
            left_axis=fch.ChartAxis(label_size=36, title=ft.Text("P (bar，絕對)", size=TOKENS.caption)),
            bottom_axis=fch.ChartAxis(label_size=24, title=ft.Text("h (kJ/kg)", size=TOKENS.caption)),
            top_axis=fch.ChartAxis(show_labels=False, label_size=0),
            right_axis=fch.ChartAxis(show_labels=False, label_size=0),
        )

    @staticmethod
    def _make_ts_chart() -> fch.LineChart:
        """T-s 圖。

回傳：
            LineChart。"""
        return fch.LineChart(
            data_series=[], height=300, min_x=0.8, max_x=2.0, min_y=-20, max_y=100, interactive=False,
            vertical_grid_lines=fch.ChartGridLines(interval=0.2, color=TOKENS.border, width=0.6),
            horizontal_grid_lines=fch.ChartGridLines(interval=20, color=TOKENS.border, width=0.6),
            left_axis=fch.ChartAxis(label_size=36, title=ft.Text("T (°C)", size=TOKENS.caption)),
            bottom_axis=fch.ChartAxis(label_size=24, title=ft.Text("s (kJ/kg·K)", size=TOKENS.caption)),
            top_axis=fch.ChartAxis(show_labels=False, label_size=0),
            right_axis=fch.ChartAxis(show_labels=False, label_size=0),
        )

    # ---- 載入與播放 ----

    def prepare(self) -> None:
        """載入性質表並建立 session（背景執行器存在時非同步）。

回傳：
    無。"""
        if self._preparing or self.sim is not None:
            return
        self._preparing = True
        self.status_text.value = "建立冷媒性質表中（約數秒）…"
        self.play_button.disabled = True
        self._safe_update()
        if self.runner is None:
            try:
                self.service.prepare()
                outcome = CalculationOutcome(value=None)
            except Exception as error:  # noqa: BLE001 — 以錯誤訊息呈現。
                outcome = CalculationOutcome(error=error)
            self._on_prepared(outcome)
        else:
            self.runner.submit(self.service.prepare, self._on_prepared)

    def _on_prepared(self, outcome: CalculationOutcome) -> None:
        """性質表完成。

參數：
    outcome: 結果。

回傳：
    無。"""
        self._preparing = False
        self.play_button.disabled = False
        if outcome.error is not None:
            self.status_text.value = f"載入失敗：{outcome.error}"
            self._safe_update()
            return
        self._dome = self.service.saturation_dome()
        self._new_session()
        self.status_text.value = "已就緒，按「播放」開始"
        self.play_button.content = "播放"
        self.reset_button.disabled = False
        self._safe_update()

    def _new_session(self) -> None:
        """依目前設定建立新的模擬。

回傳：
    無。"""
        if self._room_mode:
            self.sim = self.service.new_room_session(
                self._settings, self._scenario, reheat_mode=self._room_reheat_mode(), chw_reset=self._chw_reset,
                cooling_control_mode=self._control_mode)
        else:
            self.sim = self.service.new_session(self._settings, cooling_control_mode=self._control_mode)
        self.records = []
        self._event_count = 0
        self.event_list.controls = []
        self.latest = None
        self._show_record(None)

    def _on_play(self, _event: ft.ControlEvent | None) -> None:
        """播放／暫停。

參數：
    _event: 事件。

回傳：
    無。"""
        if self.sim is None:
            self.prepare()
            return
        self.running = not self.running
        self.play_button.content = "暫停" if self.running else "播放"
        self.play_button.icon = ft.Icons.PAUSE if self.running else ft.Icons.PLAY_ARROW
        self.status_text.value = "播放中" if self.running else "已暫停"
        if self.running and not self._loop_active and self.start_loop is not None:
            self._loop_active = True
            self.start_loop(self._loop)
        self._safe_update()

    async def _loop(self) -> None:
        """動畫迴圈（在 page 事件迴圈中執行）。

回傳：
    無。"""
        try:
            while self.running:
                await asyncio.sleep(TICK_S)
                if self.running:
                    self.tick()
        finally:
            self._loop_active = False

    def tick(self, real_dt_s: float = TICK_S) -> None:
        """推進一個動畫節拍：模擬 speed × real_dt 秒並更新畫面。

參數：
    real_dt_s: 實際經過時間。

回傳：
    無。"""
        if self.sim is None:
            return
        try:
            sim_seconds = self.speed * real_dt_s
            steps = max(1, math.ceil(sim_seconds / MAX_STEP_S - 1e-9))
            for _ in range(steps):
                record = self.sim.step(sim_seconds / steps)
                self.records.append(record)
        except ValueError as error:
            self.running = False
            self.status_text.value = f"模擬停止：{error}"
            self._safe_update()
            return
        cutoff = self.records[-1].time_s - (ROOM_HISTORY_LIMIT_S if self._room_mode else HISTORY_LIMIT_S)
        if self.records[0].time_s < cutoff:
            self.records = [r for r in self.records if r.time_s >= cutoff]
        self.latest = self.records[-1]
        if self._settings.pump_mode is PumpMode.AUTO:  # 自動時顯示控制器目前選的階梯
            self.cold_pump.set_value(self.latest.cold_pump_hz)
            self.hot_pump.set_value(self.latest.hot_pump_hz)
        self._advance_animation(self.latest, real_dt_s)
        self._show_record(self.latest)
        self._safe_update()

    def _advance_animation(self, record: StepRecord, real_dt_s: float) -> None:
        """依流量推進流動點與葉片（實際時間）。

參數：
    record: 最新記錄。
    real_dt_s: 實際經過時間。

回傳：
    無。"""
        frequency_ratio = record.frequency_hz / 60.0 if record.compressor_on else 0.0
        self._refrigerant_phase += 90.0 * frequency_ratio * real_dt_s
        gpm = (record.cold_pump_gpm + record.hot_pump_gpm) / 2
        self._water_phase += 60.0 * gpm / 12.06 * real_dt_s
        self._rotor_angle = (self._rotor_angle + 2 * math.pi * 1.2 * frequency_ratio * real_dt_s) % (2 * math.pi)

    # ---- 設定變更 ----

    def _apply_settings(self, settings) -> None:
        """套用設定到模擬（錯誤以訊息呈現）。

參數：
    settings: SimulationSettings。

回傳：
    無。"""
        try:
            if self.sim is not None:
                self.sim.update_settings(settings)
            self._settings = settings
            self.error_text.visible = False
        except ValueError as error:
            self.error_text.value = str(error)
            self.error_text.visible = True
        self._show_record(self.latest)
        self._safe_update()

    def _on_speed(self, _event: ft.ControlEvent) -> None:
        """播放速度。

參數：
    _event: 事件。

回傳：
    無。"""
        self.speed = int(self.speed_dropdown.value)

    def _on_operation(self, _event: ft.ControlEvent) -> None:
        """冷房／暖房／除濕。

        - 冷房：冰水水路；固定室溫或房間模型皆可；再熱預設關閉。
        - 暖房：熱水水路；固定室溫（房間模型目前只支援冷房）。
        - 除濕：冰水水路＋房間模型＋協調除濕（再熱只服務除濕、避免過冷）。

        只在固定室溫的冷房／暖房之間切換時沿用目前模擬（即時套用）；牽涉房間模型時重設模擬。

參數：
    _event: 事件。

回傳：
    無。"""
        mode = _selected(self.operation_button)
        if mode == self._mode:
            return
        previous_room = self._room_mode
        previous_mode = self._mode
        self._mode = mode
        if mode == "dehumidify":
            self._room_mode = True
        elif mode == "heating":
            self._room_mode = False
        operation = OperationMode.HEATING if mode == "heating" else OperationMode.COOLING
        defaults = default_settings(operation)
        self.room_slider.set_value(defaults.room_k - 273.15)
        self.outdoor_slider.set_value(defaults.outdoor_k - 273.15)
        settings = replace(self._settings, operation=operation, room_k=defaults.room_k, outdoor_k=defaults.outdoor_k,
                           reheat_fraction=self.reheat_slider.value / 100.0 if mode == "cooling" else 0.0)
        self._sync_room_controls()
        self.control_mode_text.value = ""
        if previous_room or self._room_mode or previous_mode == "dehumidify":
            self._settings = settings
            self.control_mode_text.value = self._control_mode_caption()
            self._restart_paused(f"已切換為{MODE_NAMES[mode]}模式，模擬已重設")
            return
        self._apply_settings(settings)
        self.control_mode_text.value = self._control_mode_caption()
        self._safe_update()

    def _on_fans(self, _event: ft.ControlEvent) -> None:
        """送風機台數。

參數：
    _event: 事件。

回傳：
    無。"""
        fans = frozenset(name for name, box in (("A", self.fan_a), ("B", self.fan_b)) if box.value)
        self._apply_settings(replace(self._settings, fans=fans))

    def _on_freq_mode(self, _event: ft.ControlEvent) -> None:
        """自動／手動頻率。

參數：
    _event: 事件。

回傳：
    無。"""
        mode = FrequencyMode(_selected(self.freq_mode_button))
        self.freq_step.disabled = mode is FrequencyMode.AUTO
        self._apply_settings(replace(self._settings, frequency_mode=mode,
                                     manual_frequency_hz=self.freq_step.value))

    def _restart_paused(self, message: str) -> None:
        """以目前選項重建模擬並暫停（房間模式選項、控制架構切換共用）。

參數：
    message: 狀態列訊息。

回傳：
    無。"""
        if self.sim is not None:
            self.running = False
            self.play_button.content = "播放"
            self.play_button.icon = ft.Icons.PLAY_ARROW
            self.status_text.value = message
            self._new_session()
        self._safe_update()

    def _sync_room_controls(self) -> None:
        """依運轉模式與室溫模型啟用／停用相關控制項。

回傳：
    無。"""
        room = self._room_mode
        mode = self._mode
        self.mode_caption.value = MODE_CAPTIONS[mode]
        self.room_mode_button.selected = ["room" if room else "fixed"]
        # 暖房只有固定室溫、除濕只有房間模型，只有冷房可切換。
        self.room_mode_button.disabled = mode != "cooling"
        self.room_controls.visible = room
        self.room_card.visible = room
        for key in self._room_tiles:
            self.kpis[key].visible = room
        self.kpis["dehum_state"].visible = room and mode == "dehumidify"
        # 再熱方式只在冷房＋房間模型可選；除濕固定為協調除濕。
        self.reheat_mode_label.visible = self.reheat_mode_button.visible = mode == "cooling"
        # 室溫、外氣由情境決定；固定比例再熱只在固定室溫的冷房有意義；送風機勾選改為「可用」。
        self.room_slider.disabled = room
        self.outdoor_slider.disabled = room
        self.reheat_slider.disabled = room or mode != "cooling"
        self.fan_a.label = "可用：送風機 A（3.5 kW）" if room else "送風機 A（3.5 kW）"
        self.fan_b.label = "可用：送風機 B（5.3 kW）" if room else "送風機 B（5.3 kW）"

    def _room_reheat_mode(self) -> ReheatMode:
        """房間模型使用的再熱方式：除濕模式為協調除濕，冷房為使用者選擇（預設關閉）。

回傳：
    ReheatMode。"""
        return ReheatMode.COORDINATED if self._mode == "dehumidify" else self._reheat_mode

    def _on_room_mode(self, _event: ft.ControlEvent) -> None:
        """固定室溫／房間溫濕度模型（§8；只有冷房可切換）。變更會重設模擬。

參數：
    _event: 事件。

回傳：
    無。"""
        room = _selected(self.room_mode_button) == "room"
        if room == self._room_mode or self._mode != "cooling":
            return
        self._room_mode = room
        self._sync_room_controls()
        self._restart_paused("已切換為房間溫濕度模型，模擬已重設" if room else "已切換為固定室溫，模擬已重設")

    def _on_room_option(self, _event: ft.ControlEvent) -> None:
        """情境、再熱方式、冰水重設：房間模型建立時決定，所以變更會重設模擬。

參數：
    _event: 事件。

回傳：
    無。"""
        self._scenario = self.scenario_dropdown.value or self._scenario
        self._reheat_mode = ReheatMode(_selected(self.reheat_mode_button))
        self._chw_reset = bool(self.chw_reset_box.value)
        if self._room_mode:
            self._restart_paused("已變更房間情境設定，模擬已重設")

    def _control_mode_caption(self) -> str:
        """控制架構說明（暖房時註明不影響）。

回傳：
    文字。"""
        text = CONTROL_MODE_LABELS[self._control_mode]
        if self._settings.operation is OperationMode.HEATING:
            text += "；暖房不受影響"
        return text

    def _on_control_mode(self, _event: ft.ControlEvent) -> None:
        """冷房控制架構：PID 參數依架構不同，只能在建立 session 時決定，所以切換會重設模擬並暫停。

參數：
    _event: 事件。

回傳：
    無。"""
        mode = CoolingControlMode(_selected(self.control_mode_button))
        if mode is self._control_mode:
            return
        self._control_mode = mode
        self.control_mode_text.value = self._control_mode_caption()
        self._restart_paused("已切換冷房控制架構，模擬已重設")

    def _on_manual_freq(self, value: float) -> None:
        """手動頻率。

參數：
    value: Hz。

回傳：
    無。"""
        self._apply_settings(replace(self._settings, manual_frequency_hz=value))

    def _on_pump_mode(self, _event: ft.ControlEvent) -> None:
        """水泵手動／自動（自動：依板式換熱器水側溫差逐階調整，§2.4）。

參數：
    _event: 事件。

回傳：
    無。"""
        mode = PumpMode(_selected(self.pump_mode_button))
        self.cold_pump.disabled = self.hot_pump.disabled = mode is PumpMode.AUTO
        self._apply_settings(replace(self._settings, pump_mode=mode, cold_pump_hz=self.cold_pump.value,
                                     hot_pump_hz=self.hot_pump.value))

    def _on_pumps(self, _value: float) -> None:
        """水泵頻率（冰水泵、熱水泵各自選擇階梯）。

參數：
    _value: 新值。

回傳：
    無。"""
        self._apply_settings(replace(self._settings, cold_pump_hz=self.cold_pump.value,
                                     hot_pump_hz=self.hot_pump.value))

    def _on_reheat(self, value: float) -> None:
        """除濕後再熱比例（%）。

參數：
    value: 百分比。

回傳：
    無。"""
        self._apply_settings(replace(self._settings, reheat_fraction=value / 100.0))

    def _on_environment(self, _value: float) -> None:
        """室溫與外氣。

參數：
    _value: 新值。

回傳：
    無。"""
        self._apply_settings(replace(self._settings, room_k=celsius(self.room_slider.value),
                                     outdoor_k=celsius(self.outdoor_slider.value)))

    def _on_reset(self, _event: ft.ControlEvent | None) -> None:
        """以目前設定重新開始（水溫回到 30 °C）。

參數：
    _event: 事件。

回傳：
    無。"""
        if self.sim is None:
            return
        self.running = False
        self.play_button.content = "播放"
        self.play_button.icon = ft.Icons.PLAY_ARROW
        self.status_text.value = "已重設"
        self._new_session()
        self._safe_update()

    def _on_reset_trip(self, _event: ft.ControlEvent | None) -> None:
        """手動復歸安全停機。

參數：
    _event: 事件。

回傳：
    無。"""
        if self.sim is not None:
            self.sim.reset_trip()
            self._sync_events()
            self._safe_update()

    # ---- 呈現 ----

    def _show_record(self, record: StepRecord | None) -> None:
        """更新示意圖、數值卡、警示、圖表與事件。

參數：
    record: 最新記錄。

回傳：
    無。"""
        outdoor_k = record.outdoor_k if record is not None and record.outdoor_k is not None else self._settings.outdoor_k
        self.schematic.render(record, self._refrigerant_phase, self._water_phase, self._rotor_angle, outdoor_k)
        self.clock_text.value = format_clock(self.sim.time_s if self.sim else 0.0)
        k = self.kpis
        if record is None:
            for tile in k.values():
                tile.set_value("—")
            self.warning_row.controls = []
            self.trip_button.visible = False
            self._update_charts()
            return
        on = record.compressor_on
        k["cold"].set_value(format_temperature(record.cold_water_k), "°C")
        k["hot"].set_value(format_temperature(record.hot_water_k), "°C")
        k["freq"].set_value(f"{record.frequency_hz:.1f}" if on else "停機", "Hz" if on else "")
        k["mode"].set_value(MODE_SHORT_LABELS[record.mode])
        k["mode"].tooltip = MODE_LABELS[record.mode]
        k["te"].set_value(format_temperature(record.evaporating_k), "°C" if on else "")
        k["tc"].set_value(format_temperature(record.condensing_k), "°C" if on else "")
        k["pe"].set_value(format_pressure(record.evaporating_pressure_pa), "bar" if on else "")
        k["pc"].set_value(format_pressure(record.condensing_pressure_pa), "bar" if on else "")
        k["discharge"].set_value(format_temperature(record.discharge_k), "°C" if on else "")
        k["pr"].set_value(f"{record.pressure_ratio:.2f}" if on else "—")
        k["aux"].set_value(format_power(record.fan_power_w + record.pump_power_w), "kW")
        k["reheat"].set_value(format_power(record.reheat_w), "kW")
        k["net_cooling"].set_value(format_power(record.net_cooling_w), "kW")
        if record.room_k is not None:
            k["room_t"].set_value(format_temperature(record.room_k), "°C")
            k["room_rh"].set_value(f"{(record.room_rh or 0) * 100:.0f}", "%")
            k["room_w"].set_value(f"{(record.room_humidity_ratio or 0) * 1000:.1f}", "g/kg")
            k["coil_split"].set_value(f"{record.coil_sensible_w / 1000:.2f}／{record.coil_latent_w / 1000:.2f}", "kW")
            k["outdoor"].set_value(format_temperature(record.outdoor_k), "°C")
            k["chw_set"].set_value(format_temperature(record.chw_setpoint_k), "°C")
            k["supply"].set_value(format_temperature(record.supply_k), "°C" if record.supply_k is not None else "")
            k["condensate"].set_value(f"{record.condensate_kg_s * 3600:.2f}", "kg/h")
            room = self.sim.room if self.sim is not None else None
            if self._mode == "dehumidify" and room is not None:
                k["dehum_state"].set_value("除濕＋補熱" if room.dehum_mode else "顯冷／待機",
                                           "再熱中" if record.reheat_w > 0 else "")
            else:
                k["dehum_state"].set_value("—", "")
        k["flow"].set_value(f"{record.mass_flow_kg_s * 1000:.1f}" if on else "—", "g/s" if on else "")
        k["cooling"].set_value(format_power(record.cooling_w), "kW")
        k["heating"].set_value(format_power(record.heating_w), "kW")
        k["power"].set_value(format_power(record.compressor_power_w), "kW")
        k["fan_load"].set_value(format_power(record.fan_coil_load_w), "kW")
        k["total_power"].set_value(format_power(record.total_power_w), "kW")
        cop = record.system_cop
        current = instant_cop(record)
        k["cop"].set_value("—" if cop is None else f"{cop:.2f}",
                           "" if current is None else f"瞬時 {current:.2f}")
        self.warning_row.controls = [
            ft.Container(
                ft.Text(WARNING_LABELS.get(code, code), size=TOKENS.caption, color=TOKENS.warning),
                bgcolor=TOKENS.warning_soft, border_radius=TOKENS.radius_pill,
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            )
            for code in sorted(record.warnings)
        ]
        if on and record.frequency_hz < self.service.params.compressor.manufacturer_min_frequency_hz:
            self.warning_row.controls.append(ft.Container(
                ft.Text(f"壓縮機低於原廠 {self.service.params.compressor.manufacturer_min_frequency_hz:g}–"
                        f"{self.service.params.compressor.max_frequency_hz:g} Hz 工作範圍",
                        size=TOKENS.caption, color=TOKENS.text_secondary),
                bgcolor=TOKENS.surface_variant, border_radius=TOKENS.radius_pill,
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            ))
        self.trip_button.visible = "tripped" in record.warnings
        self._update_charts()
        self._sync_events()

    def _sync_events(self) -> None:
        """把新事件加到事件列表（最新在上）。

回傳：
    無。"""
        if self.sim is None:
            return
        events: list[SimulationEvent] = self.sim.events
        for event in events[self._event_count:]:
            self.event_list.controls.insert(0, ft.Text(
                f"{format_clock(event.time_s)}  {event.message}",
                style=mono_style(size=TOKENS.caption, color=TOKENS.text_secondary),
            ))
        self._event_count = len(events)
        del self.event_list.controls[EVENT_ROWS:]

    def _update_charts(self) -> None:
        """更新趨勢圖與 P-h 圖。

回傳：
    無。"""
        samples = downsample(self.records, TREND_POINTS)
        if samples:
            # 跨度超過 4 h（房間模式看一整天）改用小時，避免分鐘刻度過密。
            axis = time_axis(samples[0].time_s, samples[-1].time_s)
            self._axis = axis
            interval = axis.interval
            self.trend_chart.min_x = axis.min_x
            self.trend_chart.max_x = axis.max_x
            self.trend_chart.vertical_grid_lines = fch.ChartGridLines(interval=interval, color=TOKENS.border, width=0.6)
            title = "時刻 (h)" if self._room_mode and axis.unit == "h" else f"模擬時間 ({axis.unit})"

            def series(values, color):
                return fch.LineChartData(
                    points=[fch.LineChartDataPoint(r.time_s / axis.divisor, v) for r, v in zip(samples, values)],
                    color=color, stroke_width=2, curved=False,
                )

            # PID 要求頻率只在自動模式有意義（手動時不畫）；先畫，讓實際階梯線疊在上面。
            show_pid = self._settings.frequency_mode is FrequencyMode.AUTO
            self.pid_legend.visible = show_pid
            self.trend_chart.data_series = (
                [fch.LineChartData(
                    points=[fch.LineChartDataPoint(r.time_s / axis.divisor, r.pid_request_hz) for r in samples],
                    color=PID_REQUEST_COLOR, stroke_width=1.5, curved=False)] if show_pid else []
            ) + [
                series([r.cold_water_k - 273.15 for r in samples], COLD_COLOR),
                series([r.hot_water_k - 273.15 for r in samples], HOT_COLOR),
                series([r.frequency_hz for r in samples], FREQ_COLOR),
            ]
            charts = (self.trend_chart, self.response_chart, self.control_chart, self.room_temp_chart, self.room_rh_chart)
            for chart in charts:
                # 橫軸標籤與格線同間距（否則全寬的門檻圖會每 0.5 min 一個標籤）。
                chart.bottom_axis.label_spacing = interval
                chart.bottom_axis.title = ft.Text(title, size=TOKENS.caption)
                for attr in ("min_x", "max_x", "vertical_grid_lines"):
                    setattr(chart, attr, getattr(self.trend_chart, attr))
            self._update_control_chart(samples)
            self._update_room_charts(samples)
            cops = [instant_cop(r) or 0.0 for r in samples]
            # 縱軸隨資料放大：Flet 圖表不裁切超出 max_y 的線，起始降溫時熱量可超過 20 kW，會畫到卡片標題上。
            peak = max(max(r.cooling_w, r.heating_w, r.total_power_w, r.reheat_w) for r in samples) / 1000
            peak = max(peak, max(cops))
            self.response_chart.max_y = max(20, 4 * math.ceil(peak / 4))
            self.response_chart.left_axis.label_spacing = 4
            self.response_chart.data_series = [
                series([r.cooling_w / 1000 for r in samples], QE_COLOR),
                series([r.heating_w / 1000 for r in samples], QC_COLOR),
                series([r.total_power_w / 1000 for r in samples], POWER_COLOR),
                series(cops, COP_COLOR),
                series([r.reheat_w / 1000 for r in samples], REHEAT_COLOR),
            ]
        else:
            self.trend_chart.data_series = []
            self.response_chart.data_series = []
            self._update_control_chart([])

        series = []
        max_bar = self.ph_chart.max_y
        if self._dome is not None:
            # 橫軸只涵蓋運轉範圍（6 bar 以上的飽和線），右側保留排氣過熱區。
            window = [(h, p) for curve in (self._dome.liquid, self._dome.vapor) for h, p in curve
                      if 6e5 <= p <= max_bar * 1e5]
            if window:
                self.ph_chart.min_x = math.floor(min(h for h, _p in window) / 1000 / 50) * 50
                self.ph_chart.max_x = math.ceil((max(h for h, _p in window) / 1000 + 90) / 50) * 50
            for curve in (self._dome.liquid, self._dome.vapor):
                series.append(fch.LineChartData(
                    points=[fch.LineChartDataPoint(h / 1000, p / 1e5) for h, p in curve
                            if 6e5 <= p <= max_bar * 1e5],
                    color=TOKENS.border_strong, stroke_width=1.5, curved=True,
                ))
        cycle = ph_cycle(self.latest) if self.latest is not None else None
        if cycle is not None:
            series.append(fch.LineChartData(
                points=[fch.LineChartDataPoint(h, p / 100) for h, p in cycle.points],
                color=TOKENS.highlight, stroke_width=2.5,
                point=fch.ChartCirclePoint(color=TOKENS.highlight, radius=4, stroke_color=TOKENS.surface,
                                           stroke_width=1.5),
            ))
        self.ph_chart.data_series = series

        ts_series = []
        if self._dome is not None and self._dome.liquid_ts:
            # 橫軸依 −20～70 °C 的飽和線決定，右側保留排氣過熱區。
            window = [s_ / 1000 for curve in (self._dome.liquid_ts, self._dome.vapor_ts)
                      for s_, t in curve if celsius(-20.0) <= t <= celsius(70.0)]
            if window:
                self.ts_chart.min_x = math.floor(min(window) / 0.2) * 0.2
                self.ts_chart.max_x = math.ceil((max(window) + 0.25) / 0.2) * 0.2
            for curve in (self._dome.liquid_ts, self._dome.vapor_ts):
                ts_series.append(fch.LineChartData(
                    points=[fch.LineChartDataPoint(s_ / 1000, t - 273.15) for s_, t in curve],
                    color=TOKENS.border_strong, stroke_width=1.5, curved=True,
                ))
        ts = (ts_cycle(self.latest, self._dome.liquid_ts, self._dome.vapor_ts)
              if self.latest is not None and self._dome is not None else None)
        if ts is not None:
            ts_series.append(fch.LineChartData(
                points=[fch.LineChartDataPoint(s_, t) for s_, t in ts.points],
                color=TOKENS.highlight, stroke_width=2.5,
            ))
            ts_series.append(fch.LineChartData(
                points=[fch.LineChartDataPoint(s_, t) for s_, t in ts.markers],
                color="#00000000", stroke_width=0,
                point=fch.ChartCirclePoint(color=TOKENS.highlight, radius=4, stroke_color=TOKENS.surface,
                                           stroke_width=1.5),
            ))
        self.ts_chart.data_series = ts_series

    def _update_control_chart(self, samples: list[StepRecord]) -> None:
        """受控水桶與門檻線（§2.3、§8.12）。

參數：
    samples: 抽樣後記錄。

回傳：
    無。"""
        band = control_band(samples)
        if band is None:
            self.control_chart.data_series = []
            self.control_legend.controls = []
            self.control_note.value = "播放後顯示受控水桶溫度與 PID 目標、停機、重啟門檻。"
            return
        self.control_card.title_control.value = band.title
        self.control_chart.min_y = band.min_y
        self.control_chart.max_y = band.max_y
        self.control_chart.horizontal_grid_lines = fch.ChartGridLines(interval=1, color=TOKENS.border, width=0.6)
        self.control_chart.left_axis.label_spacing = 2
        scale = 60.0 / self._axis.divisor  # band 以分鐘給時間
        start, end = band.times_min[0] * scale, band.times_min[-1] * scale
        # 門檻線用細實線（不用虛線或漸層：部分桌面客戶端遇到特殊畫筆會中斷繪製）。
        series = [
            fch.LineChartData(points=[fch.LineChartDataPoint(start, line.value_c), fch.LineChartDataPoint(end, line.value_c)],
                              color=THRESHOLD_COLORS[line.key], stroke_width=1.8, curved=False)
            for line in band.lines
        ]
        series.append(fch.LineChartData(
            points=[fch.LineChartDataPoint(t * scale, v) for t, v in zip(band.times_min, band.tank_c)],
            color=COLD_COLOR if band.tank_label.startswith("冰水") else HOT_COLOR, stroke_width=2, curved=False))
        self.control_chart.data_series = series
        self.control_legend.controls = [self._legend_item(COLD_COLOR if band.tank_label.startswith("冰水") else HOT_COLOR,
                                                          band.tank_label)] + [
            self._legend_item(THRESHOLD_COLORS[line.key], line.label) for line in reversed(band.lines)]
        notes = []
        if band.clipped:
            notes.append(f"超出 {band.min_y:g}–{band.max_y:g} °C 的部分貼在圖框邊緣（例如起始降溫）")
        if len(band.lines) < 3:
            notes.append("舊控制的 PID 目標與停機門檻相同，桶溫一到目標就停機，所以只有兩條線")
        self.control_note.value = "；".join(notes)

    def _update_room_charts(self, samples: list[StepRecord]) -> None:
        """房間溫濕度圖（§8）：室溫＋舒適帶、RH＋50–60 % 帶；只在房間模式顯示。

參數：
    samples: 抽樣後記錄。

回傳：
    無。"""
        data = room_series(samples) if self._room_mode else None
        if data is None:
            self.room_temp_chart.data_series = []
            self.room_rh_chart.data_series = []
            self.room_note.value = ""
            return
        d = self._axis.divisor
        xs = [t / d for t in data.times_s]
        x0, x1 = xs[0], xs[-1]

        def flat(value: float) -> fch.LineChartData:
            return fch.LineChartData(points=[fch.LineChartDataPoint(x0, value), fch.LineChartDataPoint(x1, value)],
                                     color=BAND_COLOR, stroke_width=1.5, curved=False)

        self.room_temp_chart.min_y, self.room_temp_chart.max_y = data.min_y, data.max_y
        self.room_temp_chart.left_axis.label_spacing = 1
        self.room_temp_chart.horizontal_grid_lines = fch.ChartGridLines(interval=1, color=TOKENS.border, width=0.6)
        self.room_temp_chart.data_series = [flat(v) for v in data.temperature_band_c] + [
            fch.LineChartData(points=[fch.LineChartDataPoint(x, v) for x, v in zip(xs, data.room_c)],
                              color=ROOM_COLOR, stroke_width=2, curved=False)]
        rh = [min(90.0, max(30.0, v)) for v in data.rh_pct]
        self.room_rh_chart.left_axis.label_spacing = 10
        self.room_rh_chart.horizontal_grid_lines = fch.ChartGridLines(interval=10, color=TOKENS.border, width=0.6)
        self.room_rh_chart.data_series = [flat(v) for v in data.rh_band_pct] + [
            fch.LineChartData(points=[fch.LineChartDataPoint(x, v) for x, v in zip(xs, rh)],
                              color=RH_COLOR, stroke_width=2, curved=False)]
        latest = samples[-1]
        state = ("在室" if latest.occupied else "非在室") + ("、空調啟用" if latest.system_enabled else "、空調停用")
        notes = [f"目前：{state}（在室 08–18 時，07:00 起預冷）"]
        if data.clipped:
            notes.append(f"室溫超出 {data.min_y:g}–{data.max_y:g} °C 的部分貼在圖框邊緣")
        self.room_note.value = "；".join(notes)

    def _safe_update(self) -> None:
        """已掛載時才更新畫面。

回傳：
    無。"""
        try:
            self.update()
        except RuntimeError:
            pass

    def will_unmount(self) -> None:
        """離開頁面時停止動畫。

回傳：
    無。"""
        self.running = False
