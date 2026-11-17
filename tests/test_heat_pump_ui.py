"""熱泵動態模擬頁：application service、呈現邏輯與畫面行為測試。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from application.heat_pump_simulation import HeatPumpSimulationService
from domain.heat_pump import (
    CoolingControlMode,
    FrequencyMode,
    OperationMode,
    PumpMode,
    RefrigerantMode,
    ReheatMode,
    ZoneMode,
    celsius,
    default_settings,
)
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter
from Flet_ui.ui import heat_pump_presentation as hp
from Flet_ui.ui.components import heat_pump_schematic as schematic
from Flet_ui.ui.navigation import ROUTE_BY_KEY
from Flet_ui.ui.views.heat_pump_simulation_view import HeatPumpSimulationView


@pytest.fixture(scope="module")
def service() -> HeatPumpSimulationService:
    """已建立性質表與飽和線的 service。

回傳：
    HeatPumpSimulationService。"""
    svc = HeatPumpSimulationService(ThermodynamicStateService(CanonicalUnitConverter()))
    svc.prepare()
    return svc


# ---- application service ----


def test_service_caches_table_and_dome(service: HeatPumpSimulationService) -> None:
    """性質表與飽和線只建立一次；飽和線焓值隨溫度遞增、壓力遞增。

回傳：
    無。"""
    assert service.is_ready
    assert service.table() is service.table()
    dome = service.saturation_dome()
    assert dome is service.saturation_dome()
    assert dome.reference_state == "ASHRAE"
    pressures = [p for _h, p in dome.vapor]
    assert pressures == sorted(pressures)
    # 5 °C 附近的飽和壓力約 9.33 bar（與 §4.1 一致）
    assert any(abs(p - 9.33e5) < 0.3e5 for _h, p in dome.vapor)


def test_service_new_session_uses_settings(service: HeatPumpSimulationService) -> None:
    """new_session 帶入設定與初始水溫。

回傳：
    無。"""
    sim = service.new_session(default_settings(OperationMode.HEATING), initial_cold_k=celsius(20.0))
    assert sim.settings.operation is OperationMode.HEATING
    assert sim.cold_water_k == pytest.approx(celsius(20.0))


# ---- 呈現邏輯 ----


def test_schematic_state_follows_valve_table(service: HeatPumpSimulationService) -> None:
    """每種模式的運轉管路與電磁閥狀態表一致；停機時冷媒管全為未使用。

回傳：
    無。"""
    sim = service.new_session()
    record = sim.step()
    state = hp.schematic_state(record)
    assert record.mode is RefrigerantMode.DUAL
    assert state.valves_open == frozenset({1, 6, 7, 8, 10})
    active = {key for key, value in state.pipe_states.items() if value is not hp.LineState.IDLE}
    assert active == hp.ACTIVE_PIPES[RefrigerantMode.DUAL]
    assert state.pipe_states["dis_hx2"] is hp.LineState.DISCHARGE
    assert state.pipe_states["lp_hx1"] is hp.LineState.TWO_PHASE
    assert state.outdoor_role is None
    assert state.fan_loop_tank == "cold_tank"
    assert state.pipe_colors["dis_hx2"] == hp.refrigerant_color(record.discharge_k)
    assert state.pipe_colors["suc_hx1"] == hp.refrigerant_color(record.suction_temperature_k)
    assert state.pipe_colors["dis_out"] == hp.IDLE_LINE_COLOR
    assert [c.key for c in state.callouts] == ["suction", "discharge", "liquid", "expansion"]
    assert state.callouts[1].lines[0] == f"Td {record.discharge_k - 273.15:.1f} °C"
    off = hp.schematic_state(replace(record, compressor_on=False))
    assert all(value is hp.LineState.IDLE for value in off.pipe_states.values())
    assert off.callouts == ()


def test_active_pipes_cover_a_closed_refrigerant_loop() -> None:
    """每種模式都有排氣、液管、低壓兩相與吸氣各一段（外加共用排氣管）。

