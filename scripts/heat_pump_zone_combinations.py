"""A、B 兩區各自選模式（冷房／除濕／停止）的組合比較（``docs/simulation-model.md`` §8.12.9）。

第一階段：共用冰水的組合（冷房／冷房、冷房／除濕、除濕／除濕、單台停止）。前提是兩台送風機的再熱可獨立控制（假設）。
同時冷熱（暖房／冷房、暖房／除濕）需要每台能獨立選冰水或熱水，目前水路是兩台統一切換，屬第二階段，不在此腳本。

用法：
    uv run python scripts/heat_pump_zone_combinations.py [--scenarios summer,rainy] [--days 5] [--json out.json]

每個組合重複同一日工況 ``--days`` 天，統計最後 2 天平均（比 §8.6 的週期穩態判定簡化）。
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.heat_pump.comparison import ZoneComboResult, run_zone_combination  # noqa: E402
from domain.heat_pump.cycle_table import CycleTable  # noqa: E402
from domain.heat_pump.room import ZONE_SCENARIOS, ZoneMode  # noqa: E402

C, D, OFF = ZoneMode.COOLING, ZoneMode.DEHUMIDIFY, ZoneMode.OFF
COMBINATIONS = {
    "summer": ((C, C), (C, D), (D, D), (C, OFF), (OFF, D)),
    "rainy": ((C, C), (C, D), (D, D), (OFF, D)),
}
MODE_NAMES = {"cooling": "冷房", "dehumidify": "除濕", "off": "停止"}
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


def _job(args: tuple[str, ZoneMode, ZoneMode, bool, int]) -> tuple[bool, ZoneComboResult]:
    """執行一個組合。

參數：
    args: (情境, A 模式, B 模式, 冰水重設, 天數)。

回傳：
    (冰水重設, 結果)。"""
    scenario, mode_a, mode_b, chw_reset, days = args
    return chw_reset, run_zone_combination(_table(), scenario, mode_a, mode_b, chw_reset=chw_reset, days=days)


def _zone_text(zone) -> str:
    """單區摘要。

參數：
    zone: ZoneComfort。

回傳：
    文字。"""
    if zone.mode == "off":
        return f"停止（{zone.mean_temperature_k - 273.15:.1f} °C／{zone.min_rh * 100:.0f}–{zone.max_rh * 100:.0f} %）"
    flag = "" if zone.absolute_ok() else " ✗"
    return (f"{zone.mean_temperature_k - 273.15:.2f} °C、RH {zone.min_rh * 100:.0f}–{zone.max_rh * 100:.0f} %、"
            f"超標 {zone.temperature_exceed_kh:.2f} K·h／高 {zone.humidity_high_pct_h:.1f}／低 {zone.humidity_low_pct_h:.1f} %·h、"
            f"再熱 {zone.reheat_kwh:.1f} kWh、凝結 {zone.condensate_kg:.1f} kg{flag}")


def render(rows: list[tuple[bool, ZoneComboResult]]) -> str:
    """Markdown 表格。

參數：
    rows: (冰水重設, 結果)。

回傳：
    文字。"""
    lines = ["| 情境 | A／B | 冰水重設 | 全系統 kWh/日 | 壓縮機／水泵／送風機 | A 區 | B 區 | 啟動 次/h（平均／滾動 1 h 最多） | "
             "冰水桶平均 | 智慧冷房占運轉 | 絕對門檻 |", "|" + "---|" * 11]
    for chw_reset, r in rows:
        lines.append(
            f"| {r.scenario} | {MODE_NAMES[r.mode_a]}／{MODE_NAMES[r.mode_b]} | {'有' if chw_reset else '無'} | "
            f"{r.energy_kwh:.2f} | {r.compressor_kwh:.2f}／{r.pump_kwh:.2f}／{r.fan_kwh:.2f} | "
            f"{_zone_text(r.zones[0])} | {_zone_text(r.zones[1])} | {r.starts_per_hour:.1f}／{r.max_starts_rolling_1h} | "
            f"{r.mean_cold_tank_k - 273.15:.2f} °C | {r.smart_cooling_fraction * 100:.0f} % | "
            f"{'是' if r.absolute_ok else '**否**'} |")
    return "\n".join(lines)


def main() -> None:
    """命令列進入點。

回傳：
    無。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default=",".join(COMBINATIONS))
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    jobs = [(sc, a, b, reset, args.days) for sc in args.scenarios.split(",") for a, b in COMBINATIONS[sc]
            for reset in (False, True)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_job, jobs))
    for sc in args.scenarios.split(","):
        print(f"**{ZONE_SCENARIOS[sc][0]}（{sc}）**\n")
        print(render([row for row in rows if row[1].scenario == sc]) + "\n")
    if args.json:
        Path(args.json).write_text(json.dumps([dict(asdict(r), chw_reset=reset) for reset, r in rows],
                                              ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
