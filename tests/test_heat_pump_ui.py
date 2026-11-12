"""熱泵動態模擬頁：application service、呈現邏輯與畫面行為測試。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from application.heat_pump_simulation import HeatPumpSimulationService
from domain.heat_pump import OperationMode, RefrigerantMode, celsius, default_settings
from domain.thermodynamics.state_service import ThermodynamicStateService
from domain.units.converter import CanonicalUnitConverter
from Flet_ui.ui import heat_pump_presentation as hp
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
    assert len(view.trend_chart.data_series) == 3
    assert len(view.ph_chart.data_series) == 3
    assert view.clock_text.value == "00:04:00"


def test_view_settings_reach_simulation(service: HeatPumpSimulationService) -> None:
    """控制項變更套用到模擬：暖房、送風機、手動頻率、GPM。

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
    assert not view.freq_slider.disabled
    view._on_manual_freq(42.0)
    view.tick()
    assert view.latest.frequency_hz == pytest.approx(42.0)
    view.cold_gpm.set_value(15.0)
    view._on_gpm(15.0)
    assert view.sim.settings.cold_pump_gpm == pytest.approx(15.0)


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
    view._apply_settings(replace(view._settings, manual_frequency_hz=70.0))
    assert view.error_text.visible
    assert view.sim.settings.manual_frequency_hz != 70.0


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