回傳：
    無。"""
    by_key = {pipe.key: pipe for pipe in hp.REFRIGERANT_PIPES}
    for mode, keys in hp.ACTIVE_PIPES.items():
        states = sorted(by_key[key].refrigerant_state.value for key in keys)
        assert states.count("discharge") == 2, mode
        assert {"liquid", "two_phase", "suction"} <= set(states), mode


def test_schematic_uses_solid_fill_instead_of_gradient_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """預設以平均色單色填色取代漸層（部分桌面客戶端遇到漸層會中斷整張畫布繪製）；
    設 USE_GRADIENT 才使用漸層，且示意圖所有畫筆都不含漸層。

回傳：
    無。"""
    paint = schematic._gradient((0, 0), (10, 0), ["#000000", "#FFFFFF"])
    assert paint.gradient is None and paint.color == "#808080"
    view = schematic.HeatPumpSchematic()
    view.render(None, 0.0, 0.0, 0.0)
    assert view.canvas.shapes
    assert all(getattr(getattr(shape, "paint", None), "gradient", None) is None for shape in view.canvas.shapes)
    monkeypatch.setattr(schematic, "USE_GRADIENT", True)
    assert schematic._gradient((0, 0), (10, 0), ["#000000", "#FFFFFF"]).gradient is not None


def test_water_color_gradient() -> None:
    """冷水偏藍、熱水偏紅，超出範圍夾在端點。

回傳：
    無。"""
    cold = hp.water_color(celsius(5.0))
    hot = hp.water_color(celsius(50.0))
    assert cold == "#1F4E89"
    assert hot == "#C2410C"
    assert hp.water_color(celsius(-5.0)) == cold
    assert hp.water_color(celsius(80.0)) == hot
    mid = hp.water_color(celsius(27.0))
    assert mid == "#E9E4D8"


def test_flow_dots_move_along_polyline() -> None:
    """流動點沿折線前進並循環。

回傳：
    無。"""
    line = ((0.0, 0.0), (100.0, 0.0), (100.0, 50.0))
    assert hp.polyline_length(line) == pytest.approx(150.0)
    assert hp.point_along(line, 120.0) == pytest.approx((100.0, 20.0))
    assert hp.point_along(line, 160.0) == pytest.approx((10.0, 0.0))
    first = hp.flow_dots(line, 0.0, 50.0)
    shifted = hp.flow_dots(line, 10.0, 50.0)
    assert len(first) == 3
    assert shifted[0] == pytest.approx((10.0, 0.0))


def test_formatting_and_ph_cycle(service: HeatPumpSimulationService) -> None:
    """數值格式與 P-h 循環四點。

回傳：
    無。"""
    assert hp.format_temperature(None) == "—"
    assert hp.format_temperature(celsius(7.0)) == "7.0"
    assert hp.format_power(2_515.0) == "2.52"
    assert hp.format_pressure(9.33e5) == "9.33"
    assert hp.format_clock(3_725) == "01:02:05"
    record = service.new_session().step()
    cycle = hp.ph_cycle(record)
    assert cycle is not None and len(cycle.points) == 5
    (h1, pe), (h2, pc), (h3, _), (h4, pe4), _ = cycle.points
    assert h2 > h1 > h3 == h4 and pc > pe == pe4
    assert hp.ph_cycle(replace(record, compressor_on=False)) is None
    assert hp.downsample(list(range(1000)), 100)[-1] == 999
    assert len(hp.downsample(list(range(1000)), 100)) <= 101


# ---- 畫面 ----


def _view(service: HeatPumpSimulationService) -> tuple[HeatPumpSimulationView, list]:
    """建立同步載入、記錄動畫協程的畫面。

回傳：
    (view, 已啟動的協程清單)。"""
    started: list = []
    view = HeatPumpSimulationView(service, runner=None, start_loop=started.append)
    return view, started


def test_route_is_registered() -> None:
    """路由已註冊在冷凍系統分區。

