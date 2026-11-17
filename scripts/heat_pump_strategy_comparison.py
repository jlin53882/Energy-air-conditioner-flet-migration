"""熱泵節能策略比較（``docs/simulation-model.md`` §8.6–§8.8）。

用法：
    uv run python scripts/heat_pump_strategy_comparison.py [--scenarios hot,humid,mild] [--strategies base,combo3]
        [--variant <見 VARIANTS>] [--core]

每個（情境, 策略）重複同一日工況直到週期穩態（dt 5 s），多行程平行執行；輸出 Markdown 表格。
``--variant`` 做敏感度分析（盤管參數、房間吸放濕緩衝、水泵有效功率、壓縮機最短停機）。
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
from domain.heat_pump.room import (  # noqa: E402
    ALTERNATIVE_COILS,
    DEFAULT_COILS,
    REDUCED_AIR_UA_COILS,
    SCENARIOS,
    TOTAL_FLOW_COILS,
    RoomParameters,
)

VARIANTS = {
    "default": "預設（盤管 n 0.8、吸放濕緩衝 3 倍、水泵功率因數 1）",
    "coil_n05": "盤管參數改用 n 0.5 的擬合組",
    "moisture_x1": "房間吸放濕緩衝 1 倍（只有室內空氣）",
    "moisture_x5": "房間吸放濕緩衝 5 倍",
    "pump_pf075": "水泵有效功率 = 實測 √3·V·I × 0.75",
    "coil_ua08": "盤管風側 UA × 0.8（表 8.1.1 空氣側冷量可能高估）",
    "coil_total_flow": "表 8.1.1 流量為 A+B 總流量（B 只分到 60 %）重新擬合",
    "hot_pump_x05": "熱水泵（無實測）耗電 × 0.5",
    "hot_pump_x15": "熱水泵（無實測）耗電 × 1.5",
    "min_off_600": "壓縮機最短停機 600 s（啟動 ≤ 6 次/h，設備保護）",
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
    elif variant == "coil_ua08":
        coils = REDUCED_AIR_UA_COILS
    elif variant == "coil_total_flow":
        coils = TOTAL_FLOW_COILS
    elif variant in ("hot_pump_x05", "hot_pump_x15"):
        factor = 0.5 if variant == "hot_pump_x05" else 1.5
        params = replace(params, hot_pump=replace(params.hot_pump, power_factor=factor))
    elif variant == "min_off_600":
        params = replace(params, control=replace(params.control, min_off_time_s=600.0))
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
        current = next((r for r in rows if r.strategy == "base"), None)
        full = next((r for r in rows if r.strategy == "reheat_off"), None)
        best = best_strategy(rows)
        conditional = best_relative_only(rows) if best is None else None
        lines.append(f"**{scenario.name}（{key}）**\n")
        if full is not None and not full.absolute_ok():
            lines.append("> **容量檢查**：全力方案（水泵 60 Hz、冰水 7 °C、不再熱）也未通過絕對門檻，"
                         "此情境以現有設備（或此假設房間）達不到門檻。\n")
        if best is None:
            lines.append("> 沒有任何策略通過絕對舒適門檻。☆ 為**條件式**最低用電（只要求不劣於舒適基準與數值檢查），"
                         "只表示「與基準一樣不舒適時誰較省電」，不代表達標。\n")
        lines.append("| 策略 | 全系統 kWh/日 | 相對舒適基準 | 相對現行預設 | 壓縮機／水泵／送風機／室外風扇 | 顯冷／潛冷／再熱 kWh | "
                     "溫度超標 K·h | RH>60 %·h | RH<50 %·h | 平均室溫／含濕量 | 08:00 室溫 | 室溫範圍 °C | RH 最高 | 達標 | "
                     "主機 COP | 平均冰水設定 | 啟動 次/日（次/h） | 天數 | 日用電全距 | 殘差修正 | 絕對門檻 | 不劣於基準 |")
        lines.append("|" + "---|" * 22)
        for r in rows:
            rel = f"{(r.energy_kwh / base.energy_kwh - 1) * 100:+.1f} %" if base else "—"
            rel_cur = f"{(r.energy_kwh / current.energy_kwh - 1) * 100:+.1f} %" if current else "—"
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
            starts = f"{r.compressor_starts}（{r.starts_per_hour:.1f}{'，>6' if r.starts_per_hour > 6 else ''}）"
            lines.append(
                f"| {r.name}{mark}{flag} | {r.energy_kwh:.2f} | {rel} | {rel_cur} | "
                f"{r.compressor_kwh:.2f}／{r.pump_kwh:.2f}／{r.fan_kwh:.2f}／{r.outdoor_fan_kwh:.2f} | "
                f"{r.sensible_kwh:.1f}／{r.latent_kwh:.1f}／{r.reheat_kwh:.1f} | {r.temperature_exceed_kh:.2f} | "
                f"{r.humidity_high_pct_h:.1f} | {r.humidity_low_pct_h:.1f} | "
                f"{r.mean_room_k - 273.15:.2f} °C／{r.mean_humidity_ratio * 1000:.1f} g/kg | "
                f"{r.occupancy_start_k - 273.15:.1f} | "
                f"{r.min_temperature_k - 273.15:.1f}–{r.max_temperature_k - 273.15:.1f} | {r.max_rh * 100:.0f} % | "
                f"{_fmt_pulldown(r.pulldown_s)} | {r.chiller_cop or 0:.2f} | {r.mean_chw_setpoint_k - 273.15:.1f} °C | "
                f"{starts} | {r.days}{'' if r.periodic else '（未收斂）'} | {r.daily_kwh_range:.2f} | "
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
