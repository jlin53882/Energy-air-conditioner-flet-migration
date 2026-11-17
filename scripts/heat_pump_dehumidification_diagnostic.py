"""高濕情境的除濕能力診斷（``docs/simulation-model.md`` §8.12）。

§8.7 把「水泵 60 Hz、冰水 7 °C、不再熱」稱為全力方案，但它仍受送風機分級與 25 °C 過冷下限約束：
室溫偏低時送風機會停，除濕跟著停，所以不是最大持續除濕能力測試。本腳本在高濕情境逐項放寬，
看是哪一個環節讓濕度守不住：

- D0：按需再熱（§8.7 已跑過的現行控制）。
- D1：D0 ＋ 室溫 > 25 °C 時兩台送風機都開（除濕風量最大），按需再熱把室溫拉回 26 °C 附近。
- D2：D1 ＋ 冰水 5.5 °C（低水溫；板式出水會接近 4 °C 防凍限頻，另列保護事件次數）。
- D3：D2 ＋ 再熱盤管 UA × 2、再熱增益 × 2（再熱能力不再是瓶頸）。

用法：
    uv run python scripts/heat_pump_dehumidification_diagnostic.py [--split]
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.heat_pump.comparison import Strategy, StrategyResult, run_strategy  # noqa: E402
from domain.heat_pump.cycle_table import CycleTable  # noqa: E402
from domain.heat_pump.parameters import FULL_ELECTRICAL, CoolingControlMode, HeatPumpParameters, celsius  # noqa: E402
from domain.heat_pump.room import SCENARIOS, IndoorControlParameters, ReheatMode  # noqa: E402

STEPS = {
    "D0": "按需再熱（現行控制）",
    "D1": "＋兩台送風機（室溫 > 25 °C 時全開）",
    "D2": "＋冰水 5.5 °C",
    "D3": "＋再熱能力 × 2",
}
_TABLE: CycleTable | None = None


def _table() -> CycleTable:
    """每個行程建一次性質表。

回傳：
    CycleTable。"""
    global _TABLE
    if _TABLE is None:
        from domain.thermodynamics.state_service import ThermodynamicStateService
        from domain.units.converter import CanonicalUnitConverter

        _TABLE = CycleTable.build(ThermodynamicStateService(CanonicalUnitConverter()))
    return _TABLE


def control_for(step: str) -> IndoorControlParameters:
    """各診斷步驟的室內控制參數（逐項累加）。

參數：
    step: D0–D3。

回傳：
    IndoorControlParameters。"""
    c = IndoorControlParameters()
    level = int(step[1])
    if level >= 1:
        # 室溫 > 25 °C（舒適帶下限 25.5 再留 0.5 K）時兩台送風機都開，除濕風量最大；室溫降到 25 °C 才減台，
        # 避免把房間壓到舒適帶以下（第一版門檻壓到 20 °C，室溫被拉到約 20 °C，再熱補不回來，結果無效）。
        c = replace(c, stage1_on_k=celsius(25.2), stage2_on_k=celsius(25.3), stage2_off_k=celsius(25.1),
                    stage1_off_k=celsius(25.0), overcool_floor_k=celsius(25.0), stage2_after_s=0.0)
    if level >= 2:
        c = replace(c, chw_min_k=celsius(5.5), chw_max_k=celsius(5.5))
    if level >= 3:
        c = replace(c, reheat_ua_w_k=2 * c.reheat_ua_w_k, reheat_gain_w_k=2 * c.reheat_gain_w_k)
    return c


def _job(args: tuple[str, bool]) -> tuple[str, StrategyResult]:
    """執行一個診斷步驟。

參數：
    args: (步驟, 是否用目標分離控制)。

回傳：
    (步驟, 結果)。"""
    step, split = args
    params = replace(HeatPumpParameters(), electrical=FULL_ELECTRICAL)
    if split:
        params = replace(params, control=replace(params.control, cooling_control_mode=CoolingControlMode.SPLIT))
    strategy = Strategy(f"dehum_{step}", STEPS[step], reheat_mode=ReheatMode.DEMAND)
    result = run_strategy(_table(), "humid", SCENARIOS["humid"], strategy, params=params, control=control_for(step))
    return step, result


def main() -> None:
    """命令列進入點。

回傳：
    無。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", action="store_true", help="壓縮機用目標分離控制")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_job, [(step, args.split) for step in STEPS]))
    print("| 步驟 | 內容 | kWh/日 | 顯冷／潛冷／再熱 kWh | 溫度超標 K·h | RH>60 %·h | RH 最高 | 平均室溫／含濕量 | "
          "冰水桶平均 | 主機 COP | 保護事件 次/日 | 絕對門檻 |")
    print("|" + "---|" * 12)
    for step, r in rows:
        print(f"| {step} | {STEPS[step]} | {r.energy_kwh:.2f} | {r.sensible_kwh:.1f}／{r.latent_kwh:.1f}／{r.reheat_kwh:.1f} | "
              f"{r.temperature_exceed_kh:.2f} | {r.humidity_high_pct_h:.1f} | {r.max_rh * 100:.0f} % | "
              f"{r.mean_room_k - 273.15:.2f} °C／{r.mean_humidity_ratio * 1000:.1f} g/kg | "
              f"{r.cold_tank_mean_k - 273.15:.2f} °C | {r.chiller_cop or 0:.2f} | {r.protection_events} | {'是' if r.absolute_ok() else '否'} |")


if __name__ == "__main__":
    main()