回傳：
    無。"""
    route = ROUTE_BY_KEY["heat_pump_simulation"]
    assert route.section == "冷凍系統"
    assert route.description


def test_view_loads_plays_and_ticks(service: HeatPumpSimulationService) -> None:
    """載入 → 播放啟動動畫協程 → tick 推進模擬並更新數值、示意圖與圖表。

回傳：
    無。"""
    view, started = _view(service)
    assert view.sim is None
    view._on_play(None)
    assert view.sim is not None and not view.running
    view._on_play(None)
    assert view.running and len(started) == 1
    view._on_play(None)
    assert not view.running
    view.speed = 120
    for _ in range(10):
        view.tick()
    assert view.sim.time_s == pytest.approx(10 * 120 * 0.2)
    assert all(r.dt_s <= 5.0 for r in view.records)
    assert view.kpis["cold"].value_control.value != "—"
    assert view.schematic.state is not None
    assert len(view.trend_chart.data_series) == 4  # 自動模式另畫 PID 要求頻率
    assert view.pid_legend.visible
    assert len(view.ph_chart.data_series) == 3
    assert view.clock_text.value == "00:04:00"


def test_view_settings_reach_simulation(service: HeatPumpSimulationService) -> None:
    """控制項變更套用到模擬：暖房、送風機、手動頻率階梯、泵頻率、再熱比例。

回傳：
    無。"""
    view, _started = _view(service)
    view._on_play(None)
    view.operation_button.selected = ["heating"]
    view._on_operation(None)
    assert view.sim.settings.operation is OperationMode.HEATING
    assert view.sim.settings.outdoor_k == pytest.approx(celsius(15.0))
    assert view.room_slider.value == pytest.approx(20.0)
    view.fan_a.value = False
    view._on_fans(None)
    assert view.sim.settings.fans == frozenset({"B"})
    view.freq_mode_button.selected = ["manual"]
    view._on_freq_mode(None)
    assert not view.freq_step.disabled
    view.freq_step.set_value(40.0)
    view._on_manual_freq(40.0)
    view.tick()
    assert view.latest.frequency_hz == pytest.approx(40.0)
    assert "低於原廠" in view.freq_step.info.value
    view.cold_pump.set_value(30.0)
    view._on_pumps(30.0)
    assert view.sim.settings.cold_pump_hz == 30.0 and view.sim.settings.hot_pump_hz == 60.0
    assert view.cold_pump.info.value == "4.76 GPM · 167 W"
    view.tick()
    assert view.latest.cold_pump_gpm == pytest.approx(4.76, abs=0.01)
    view.pump_mode_button.selected = ["auto"]
    view._on_pump_mode(None)
    assert view.sim.settings.pump_mode is PumpMode.AUTO and view.cold_pump.disabled and view.hot_pump.disabled
    view.pump_mode_button.selected = ["manual"]
    view._on_pump_mode(None)
    assert view.sim.settings.pump_mode is PumpMode.MANUAL and not view.cold_pump.disabled
    assert view.reheat_slider.disabled  # 暖房不使用再熱
    view.operation_button.selected = ["cooling"]
    view._on_operation(None)
    assert not view.reheat_slider.disabled
    view.reheat_slider.set_value(40.0)
    view._on_reheat(40.0)
    assert view.sim.settings.reheat_fraction == pytest.approx(0.4)


def test_view_shows_events_and_reset(service: HeatPumpSimulationService) -> None:
    """模式切換事件顯示在事件記錄；重設後清空並回到 30 °C。

回傳：
    無。"""
    view, _started = _view(service)
    view._on_play(None)
    view.speed = 120
    for _ in range(20):  # 8 分鐘：冷房約 6.7 min 切智慧冷房
        view.tick()
    assert view.latest.mode is RefrigerantMode.SMART_COOLING
    assert any("智慧冷房" in control.value for control in view.event_list.controls)
    view._on_reset(None)
    assert view.sim.time_s == 0.0
    assert view.records == [] and view.event_list.controls == []
    assert view.sim.cold_water_k == pytest.approx(celsius(30.0))


def test_view_reports_invalid_settings(service: HeatPumpSimulationService) -> None:
    """無效設定不套用，改顯示錯誤訊息。

