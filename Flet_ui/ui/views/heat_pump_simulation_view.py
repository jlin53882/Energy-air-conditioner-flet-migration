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
    FrequencyMode,
    HeatPumpSimulation,
    OperationMode,
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
    LINE_COLORS,
    LINE_LABELS,
    MODE_LABELS,
    MODE_SHORT_LABELS,
    WARNING_LABELS,
    LineState,
    downsample,
    format_clock,
    format_power,
    format_pressure,
    format_temperature,
    instant_cop,
    ph_cycle,
)
from ..theme import TOKENS, mono_style, primary_button_style, secondary_button_style, style_dropdown

TICK_S = 0.2
MAX_STEP_S = 5.0
SPEEDS = (1, 10, 30, 60, 120)
DEFAULT_SPEED = 60
HISTORY_LIMIT_S = 3 * 3600.0
TREND_POINTS = 360
EVENT_ROWS = 30
COLD_COLOR = "#1F4E89"
HOT_COLOR = "#C2410C"
FREQ_COLOR = "#7A5195"

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
        self._settings = default_settings(OperationMode.COOLING)

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
        self.operation_button = _segmented([("cooling", "冷房"), ("heating", "暖房")], "cooling", self._on_operation)
        self.fan_a = ft.Checkbox(label="送風機 A（3.5 kW）", value=True, on_change=self._on_fans)
        self.fan_b = ft.Checkbox(label="送風機 B（5.3 kW）", value=True, on_change=self._on_fans)
        self.freq_mode_button = _segmented([("auto", "自動 PI"), ("manual", "手動")], "auto", self._on_freq_mode)
        self.freq_slider = _LabeledSlider("手動頻率", "Hz", 30, 60, 60, 30, 0, self._on_manual_freq)
        self.freq_slider.disabled = True
        self.cold_gpm = _LabeledSlider("冰水泵", "GPM", 6, 20, 12.06, 56, 2, self._on_gpm)
        self.hot_gpm = _LabeledSlider("熱水泵", "GPM", 6, 20, 12.06, 56, 2, self._on_gpm)
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
            )
        }
        self.warning_row = ft.Row(wrap=True, spacing=TOKENS.spacing_xs)
        self.event_list = ft.ListView(height=160, spacing=2)
        self.trend_chart = self._make_trend_chart()
        self.ph_chart = self._make_ph_chart()
        self._dome: SaturationDome | None = None

        legend = ft.Row(
            [self._legend_item(LINE_COLORS[state], LINE_LABELS[state]) for state in LineState],
            wrap=True, spacing=TOKENS.spacing_md,
        )
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
                ft.Text("運轉方式（兩台送風機統一切換）", size=TOKENS.caption, color=TOKENS.text_secondary),
                self.operation_button,
                ft.Row([self.fan_a, self.fan_b], wrap=True),
                ft.Text("壓縮機頻率（30～60 Hz）", size=TOKENS.caption, color=TOKENS.text_secondary),
                self.freq_mode_button,
                self.freq_slider,
                ft.Divider(height=8, color=TOKENS.border),
                self.cold_gpm,
                self.hot_gpm,
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
        trend_card = EngineeringCard("水溫與頻率趨勢", ft.Column([
            self.trend_chart,
            ft.Row([self._legend_item(COLD_COLOR, "冰水 °C"), self._legend_item(HOT_COLOR, "熱水 °C"),
                    self._legend_item(FREQ_COLOR, "壓縮機頻率 Hz")], spacing=TOKENS.spacing_md, wrap=True),
        ]), icon=ft.Icons.SHOW_CHART)
        trend_card.col = {"xs": 12, "lg": 6}
        ph_card = EngineeringCard("P-h 圖（R410A）", self.ph_chart, subtitle="目前運轉點的循環；焓基準 ASHRAE",
                                  icon=ft.Icons.STACKED_LINE_CHART)
        ph_card.col = {"xs": 12, "lg": 6}
        events_card = EngineeringCard("事件記錄", self.event_list, icon=ft.Icons.LIST_ALT)

        super().__init__(
            [
                ft.ResponsiveRow([controls_card, schematic_card], spacing=TOKENS.spacing_md,
                                 run_spacing=TOKENS.spacing_md),
                ft.ResponsiveRow(list(self.kpis.values()), spacing=TOKENS.spacing_sm, run_spacing=TOKENS.spacing_sm),
                ft.ResponsiveRow([trend_card, ph_card], spacing=TOKENS.spacing_md, run_spacing=TOKENS.spacing_md),
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
    def _make_trend_chart() -> fch.LineChart:
        """趨勢圖。

回傳：
            LineChart。"""
        return fch.LineChart(
            data_series=[], height=260, min_y=0, max_y=65, min_x=0, max_x=60,
            interactive=False,
            horizontal_grid_lines=fch.ChartGridLines(interval=10, color=TOKENS.border, width=0.6),
            left_axis=fch.ChartAxis(label_size=36, title=ft.Text("°C／Hz", size=TOKENS.caption)),
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
        self.sim = self.service.new_session(self._settings)
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
        cutoff = self.records[-1].time_s - HISTORY_LIMIT_S
        if self.records[0].time_s < cutoff:
            self.records = [r for r in self.records if r.time_s >= cutoff]
        self.latest = self.records[-1]
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
        gpm = (self._settings.cold_pump_gpm + self._settings.hot_pump_gpm) / 2
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
        """冷房／暖房：切換時套用該模式的預設環境溫度。

參數：
    _event: 事件。

回傳：
    無。"""
        operation = OperationMode(_selected(self.operation_button))
        defaults = default_settings(operation)
        self.room_slider.set_value(defaults.room_k - 273.15)
        self.outdoor_slider.set_value(defaults.outdoor_k - 273.15)
        self._apply_settings(replace(self._settings, operation=operation, room_k=defaults.room_k,
                                     outdoor_k=defaults.outdoor_k))

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
        self.freq_slider.disabled = mode is FrequencyMode.AUTO
        self._apply_settings(replace(self._settings, frequency_mode=mode,
                                     manual_frequency_hz=self.freq_slider.value))

    def _on_manual_freq(self, value: float) -> None:
        """手動頻率。

參數：
    value: Hz。

回傳：
    無。"""
        self._apply_settings(replace(self._settings, manual_frequency_hz=value))

    def _on_gpm(self, _value: float) -> None:
        """水泵 GPM。

參數：
    _value: 新值。

回傳：
    無。"""
        self._apply_settings(replace(self._settings, cold_pump_gpm=self.cold_gpm.value,
                                     hot_pump_gpm=self.hot_gpm.value))

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
        self.schematic.render(record, self._refrigerant_phase, self._water_phase, self._rotor_angle)
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
            start_min = samples[0].time_s / 60
            span_min = max(10.0, samples[-1].time_s / 60 - start_min)
            interval = next(step for step in (5, 10, 15, 30, 60) if span_min / step <= 8)
            self.trend_chart.min_x = math.floor(start_min / interval) * interval
            self.trend_chart.max_x = math.ceil((start_min + span_min) / interval) * interval
            self.trend_chart.vertical_grid_lines = fch.ChartGridLines(interval=interval, color=TOKENS.border, width=0.6)

            def series(values, color):
                return fch.LineChartData(
                    points=[fch.LineChartDataPoint(r.time_s / 60, v) for r, v in zip(samples, values)],
                    color=color, stroke_width=2, curved=False,
                )

            self.trend_chart.data_series = [
                series([r.cold_water_k - 273.15 for r in samples], COLD_COLOR),
                series([r.hot_water_k - 273.15 for r in samples], HOT_COLOR),
                series([r.frequency_hz for r in samples], FREQ_COLOR),
            ]
        else:
            self.trend_chart.data_series = []

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
