"""熱泵節能策略比較（``docs/simulation-model.md`` §8.6–§8.8）。

用法：
    uv run python scripts/heat_pump_strategy_comparison.py [--scenarios hot,humid,mild] [--strategies base,combo3]
        [--variant default|coil_n05|moisture_x1|moisture_x5|pump_pf075] [--core]

每個（情境, 策略）重複同一日工況直到週期穩態（dt 5 s），多行程平行執行；輸出 Markdown 表格。
``--variant`` 做敏感度分析（盤管參數、房間吸放濕緩衝、水泵有效功率）。
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.heat_pump.comparison import (  # noqa: E402
    CORE_STRATEGIES,
    REFERENCE_CANDIDATES,
    STRATEGIES,
    Strategy,
    StrategyResult,
    acceptable,
    best_relative_only,
    best_strategy,
    reference_result,
    run_strategy,
)
from domain.heat_pump.cycle_table import CycleTable  # noqa: E402
from domain.heat_pump.parameters import FULL_ELECTRICAL, HeatPumpParameters  # noqa: E402
from domain.heat_pump.room import ALTERNATIVE_COILS, DEFAULT_COILS, SCENARIOS, RoomParameters  # noqa: E402

VARIANTS = {
    "default": "預設（盤管 n 0.8、吸放濕緩衝 3 倍、水泵功率因數 1）",
    "coil_n05": "盤管參數改用 n 0.5 的擬合組",
    "moisture_x1": "房間吸放濕緩衝 1 倍（只有室內空氣）",
    "moisture_x5": "房間吸放濕緩衝 5 倍",
    "pump_pf075": "水泵有效功率 = 實測 √3·V·I × 0.75",
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


def _job(args: tuple[str, Strategy, str]) -> StrategyResult:
    """執行一個（情境, 策略, 敏感度變體）。

參數：
    args: (情境代碼, 策略, 變體)。

回傳：
    StrategyResult。"""
    scenario_key, strategy, variant = args
    params = replace(HeatPumpParameters(), electrical=FULL_ELECTRICAL)
    coils = DEFAULT_COILS
    room = RoomParameters()
    if variant == "coil_n05":
        coils = ALTERNATIVE_COILS
    elif variant == "moisture_x1":
        room = replace(room, moisture_buffer_factor=1.0)
    elif variant == "moisture_x5":
        room = replace(room, moisture_buffer_factor=5.0)
    elif variant == "pump_pf075":
        params = replace(params, cold_pump=replace(params.cold_pump, power_factor=0.75),
                         hot_pump=replace(params.hot_pump, power_factor=0.75))
    return run_strategy(_table(), scenario_key, SCENARIOS[scenario_key], strategy, params=params, room_params=room,
                        coils=coils)


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
        conditional = best_relative_only(rows) if best is None else None
        lines.append(f"**{scenario.name}（{key}）**\n")
        if best is None:
            lines.append("> 沒有任何策略通過絕對舒適門檻。☆ 為**條件式**最低用電（只要求不劣於舒適基準與數值檢查），"
                         "結論只表示「與基準一樣不舒適時誰較省電」，不代表達標。\n")
        lines.append("| 策略 | 全系統 kWh | 相對舒適基準 | 壓縮機／水泵／送風機／室外風扇 | 顯冷／潛冷／再熱 kWh | "
                     "溫度超標 K·h | RH>60 %·h | RH<50 %·h | 室溫範圍 °C | RH 最高 | 達標 | 主機 COP | "
                     "平均冰水設定 | 啟動次數 | 天數 | 日間變動 kWh | 殘差修正 kWh | 絕對門檻 | 不劣於基準 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            rel = f"{(r.energy_kwh / base.energy_kwh - 1) * 100:+.1f} %" if base else "—"
            if base is None:
                rel_ok = "—"
            elif r.strategy == base.strategy:
                rel_ok = "（舒適基準）"
            else:
                rel_ok = "是" if r.comfort_ok(base) else "**否**"
            mark = " ⭐" if best is not None and r.strategy == best.strategy else ""
            if conditional is not None and r.strategy == conditional.strategy:
                mark = " ☆"
            flag = "" if r.valid else " ⚠"
            lines.append(
                f"| {r.name}{mark}{flag} | {r.energy_kwh:.2f} | {rel} | "
                f"{r.compressor_kwh:.2f}／{r.pump_kwh:.2f}／{r.fan_kwh:.2f}／{r.outdoor_fan_kwh:.2f} | "
                f"{r.sensible_kwh:.1f}／{r.latent_kwh:.1f}／{r.reheat_kwh:.1f} | {r.temperature_exceed_kh:.2f} | "
                f"{r.humidity_high_pct_h:.1f} | {r.humidity_low_pct_h:.1f} | "
                f"{r.min_temperature_k - 273.15:.1f}–{r.max_temperature_k - 273.15:.1f} | {r.max_rh * 100:.0f} % | "
                f"{_fmt_pulldown(r.pulldown_s)} | {r.chiller_cop or 0:.2f} | {r.mean_chw_setpoint_k - 273.15:.1f} °C | "
                f"{r.compressor_starts} | {r.days}{'' if r.periodic else '（未收斂）'} | {r.day_to_day_kwh:.2f} | "
                f"{r.storage_correction_kwh:+.2f} | {'是' if r.absolute_ok() else '**否**'} | {rel_ok} |"
            )
        acceptable_count = sum(1 for r in rows if base is not None and acceptable(r, base))
        lines.append(f"\n可列入比較（數值檢查、絕對門檻、不劣於基準都通過）：{acceptable_count}／{len(rows)}。\n")
    return "\n".join(lines)


def main() -> None:
    """命令列進入點。

回傳：
    無。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--strategies", default=",".join(s.key for s in STRATEGIES))
    parser.add_argument("--core", action="store_true", help="只跑三組核心比較（基準、水泵最佳化、水泵＋冰水重設＋按需再熱）")
    parser.add_argument("--variant", default="default", choices=sorted(VARIANTS))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    scenarios = args.scenarios.split(",")
    keys = CORE_STRATEGIES if args.core else tuple(args.strategies.split(","))
    wanted = [s for s in STRATEGIES if s.key in keys]
    by_key = {s.key: s for s in STRATEGIES}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        # 第一輪：舒適基準候選；第二輪：單一策略疊在各情境的舒適基準再熱方式上。
        first = [(sc, by_key[k], args.variant) for sc in scenarios for k in REFERENCE_CANDIDATES]
        results = list(pool.map(_job, first))
        references = {sc: by_key[reference_result([r for r in results if r.scenario == sc]).strategy]
                      for sc in scenarios}
        second = [(sc, st.layered_on(references[sc]), args.variant) for sc in scenarios for st in wanted
                  if st.key not in REFERENCE_CANDIDATES]
        results += list(pool.map(_job, second))
    order = {s.key: i for i, s in enumerate(STRATEGIES)}
    results.sort(key=lambda r: (scenarios.index(r.scenario), order[r.strategy]))
    print(f"敏感度變體：{VARIANTS[args.variant]}\n")
    print(render(results))


if __name__ == "__main__":
    main()