回傳：
    無。"""
    view, _started = _view(service)
    view._on_play(None)
    view._apply_settings(replace(view._settings, manual_frequency_hz=35.0))
    assert view.error_text.visible
    assert view.sim.settings.manual_frequency_hz != 35.0
    view._apply_settings(replace(view._settings, cold_pump_hz=45.0))
    assert view.error_text.visible and view.sim.settings.cold_pump_hz == 60.0


def test_refrigerant_color_scale_runs_blue_to_red() -> None:
    """冷媒色階：低溫偏藍、高溫偏紅，端點外夾住。

回傳：
    無。"""
    cold = hp.refrigerant_color(celsius(-20.0))
    hot = hp.refrigerant_color(celsius(120.0))
    assert cold == hp.TEMPERATURE_LEGEND[0][1]
    assert hot == hp.TEMPERATURE_LEGEND[-1][1]
    r_cold, b_cold = int(cold[1:3], 16), int(cold[5:7], 16)
    r_hot, b_hot = int(hot[1:3], 16), int(hot[5:7], 16)
    assert b_cold > r_cold and r_hot > b_hot


def test_outdoor_callout_and_role_in_smart_modes(service: HeatPumpSimulationService) -> None:
    """智慧冷房：室外換熱器當冷凝器並顯示放熱量。

回傳：
    無。"""
    sim = service.new_session()
    sim.run(15 * 60.0)
    record = sim.step()
    state = hp.schematic_state(record)
    assert state.outdoor_role == "condenser"
    outdoor = next(c for c in state.callouts if c.key == "outdoor")
    assert outdoor.lines[0] == f"冷凝放熱 {record.outdoor_heat_w / 1000:.2f} kW"


def test_ts_cycle_follows_saturation_lines(service: HeatPumpSimulationService) -> None:
    """T-s 路徑經過 Tc 飽和蒸氣／液與 Te 飽和蒸氣；四個狀態點的溫度正確。

回傳：
    無。"""
    dome = service.saturation_dome()
    record = service.new_session().step()
    path = hp.ts_cycle(record, dome.liquid_ts, dome.vapor_ts)
    assert path is not None
    assert len(path.points) == 8 and path.points[0] == path.points[-1]
    (s1, t1), (s2, t2), (s3, t3), (s4, t4) = path.markers
    assert t1 == pytest.approx(record.suction_temperature_k - 273.15)
    assert t2 == pytest.approx(record.discharge_k - 273.15)
    assert t4 == pytest.approx(record.evaporating_k - 273.15)
    assert s2 > s1 > s4 > s3
    tc = record.condensing_k - 273.15
    assert path.points[2][1] == pytest.approx(tc) and path.points[3][1] == pytest.approx(tc)
    assert path.points[2][0] > path.points[3][0]
    bare = hp.ts_cycle(record)
    assert len(bare.points) == 5


def test_reheat_coil_is_drawn_and_warning_labels(service: HeatPumpSimulationService) -> None:
    """再熱時示意圖標示盤管負荷並啟用熱水迴路；停用時為未使用；結霜警示改為「結霜／結冰」。

回傳：
    無。"""
    sim = service.new_session(replace(default_settings(OperationMode.COOLING), reheat_fraction=0.3))
    sim.run(600.0)
    record = sim.step()
    assert record.reheat_w > 0
    state = hp.schematic_state(record)
    assert state.reheat_w == pytest.approx(record.reheat_w)
    idle = hp.schematic_state(replace(record, reheat_w=0.0))
    assert idle.reheat_w == 0.0
    assert hp.REHEAT_SUPPLY.points[0][0] < hp.REHEAT_RETURN.points[0][0]  # 供水在左、回水在右
    assert hp.REHEAT_COIL.x + hp.REHEAT_COIL.width < hp.FAN_LOOP_HOT.points[0][0]  # 不壓到暖房水管
    assert "結冰" in hp.WARNING_LABELS["frost"]


def test_schematic_canvas_draws_new_elements(service: HeatPumpSimulationService) -> None:
    """畫布包含再熱盤管標籤與泵浦頻率標籤。

