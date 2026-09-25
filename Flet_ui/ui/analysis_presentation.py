"""分析項目的畫面說明文字，以穩定 analysis_id 為鍵。

此表只提供說明與公式提示，計算仍由各分析模組與既有 HVAC 服務負責。
公式文字須與實際服務行為一致；實作與命名不一致的項目只保留文字說明。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisPresentation:
    """單一分析項目的簡短說明、公式提示與導覽短標籤。"""

    summary: str
    formula: str | None = None
    short_label: str | None = None


ANALYSIS_PRESENTATION: dict[str, AnalysisPresentation] = {
    "compressor.compression_ratio": AnalysisPresentation(
        "以吸入與排出絕對壓力計算壓縮比；選擇錶壓力時會先加上大氣壓力。",
        "CR = P_discharge,abs / P_suction,abs",
        "壓縮比",
    ),
    "compressor.work": AnalysisPresentation(
        "穩流壓縮機輸入功率，不考慮殼體熱傳。",
        "W_in = m · (h2 − h1)",
        "壓縮功",
    ),
    "compressor.isentropic_efficiency": AnalysisPresentation(
        "等熵壓縮焓升與實際壓縮焓升之比。",
        "η_isen = (h2s − h1) / (h2 − h1)",
        "等熵效率",
    ),
    "compressor.refrigeration_capacity": AnalysisPresentation(
        "由壓縮機排氣量、容積效率、吸入密度與蒸發器焓差估算系統冷凍能力。",
        "Q_L = V · η_vol · ρ1 · (h1 − h4)",
        "冷凍能力",
    ),
    "compressor.work_heat_transfer": AnalysisPresentation(
        "考慮壓縮機對外散熱時的輸入功率。",
        "W_in = m · (h2 − h1) + Q_out",
        "壓縮功（含熱傳）",
    ),
    "compressor.reversible_work": AnalysisPresentation(
        "相同進出口狀態與死狀態溫度下的可逆功率。",
        "W_rev = m · [(h2 − h1) − T0 · (s2 − s1)]",
        "可逆功",
    ),
    "compressor.exergy_destruction": AnalysisPresentation(
        "以死狀態 (T0, h0, s0) 為基準，計算壓縮過程的㶲（Exergy）破壞率。",
        "X_dest = m · (ψ1 − ψ2) + W_in，ψ = (h − h0) − T0 · (s − s0)",
        "Exergy 破壞",
    ),
    "compressor.volumetric_efficiency": AnalysisPresentation(
        "由餘隙容積比與進出口比容計算容積效率。",
        "η_vol = 1 − R · (v1 / v2 − 1)",
        "容積效率",
    ),
    "compressor.exergy_efficiency_loss": AnalysisPresentation(
        "以㶲（Exergy）破壞率相對於實際輸入功計算效能。",
        "η = 1 − X_dest / W_in",
        "效能損失",
    ),
    "compressor.exergy_efficiency_ratio": AnalysisPresentation(
        "以死狀態為基準評估壓縮機的㶲（Exergy）效率。",
        None,
        "Exergy 效率",
    ),
    "compressor.combined_example": AnalysisPresentation(
        "以 CoolProp 查詢進出口狀態，一次計算容積效率、輸入功、等熵效率、㶲（Exergy）破壞率與效率。",
        None,
        "綜合分析",
    ),
    "evaporator.heat_rate": AnalysisPresentation(
        "冷媒在蒸發器中吸收的熱量（出口焓減入口焓）。",
        "Q_e = m · (h2 − h1)",
        "熱交換率",
    ),
    "condenser.heat_rate": AnalysisPresentation(
        "冷媒在冷凝器中放出的熱量（入口焓減出口焓）。",
        "Q_c = m · (h1 − h2)",
        "放熱率",
    ),
    "psychrometrics.tdb_twb": AnalysisPresentation(
        "依海拔推算大氣壓力，再以乾球與濕球溫度求得濕空氣完整性質（ASHRAE 模型）。",
        None,
        "乾球 + 濕球",
    ),
    "psychrometrics.tdb_rh": AnalysisPresentation(
        "依海拔推算大氣壓力，再以乾球溫度與相對濕度求得濕空氣完整性質（ASHRAE 模型）。",
        None,
        "乾球 + 相對濕度",
    ),
}


def presentation_for(analysis_id: str) -> AnalysisPresentation | None:
    """回傳分析項目的畫面說明；未登錄時回傳 None。

參數：
    analysis_id: 分析註冊表中的穩定識別碼。

回傳：
    對應的 AnalysisPresentation，或 None。"""
    return ANALYSIS_PRESENTATION.get(analysis_id)
