"""分析項目的畫面說明文字，以穩定 analysis_id 為鍵。

此表只提供說明與公式提示，計算仍由各分析模組與既有 HVAC 服務負責。
公式文字須與實際服務行為一致；實作與命名不一致的項目只保留文字說明。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisPresentation:
    """單一分析項目的簡短說明、公式提示、導覽短標籤與結果區呈現設定。

    ``key_metrics`` 列出要放在結果區頂端的結果名稱（必須與模組輸出的名稱
    相同，依序挑選、找不到的略過）；未指定時取前幾個結果。``chart_title``
    是分析附有圖表時的圖表卡片標題。兩者都只影響排版。
    """

    summary: str
    formula: str | None = None
    short_label: str | None = None
    key_metrics: tuple[str, ...] = ()
    chart_title: str = "圖表"


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
        "以可逆功相對於實際輸入功計算㶲（Exergy）效率；理論上與效能損失法結果相同，可互相驗證。",
        "η_ex = W_rev / W_in，W_rev = ṁ · [(h2 − h1) − T0 · (s2 − s1)]",
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
    "condenser.exergy": AnalysisPresentation(
        "以冷凝壓力與冷媒進出口溫度計算放熱量、熵產生與 Exergy 破壞；等效傳熱邊界溫度（熱量穿越所選控制邊界的溫度）決定熱帶走多少 Exergy。",
        "X_dest = ṁ·(ex1 − ex2) − Q_H·(1 − T0/T_b) = T0·S_gen，η = Q_H·(1 − T0/T_b) / [ṁ·(ex1 − ex2)]",
        "Exergy 分析",
        key_metrics=("Exergy 破壞率 X_dest", "Exergy 效率 η", "放熱量 Q_H", "熵產生率 S_gen"),
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
    "psychrometrics.mixing": AnalysisPresentation(
        "兩股空氣（例如外氣與回風）在同一大氣壓力下絕熱混合；各股風量以自身比容換算為乾空氣質量。",
        "W_m = Σ m_i · W_i / Σ m_i，h_m = Σ m_i · h_i / Σ m_i",
        "氣流混合",
        key_metrics=("混合後風量", "乾球溫度 Tdb", "相對濕度 RH", "比焓 h"),
        chart_title="濕空氣線圖",
    ),
    "psychrometrics.sensible": AnalysisPresentation(
        "濕度比不變的加熱或冷卻；出口低於入口露點時會凝結，請改用冷卻除濕盤管。",
        "Q = m_da · (h2 − h1)",
        "顯熱加熱／冷卻",
        key_metrics=("加熱量", "冷卻量（顯熱）", "乾球溫度 Tdb", "相對濕度 RH", "乾空氣質量流率"),
        chart_title="濕空氣線圖",
    ),
    "psychrometrics.cooling_coil": AnalysisPresentation(
        "冷卻除濕盤管的全熱、顯熱、潛熱、顯熱比與冷凝水量（忽略冷凝水焓）。",
        "Q_total = m_da · (h1 − h2)，Q_s = m_da · (h_x − h2)，h_x = h(T1, W2)",
        "冷卻除濕",
        key_metrics=("全熱負荷", "顯熱比 SHR", "冷凝水量", "乾球溫度 Tdb"),
        chart_title="濕空氣線圖",
    ),
    "psychrometrics.supply_airflow": AnalysisPresentation(
        "依室內顯熱負荷與送風溫度估算送風量（送風與室內濕度比相同）。",
        "m_da = Q_s / (h_room − h_supply)，V = m_da · v_supply",
        "送風量估算",
        key_metrics=("所需送風量", "送風溫差 ΔT", "乾球溫度 Tdb", "相對濕度 RH"),
        chart_title="濕空氣線圖",
    ),
    "cycle.vapor_compression": AnalysisPresentation(
        "單級蒸氣壓縮循環：蒸發／冷凝飽和溫度、過熱、過冷與壓縮機等熵效率，求 COP、流量與功率，並繪製 P-h 圖。",
        "COP = (h1 − h4) / (h2 − h1)，h2 = h1 + (h2s − h1) / η_isen，h4 = h3",
        "蒸氣壓縮循環",
        key_metrics=("冷房 COP", "壓縮機功率", "冷凝器放熱量", "冷媒質量流率"),
        chart_title="P-h 圖",
    ),
    "refrigerant.saturation": AnalysisPresentation(
        "已知絕對壓力（可輸入錶壓）或飽和溫度，查詢飽和液體（泡點）與飽和蒸氣（露點）的完整性質；"
        "非共沸冷媒顯示溫度滑移或泡點／露點壓力差。",
        "h_fg = h_vapor(Q=1) − h_liquid(Q=0)，滑移 = T_dew − T_bubble",
        "飽和性質",
        key_metrics=("泡點溫度", "露點溫度", "溫度滑移", "蒸發潛熱 h_fg"),
    ),
    "refrigerant.superheat_subcooling": AnalysisPresentation(
        "以量測壓力與管溫判讀過熱度（相對露點）或過冷度（相對泡點），並顯示非共沸冷媒的溫度滑移。",
        "SH = T − T_dew(P)，SC = T_bubble(P) − T",
        "過熱／過冷判讀",
        key_metrics=("狀態", "過熱度", "過冷度", "絕對壓力", "溫度滑移"),
    ),
    "psychrometric_chart.plot": AnalysisPresentation(
        "依海拔計算大氣壓力並繪製飽和線、等相對濕度線與等焓線；乾球溫度與相對濕度以逗號分隔可標示多點。",
        None,
        "濕空氣線圖",
        key_metrics=("大氣壓力",),
        chart_title="濕空氣線圖",
    ),
}


def presentation_for(analysis_id: str) -> AnalysisPresentation | None:
    """回傳分析項目的畫面說明；未登錄時回傳 None。

參數：
    analysis_id: 分析註冊表中的穩定識別碼。

回傳：
    對應的 AnalysisPresentation，或 None。"""
    return ANALYSIS_PRESENTATION.get(analysis_id)