回傳：
    無。"""
    from Flet_ui.ui.components.heat_pump_schematic import HeatPumpSchematic

    sim = service.new_session(replace(default_settings(OperationMode.COOLING), cold_pump_hz=40.0))
    sim.run(600.0)
    record = sim.step()
    schematic = HeatPumpSchematic()
    schematic.render(record, 0.0, 0.0, 0.0, celsius(30.0))
    texts = [shape.value for shape in schematic.canvas.shapes if hasattr(shape, "value") and shape.value]
    assert any("再熱盤管" in text for text in texts)
    assert any(text.startswith("40 Hz") for text in texts)
    assert "E505DH-49A2W" in texts
    assert hp.REHEAT_COIL.key == "reheat_coil"


# ---- 受控水桶門檻圖與冷房控制架構（§8.12） ----


def test_threshold_lines_merge_overlapping_values() -> None:
    """LEGACY 冷房目標＝停機合併成一條線；目標分離則三條線，由低到高排列。

回傳：
    無。"""
    legacy = hp.threshold_lines(celsius(7.0), celsius(7.0), celsius(8.0))
    assert [line.label for line in legacy] == ["停機＝PID 目標 7.0 °C", "重啟 8.0 °C"]
    assert legacy[0].key == "target"
    split = hp.threshold_lines(celsius(7.5), celsius(7.0), celsius(8.0))
    assert [line.key for line in split] == ["stop", "target", "restart"]
    assert [line.value_c for line in split] == pytest.approx([7.0, 7.5, 8.0])


def test_control_band_zooms_and_clips(service: HeatPumpSimulationService) -> None:
    """冷房視窗為停機 − 2 ～ 重啟 + 4 K、向外取偶數（4–12 °C）；起始 30 °C 的降溫貼在上緣並標示；
    暖房改畫熱水桶與 45／46／42 °C。

回傳：
    無。"""
    sim = service.new_session(cooling_control_mode=CoolingControlMode.SPLIT)
    records = sim.run(1800.0)
    band = hp.control_band(records)
    assert band is not None and band.title.startswith("冰水桶")
    assert (band.min_y, band.max_y) == (4, 12)
    assert band.clipped and max(band.tank_c) == 12
    assert len(band.lines) == 3
    heating = service.new_session(default_settings(OperationMode.HEATING))
    hb = hp.control_band(heating.run(600.0))
    assert hb is not None and hb.title.startswith("熱水桶")
    assert [line.value_c for line in hb.lines] == pytest.approx([42.0, 45.0, 46.0])
    assert (hb.min_y, hb.max_y) == (38, 50)
    assert hp.control_band([]) is None


def test_view_control_mode_switch_resets_and_draws_thresholds(service: HeatPumpSimulationService) -> None:
    """切換冷房控制架構會重設模擬並暫停；門檻圖畫出三條參考線＋桶溫；手動頻率時不畫 PID 要求頻率。

回傳：
    無。"""
    view, _started = _view(service)
    view._on_play(None)
    view.speed = 120
    for _ in range(5):
        view.tick()
    assert len(view.control_chart.data_series) == 3  # LEGACY：兩條門檻線＋桶溫
    assert "只有兩條線" in view.control_note.value
    old = view.sim
    view.control_mode_button.selected = [CoolingControlMode.SPLIT.value]
    view._on_control_mode(None)
    assert view.sim is not old and view.sim.time_s == 0.0 and not view.running
    assert view.sim.params.control.cooling_control_mode is CoolingControlMode.SPLIT
    assert "已切換" in view.status_text.value
    for _ in range(5):
        view.tick()
    assert len(view.control_chart.data_series) == 4
    assert view.latest.control_target_k == pytest.approx(celsius(7.5))
    assert view.control_chart.min_y == 4 and view.control_chart.max_y == 12
    assert view.response_chart.max_y >= 20 and view.response_chart.max_y % 4 == 0
    view.freq_mode_button.selected = ["manual"]
    view._on_freq_mode(None)
    assert view.sim.settings.frequency_mode is FrequencyMode.MANUAL
    view.tick()
    assert len(view.trend_chart.data_series) == 3 and not view.pid_legend.visible
    view.operation_button.selected = ["heating"]
    view._on_operation(None)
    assert "暖房不受影響" in view.control_mode_text.value


# ---- 房間溫濕度模型（§8） ----


def test_time_axis_switches_to_hours_for_long_spans() -> None:
    """跨度 ≤ 4 h 用分鐘、超過改用小時，格線最多約 8 格。

