"""熱泵節能策略比較（``docs/simulation-model.md`` §8.7）。

用法：``uv run python scripts/heat_pump_strategy_comparison.py [--scenarios hot,humid,mild] [--strategies base,combo]``

每個（情境, 策略）連跑兩天（dt 5 s），以多行程平行執行；輸出 Markdown 表格。
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.heat_pump.comparison import (  # noqa: E402
    REFERENCE_CANDIDATES,
    STRATEGIES,
    Strategy,
    StrategyResult,
    best_strategy,
    reference_result,
    run_strategy,
)
from domain.heat_pump.cycle_table import CycleTable  # noqa: E402
from domain.heat_pump.room import SCENARIOS  # noqa: E402

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


def _job(args: tuple[str, Strategy]) -> StrategyResult:
    """執行一個（情境, 策略）。

參數：
    args: (情境代碼, 策略)。

回傳：
    StrategyResult。"""
    scenario_key, strategy = args
    return run_strategy(_table(), scenario_key, SCENARIOS[scenario_key], strategy)


def _fmt_pulldown(value: float | None) -> str:
    """達標時間格式。

參數：
    value: 秒或 None。

回傳：
    文字。"""
    return "未達標" if value is None else f"{value / 60:.0f} min"


def render(results: list[StrategyResult]) -> str:
    """輸出 Markdown。

參數：
    results: 全部結果。

回傳：
    Markdown 文字。"""
    lines: list[str] = []
    for key, scenario in SCENARIOS.items():
        rows = [r for r in results if r.scenario == key]
        if not rows:
            continue
        base = reference_result(rows)
        best = best_strategy(rows)
        lines.append(f"#### {scenario.name}（{key}）\n")
        lines.append("| 策略 | 修正後 kWh | 相對舒適基準 | 壓縮機／水泵／送風機／室外風扇 kWh | 顯冷／潛冷／再熱 kWh | "
                     "溫度超標 K·h | RH>60 %·h | RH<50 %·h | 室溫範圍 °C | RH 最高 | 達標 | 主機 COP | 平均冰水設定 | 啟動次數 | 舒適度不劣於舒適基準 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            rel = f"{(r.corrected_energy_kwh / base.corrected_energy_kwh - 1) * 100:+.1f} %" if base else "—"
            if base is None:
                ok = "—"
            elif r.strategy == base.strategy:
                ok = "—（舒適基準）"
            else:
                ok = "是" if r.comfort_ok(base) else "**否**"
            mark = " ⭐" if best is not None and r.strategy == best.strategy else ""
            lines.append(
                f"| {r.name}{mark} | {r.corrected_energy_kwh:.2f} | {rel} | "
                f"{r.compressor_kwh:.2f}／{r.pump_kwh:.2f}／{r.fan_kwh:.2f}／{r.outdoor_fan_kwh:.2f} | "
                f"{r.sensible_kwh:.1f}／{r.latent_kwh:.1f}／{r.reheat_kwh:.1f} | {r.temperature_exceed_kh:.2f} | "
                f"{r.humidity_high_pct_h:.1f} | {r.humidity_low_pct_h:.1f} | "
                f"{r.min_temperature_k - 273.15:.1f}–{r.max_temperature_k - 273.15:.1f} | {r.max_rh * 100:.0f} % | "
                f"{_fmt_pulldown(r.pulldown_s)} | {r.chiller_cop or 0:.2f} | {r.mean_chw_setpoint_k - 273.15:.1f} °C | "
                f"{r.compressor_starts} | {ok} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    """命令列進入點。

回傳：
    無。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--strategies", default=",".join(s.key for s in STRATEGIES))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    scenarios = args.scenarios.split(",")
    wanted = [s for s in STRATEGIES if s.key in args.strategies.split(",")]
    by_key = {s.key: s for s in STRATEGIES}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        # 第一輪：舒適基準候選；第二輪：單一策略疊在各情境的舒適基準再熱方式上。
        first = [(sc, by_key[k]) for sc in scenarios for k in REFERENCE_CANDIDATES]
        results = list(pool.map(_job, first))
        references = {sc: by_key[reference_result([r for r in results if r.scenario == sc]).strategy]
                      for sc in scenarios}
        second = [(sc, st.layered_on(references[sc])) for sc in scenarios for st in wanted
                  if st.key not in REFERENCE_CANDIDATES]
        results += list(pool.map(_job, second))
    order = {s.key: i for i, s in enumerate(STRATEGIES)}
    results.sort(key=lambda r: (scenarios.index(r.scenario), order[r.strategy]))
    print(render(results))


if __name__ == "__main__":
    main()
