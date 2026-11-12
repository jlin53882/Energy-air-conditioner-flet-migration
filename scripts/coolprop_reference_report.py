"""產生 R717（Ammonia）reference state 診斷報告（Markdown），可重現本專案的物性驗證數字。

用法：
    uv run python scripts/coolprop_reference_report.py > report.md

報告內容全部由目前安裝的 CoolProp 實際計算，不含任何手寫的計算結果；Siemens 表格數值
只作為外部交叉比對資料（來源：Siemens Building Technologies「Refrigeration Technology」
Table 2-5「Vapor table of Ammonia (R717, NH3)」，壓力為絕對壓 bar）。
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import CoolProp.CoolProp as CP  # noqa: E402

from application.models import SaturationPropertiesRequest  # noqa: E402
from application.refrigeration import RefrigerationService  # noqa: E402
from domain.thermodynamics.reference_state import coolprop_version  # noqa: E402
from domain.thermodynamics.state_service import ThermodynamicStateService  # noqa: E402
from domain.thermodynamics.thermo_policy import resolve_thermo_policy  # noqa: E402
from domain.units.converter import CanonicalUnitConverter  # noqa: E402

FLUID = "R717"
STANDARD_ATMOSPHERE_PA = 101_325.0
# (°C, p [bar abs], h' [kJ/kg], h'' [kJ/kg], r [kJ/kg])
SIEMENS_ROWS = (
    (-40.0, 0.72, 20.3, 1407.3, 1387.0),
    (-30.0, 1.20, 64.6, 1422.5, 1357.8),
    (-25.0, 1.52, 87.0, 1429.6, 1342.7),
    (-20.0, 1.90, 109.4, 1436.5, 1327.1),
    (-10.0, 2.91, 154.5, 1449.3, 1294.8),
    (0.0, 4.29, 200.0, 1460.7, 1260.7),
    (20.0, 8.57, 292.2, 1478.7, 1186.6),
    (40.0, 15.55, 386.4, 1489.6, 1103.2),
    (60.0, 26.14, 484.4, 1491.5, 1007.1),
    (100.0, 62.52, 708.2, 1451.2, 743.0),
)


def main() -> None:
    """輸出 Markdown 報告。"""
    service = ThermodynamicStateService(CanonicalUnitConverter())
    refrigeration = RefrigerationService(service)
    out: list[str] = []
    add = out.append

    add("# R717 reference state 診斷報告")
    add("")
    add(f"- CoolProp：{coolprop_version()}（git {CP.get_global_param_string('gitrevision')}）")
    add(f"- Python：{platform.python_version()}；平台：{platform.platform()}")
    add(f"- 流體輸入：`{FLUID}` → canonical `{CP.get_fluid_param_string(FLUID, 'name')}`；"
        f"別名：{CP.get_fluid_param_string(FLUID, 'aliases')}")
    add(f"- 狀態方程：{CP.get_fluid_param_string(FLUID, 'BibTeX-EOS')}（HEOS backend）")
    add(f"- 臨界點：{CP.PropsSI('Tcrit', FLUID) - 273.15:.2f} °C、{CP.PropsSI('pcrit', FLUID) / 1e5:.2f} bar"
        "（Siemens 表：132.35 °C、113.53 bar）")
    add("")

    policy = refrigeration.resolve(FLUID, "Auto")
    add("## Auto 解析（冷凍工作流）")
    add("")
    for label, value in policy.summary_rows():
        add(f"- {label}：{value}")
    add("")

    add("## −25 °C（248.15 K）飽和狀態，各基準")
    add("")
    add("| requested | effective | P_sat [kPa abs] | h_f [kJ/kg] | h_g [kJ/kg] | h_fg [kJ/kg] | s_g [kJ/(kg·K)] |")
    add("|---|---|---:|---:|---:|---:|---:|")
    for requested in ("Auto", "IIR", "ASHRAE", "NBP", "DEF"):
        resolved = refrigeration.resolve(FLUID, requested)
        result = refrigeration.saturation_properties(SaturationPropertiesRequest(
            FLUID, temperature_k=248.15, reference_state=resolved.reference_state
        ))
        add(f"| {requested} | {resolved.reference_state} | {result.vapor.pressure_pa / 1000:.3f} | "
            f"{result.liquid.enthalpy_j_kg / 1000:.3f} | {result.vapor.enthalpy_j_kg / 1000:.3f} | "
            f"{(result.vapor.enthalpy_j_kg - result.liquid.enthalpy_j_kg) / 1000:.3f} | "
            f"{result.vapor.entropy_j_kgk / 1000:.5f} |")
    add("")

    add("## 壓力語義：152 kPa（abs）與 152 kPag")
    add("")
    add("| 輸入 | 送入計算的絕對壓力 [Pa] | T_sat [°C] | h_g（IIR）[kJ/kg] |")
    add("|---|---:|---:|---:|")
    for label, pressure in (("152 kPa abs", 152_000.0), ("152 kPag（+101.325 kPa）", 152_000.0 + STANDARD_ATMOSPHERE_PA)):
        result = refrigeration.saturation_properties(SaturationPropertiesRequest(
            FLUID, pressure_pa=pressure, reference_state="IIR"
        ))
        add(f"| {label} | {pressure:.0f} | {result.vapor.temperature_k - 273.15:.3f} | "
            f"{result.vapor.enthalpy_j_kg / 1000:.3f} |")
    add("")

    add("## 與 Siemens Table 2-5 交叉比對（IIR）")
    add("")
    add("| T [°C] | p 表/CP [bar] | Δp | h' 表/CP | Δh' | h'' 表/CP | Δh'' | r 表/CP | Δr |")
    add("|---:|---|---:|---|---:|---|---:|---|---:|")
    for t_c, p_bar, h_f, h_g, latent in SIEMENS_ROWS:
        temperature = t_c + 273.15
        liquid = service.calculate_state_si(FLUID, [("T", temperature), ("Q", 0.0)], "IIR")
        vapor = service.calculate_state_si(FLUID, [("T", temperature), ("Q", 1.0)], "IIR")
        cp_p, cp_hf, cp_hg = liquid["P"] / 1e5, liquid["H"] / 1000, vapor["H"] / 1000
        cp_r = cp_hg - cp_hf
        add(f"| {t_c:.0f} | {p_bar:.2f} / {cp_p:.3f} | {cp_p - p_bar:+.3f} | {h_f:.1f} / {cp_hf:.2f} | "
            f"{cp_hf - h_f:+.2f} | {h_g:.1f} / {cp_hg:.2f} | {cp_hg - h_g:+.2f} | {latent:.1f} / {cp_r:.2f} | "
            f"{cp_r - latent:+.2f} |")
    add("")

    add("## Auto 解析矩陣（不維護冷媒白名單）")
    add("")
    add("| 流體 | 模型 | 基準 | 備援說明 |")
    add("|---|---|---|---|")
    for fluid in ("R717", "NH3", "R134a", "R32", "R410A", "R744", "Water", "Air", "Nitrogen"):
        resolved = resolve_thermo_policy(fluid)
        add(f"| {fluid} | {resolved.model_label} | {resolved.reference_label} | {resolved.fallback_reason or '—'} |")
    print("\n".join(out))


if __name__ == "__main__":
    main()