回傳：
    無。"""
    short = hp.time_axis(0.0, 3 * 3600.0)
    assert short.unit == "min" and short.interval == 30
    day = hp.time_axis(6 * 3600.0, 30 * 3600.0)
    assert day.unit == "h" and day.interval == 3 and (day.min_x, day.max_x) == (6, 30)
    assert hp.format_clock(3600.0) == "01:00:00"
    assert hp.format_clock(86400.0 + 7 * 3600.0) == "第 2 天 07:00:00"


def test_room_session_and_series(service: HeatPumpSimulationService) -> None:
    """房間 session 從 06:00 起、用全系統耗電口徑；室溫視窗為舒適帶 ± 約 4 K（偶數邊界）；
    示意圖的送風機取室內控制器實際開的台數。

回傳：
    無。"""
    sim = service.new_room_session(default_settings(OperationMode.COOLING), "hot")
    assert sim.time_s == pytest.approx(6 * 3600.0)
    assert sim.params.electrical.standby_w > 0
    records = sim.run(2.5 * 3600.0)
    assert not records[0].system_enabled and records[-1].system_enabled
    series = hp.room_series(records)
    assert series is not None and (series.min_y, series.max_y) == (22, 30)
    assert series.temperature_band_c == pytest.approx((25.5, 26.5))
    assert all(30.0 < v < 90.0 for v in series.rh_pct)
    off = records[0]
    assert off.fans_running == frozenset() and hp.schematic_state(off).fans_on == frozenset()
    assert hp.room_series([r for r in records if False]) is None


def test_view_room_mode_toggles_controls_and_charts(service: HeatPumpSimulationService) -> None:
    """冷房切到房間模式：重設、停用室溫／外氣／再熱比例滑桿、顯示房間卡片與數值卡；情境與再熱方式變更會重設；
    播放後畫出室溫與 RH（含舒適帶），時間軸跨度長時改用小時；暖房時不能用房間模型。

回傳：
    無。"""
    view, _started = _view(service)
    view._on_play(None)
    assert view.sim.settings.reheat_fraction == 0.0 and view.reheat_slider.value == 0.0  # 冷房預設不再熱
    view.room_mode_button.selected = ["room"]
    view._on_room_mode(None)
    assert view.sim.room is not None and view.sim.settings.operation is OperationMode.COOLING
    assert view.sim.room.reheat_mode is ReheatMode.OFF  # 冷房＋房間模型：再熱預設關閉
    assert view.room_slider.disabled and view.outdoor_slider.disabled and view.reheat_slider.disabled
    assert view.room_card.visible and view.room_controls.visible and view.reheat_mode_button.visible
    assert not view.kpis["dehum_state"].visible
    assert all(view.kpis[key].visible for key in view._room_tiles if key != "dehum_state")
    assert "可用" in view.fan_a.label and "已切換為房間" in view.status_text.value
    view.scenario_dropdown.value = "humid"
    view.reheat_mode_button.selected = [ReheatMode.DEMAND.value]
    view.chw_reset_box.value = True
    view._on_room_option(None)
    assert view.sim.room.scenario.name.startswith("高濕")
    assert view.sim.room.reheat_mode is ReheatMode.DEMAND and view.sim.room.chw_reset
    view.speed = 1200
    for _ in range(40):  # 40 × 240 s = 2 h 40 min
        view.tick()
    assert view.kpis["room_t"].value_control.value != "—"
    assert view.kpis["condensate"].unit_control.value == "kg/h"
    assert len(view.room_temp_chart.data_series) == 3 and len(view.room_rh_chart.data_series) == 3
    assert view.room_temp_chart.min_y == 22 and view.room_temp_chart.max_y == 30
    assert "在室" in view.room_note.value
    assert view._axis.unit == "min"
    for _ in range(30):  # 再 2 h：跨度 > 4 h 改用小時
        view.tick()
    assert view._axis.unit == "h"
    assert view.room_temp_chart.bottom_axis.title.value == "時刻 (h)"
    view.operation_button.selected = ["heating"]
    view._on_operation(None)
    assert view.sim.room is None and view.room_mode_button.disabled and not view.room_card.visible
    assert view.sim.settings.operation is OperationMode.HEATING
    assert not any(view.kpis[key].visible for key in view._room_tiles)


def test_view_dehumidify_mode_uses_room_model_and_coordinated_reheat(service: HeatPumpSimulationService) -> None:
    """除濕模式：強制房間模型＋協調除濕（再熱方式不可選）、顯示除濕狀態；切回冷房時再熱回到使用者選擇（預設關閉）。

回傳：
    無。"""
    view, _started = _view(service)
    view._on_play(None)
    view.operation_button.selected = ["dehumidify"]
    view._on_operation(None)
    assert view.sim.room is not None and view.sim.room.reheat_mode is ReheatMode.COORDINATED
    assert view.sim.settings.operation is OperationMode.COOLING and view.sim.settings.reheat_fraction == 0.0
    assert view.room_mode_button.disabled and view.room_mode_button.selected == ["room"]
    assert not view.reheat_mode_button.visible and view.kpis["dehum_state"].visible
    assert "除濕" in view.mode_caption.value and "已切換為除濕" in view.status_text.value
    view.scenario_dropdown.value = "humid"
    view._on_room_option(None)
    view.speed = 1200
    for _ in range(45):  # 06:00 → 09:00
        view.tick()
    assert view.kpis["dehum_state"].value_control.value in ("除濕＋補熱", "顯冷／待機")
    view.operation_button.selected = ["cooling"]
    view._on_operation(None)
    assert view.sim.room is not None and view.sim.room.reheat_mode is ReheatMode.OFF
    assert not view.room_mode_button.disabled and view.reheat_mode_button.visible


def test_view_zoned_mode_draws_each_zone(service: HeatPumpSimulationService) -> None:
    """分區：勾選後每區各選模式、建立兩區模型；溫濕度圖每區一條線（不畫平均）、數值卡以「A｜B」並列。

回傳：
    無。"""
    view, _started = _view(service)
    view._on_play(None)
    view.room_mode_button.selected = ["room"]
    view._on_room_mode(None)
    view.zoned_box.value = True
    view.zone_buttons["A"].selected = [ZoneMode.COOLING.value]
    view.zone_buttons["B"].selected = [ZoneMode.DEHUMIDIFY.value]
    view._on_zone_option(None)
    assert view.zone_controls.visible and not view.single_room_controls.visible
    zones = view.sim.room.zones
    assert [z.mode for z in zones] == [ZoneMode.COOLING, ZoneMode.DEHUMIDIFY]
    assert "分區" in view.mode_caption.value and view.kpis["dehum_state"].visible
    view.speed = 1200
    for _ in range(25):  # 06:00 → 07:40
        view.tick()
    assert len(view.room_temp_chart.data_series) == 4  # 兩條舒適帶＋A、B
    assert "A｜B" in view.kpis["room_t"].unit_control.value
    assert view.kpis["dehum_state"].unit_control.value == "A｜B"
    assert any("B 區" in str(item.controls[1].value) for item in view.room_temp_legend.controls)
    view.zone_buttons["A"].selected = [ZoneMode.OFF.value]
    view._on_zone_option(None)
    assert view.sim.room.zones[0].mode is ZoneMode.OFF
