# analysis_modules/coolprop_utils.py
# ======================================================
# 通用 CoolProp + Matplotlib 圖表繪製模組
# ======================================================

import matplotlib
matplotlib.use("svg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, ScalarFormatter
import CoolProp.CoolProp as CP
import numpy as np
from functools import lru_cache

from domain.thermodynamics.reference_state import ReferenceStatePolicy, ReferenceStateService

_REFERENCE_STATE = ReferenceStateService()

def _effective_reference_state(
    fluid: str, ref_state: str
) -> ReferenceStatePolicy | str:
    """Resolve chart UI reference-state semantics to a shared policy code."""
    if ref_state == "Auto":
        return ReferenceStatePolicy.DEFAULT if fluid == "Water" else ReferenceStatePolicy.ASHRAE
    if ref_state in {"ASHRAE", "NBP", "IIR", "DEF"}:
        return ref_state
    raise ValueError(f"Unsupported chart reference-state policy: {ref_state}")


# ======================================================
# 中文字型設定（避免方框警告）
# ======================================================
def setup_chinese_font():
    try:
        matplotlib.rcParams["font.sans-serif"] = [
            "Microsoft JhengHei", "PingFang TC", "Noto Sans CJK TC",
            "Arial Unicode MS", "DejaVu Sans"
        ]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False

setup_chinese_font()

# ======================================================
# (新增) 冷媒驗證函式
# ======================================================
def check_coolprop_fluid(fluid_name):
    """
    檢查 CoolProp 中是否存在指定的流體名稱。
    """
    if not fluid_name:
        return False, "名稱不可為空"
    try:
        # 嘗試獲取一個基本屬性。
        with _REFERENCE_STATE.calculation_scope(fluid_name):
            CP.PropsSI('Tcrit', fluid_name)
        return True, "驗證成功"
    except ValueError as e:
        # CoolProp 通常會引發 ValueError (例如 "Unable to load fluid [...]")
        return False, "找不到此流體"
    except Exception as e:
        # 捕捉其他潛在錯誤
        return False, f"未知錯誤: {e}"

# ======================================================
# 快取 CoolProp 計算 (接受 ref_state)
# ======================================================
@lru_cache(maxsize=10000)
def safe_props(output, in1, in1_val, in2, in2_val, fluid, ref_state="Auto"):
    """Query CoolProp under the process-wide reference-state transaction."""
    try:
        with _REFERENCE_STATE.calculation_scope(
            fluid, _effective_reference_state(fluid, ref_state)
        ):
            if (in1 == "V" and in1_val == 0) or (in2 == "V" and in2_val == 0):
                return np.nan
            if (in1 == "D" and in1_val == 0) or (in2 == "D" and in2_val == 0):
                return np.nan
            return CP.PropsSI(output, in1, in1_val, in2, in2_val, fluid)
    except Exception:
        return np.nan

# ======================================================
# 通用飽和線生成函式 (接受 ref_state)
# ======================================================
def get_saturation_curve(fluid, ref_state, mode="T", num_points=400):
    """Generate a saturation curve under the shared CoolProp lock."""
    with _REFERENCE_STATE.calculation_scope(
        fluid, _effective_reference_state(fluid, ref_state)
    ):
        return _get_saturation_curve_unlocked(fluid, ref_state, mode, num_points)

def _get_saturation_curve_unlocked(fluid, ref_state, mode="T", num_points=400):
    """
    生成指定流體的飽和線（液線與氣線）。
    """
    try:
        T_crit = CP.PropsSI("Tcrit", fluid)
        T_trip = CP.PropsSI("Ttriple", fluid)
        P_crit = CP.PropsSI("pcrit", fluid)
        P_trip = CP.PropsSI("ptriple", fluid)
    except Exception as e:
        print(f"無法取得臨界/三相資料: {e}")
        return None

    if mode == "T":
        try:
            Ts = np.linspace(T_trip * 1.01, T_crit * 0.999, num_points)
        except ValueError: 
             Ts = np.linspace(T_crit * 0.999, T_trip * 1.01, num_points)
        P_liq = []
        P_vap = []
        for T in Ts:
            try:
                P_liq.append(CP.PropsSI("P", "T", T, "Q", 0, fluid))
                P_vap.append(CP.PropsSI("P", "T", T, "Q", 1, fluid))
            except Exception:
                P_liq.append(np.nan)
                P_vap.append(np.nan)
        Ts = np.append(Ts, T_crit)
        P_liq.append(P_crit)
        P_vap.append(P_crit)
        mask = ~np.isnan(P_liq) & ~np.isnan(P_vap)
        return Ts[mask], np.array(P_liq)[mask], Ts[mask], np.array(P_vap)[mask]
    elif mode == "P":
        try:
            Ps = np.logspace(np.log10(P_trip * 1.05), np.log10(P_crit * 0.999), num_points)
        except ValueError: 
             Ps = np.logspace(np.log10(P_crit * 0.999), np.log10(P_trip * 1.05), num_points)
        T_liq = []
        T_vap = []
        for P in Ps:
            try:
                T_liq.append(CP.PropsSI("T", "P", P, "Q", 0, fluid))
                T_vap.append(CP.PropsSI("T", "P", P, "Q", 1, fluid))
            except Exception:
                T_liq.append(np.nan)
                T_vap.append(np.nan)
        Ps = np.append(Ps, P_crit)
        T_liq.append(T_crit)
        T_vap.append(T_crit)
        mask = ~np.isnan(T_liq) & ~np.isnan(T_vap)
        return Ps[mask], np.array(T_liq)[mask], Ps[mask], np.array(T_vap)[mask]
    else:
        raise ValueError("mode 只能是 'T' 或 'P'")




# ======================================================
# 主繪圖函式：供 ThermoDiagramModule 調用 (修改：接受 target_P_unit)
# ======================================================
def generate_thermo_diagram(fluid, diagram, state_points_si, unit_converter,
                          connect_points=False, input_mode=None, ref_state="Auto",
                          target_P_unit="MPa", # 接受Y軸壓力單位
                          result_text=None):
    """Build a diagram while holding the shared CoolProp transaction lock."""
    with _REFERENCE_STATE.calculation_scope(
        fluid, _effective_reference_state(fluid, ref_state)
    ):
        return _generate_thermo_diagram_unlocked(
            fluid, diagram, state_points_si, unit_converter, connect_points,
            input_mode, ref_state, target_P_unit, result_text
        )

def _generate_thermo_diagram_unlocked(fluid, diagram, state_points_si, unit_converter,
                          connect_points=False, input_mode=None, ref_state="Auto",
                          target_P_unit="MPa", result_text=None):
    """
    建立熱力圖（P-h、T-s、P-v、T-v）
    """
    plt.close('all')

    # CoolProp reference-state setup is owned by the public wrapper.
    try:
        CP.PropsSI("Tcrit", fluid)
    except Exception:
        fig, ax = plt.subplots(figsize=(8, 6))
        # (修改) 更新錯誤訊息
        ax.text(0.5, 0.5, f"CoolProp 無法初始化流體 '{fluid}'\n(或參考狀態 '{ref_state}' 不適用)", 
                ha='center', va='center', color='red', wrap=True)
        return fig

    # 臨界與三相資料
    try:
        Pcrit = CP.PropsSI("pcrit", fluid)
        Tcrit = CP.PropsSI("Tcrit", fluid)
        Ptriple = CP.PropsSI("ptriple", fluid)
        Ttriple = CP.PropsSI("Ttriple", fluid)
    except Exception:
        Pcrit, Tcrit, Ptriple, Ttriple = np.nan, np.nan, 1000, 100

    # 定義通用格式 (小數優先)
    log_fmt = FuncFormatter(lambda x, pos: f"{x:g}")

    fig, ax = plt.subplots(figsize=(8, 6))
    x_label = "" 
    y_label = "" 

    # ------------------------------------------------------
    # 使用 get_saturation_curve() 取得飽和液線與氣線
    # ------------------------------------------------------
    try:
        if diagram in ["P-h", "P-v"]:
            Ps_liq, Ts_liq, Ps_vap, Ts_vap = get_saturation_curve(fluid, ref_state, mode="P")
        else:
            Ts_liq, Ps_liq, Ts_vap, Ps_vap = get_saturation_curve(fluid, ref_state, mode="T")

        if Ps_liq is None or len(Ps_liq) == 0:
            raise ValueError("無法取得飽和線資料")

        target_T_unit = unit_converter.default_units["T"]
        
        # ------------------------------------------------------
        # 根據圖型轉換 X, Y 座標
        # ------------------------------------------------------
        if diagram == "P-h":
            x_liq = [safe_props("H", "P", p, "Q", 0, fluid, ref_state) / 1000 for p in Ps_liq]
            x_vap = [safe_props("H", "P", p, "Q", 1, fluid, ref_state) / 1000 for p in Ps_vap]
            y_liq = [unit_converter.convert_from_si("P", p, target_P_unit) for p in Ps_liq]
            y_vap = [unit_converter.convert_from_si("P", p, target_P_unit) for p in Ps_vap]
            x_label = f"焓 ({unit_converter.default_units['H']})"
            y_label = f"壓力 ({target_P_unit})" 
            ax.set_yscale("log")
            ax.yaxis.set_major_formatter(log_fmt) 

        elif diagram == "T-s":
            x_liq = [safe_props("S", "T", T, "Q", 0, fluid, ref_state) / 1000 for T in Ts_liq]
            x_vap = [safe_props("S", "T", T, "Q", 1, fluid, ref_state) / 1000 for T in Ts_vap]
            y_liq = [unit_converter.convert_from_si("T", T, target_T_unit) for T in Ts_liq]
            y_vap = [unit_converter.convert_from_si("T", T, target_T_unit) for T in Ts_vap]
            x_label = f"熵 ({unit_converter.default_units['S']})"
            y_label = f"溫度 ({target_T_unit})"

        elif diagram == "P-v":
            x_liq = [1 / safe_props("D", "P", p, "Q", 0, fluid, ref_state) for p in Ps_liq]
            x_vap = [1 / safe_props("D", "P", p, "Q", 1, fluid, ref_state) for p in Ps_vap]
            y_liq = [unit_converter.convert_from_si("P", p, target_P_unit) for p in Ps_liq]
            y_vap = [unit_converter.convert_from_si("P", p, target_P_unit) for p in Ps_vap]
            x_label = f"比容 ({unit_converter.default_units['V']})"
            y_label = f"壓力 ({target_P_unit})" 
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.xaxis.set_major_formatter(log_fmt) 
            ax.yaxis.set_major_formatter(log_fmt)

        elif diagram == "T-v":
            x_liq = [1 / safe_props("D", "T", T, "Q", 0, fluid, ref_state) for T in Ts_liq]
            x_vap = [1 / safe_props("D", "T", T, "Q", 1, fluid, ref_state) for T in Ts_vap]
            y_liq = [unit_converter.convert_from_si("T", T, target_T_unit) for T in Ts_liq]
            y_vap = [unit_converter.convert_from_si("T", T, target_T_unit) for T in Ts_vap]
            x_label = f"比容 ({unit_converter.default_units['V']})"
            y_label = f"溫度 ({target_T_unit})"
            ax.set_xscale("log")
            ax.xaxis.set_major_formatter(log_fmt)

        else:
            ax.text(0.5, 0.5, "未知圖型", ha='center', va='center', color='red')
            return fig

        # ------------------------------------------------------
        # 畫飽和線（液線 + 氣線）
        # ------------------------------------------------------
        ax.plot(x_liq, y_liq, "b-", label="飽和液體", linewidth=2)
        ax.plot(x_vap, y_vap, "r-", label="飽和氣體", linewidth=2)

        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)

    except Exception as e:
        ax.text(0.5, 0.5, f"繪圖失敗: {e}", ha='center', va='center', color='red')
        return fig


    # ---- 狀態點 (使用 annotate 標註) ----
    try:
        target_T_unit = unit_converter.default_units["T"]
        
        plotted_points = False 
        plot_x_coords = [] 
        plot_y_coords = [] 
        all_T_K = []       

        # 遍歷所有傳入的狀態點
        for i, point in enumerate(state_points_si):
            T_K, P_Pa, h_J_kg, s_J_kgK, v_m3_kg = [np.nan] * 5 
            
            input_type = point.get("input_type", "T-P") 
            point_label = point.get("label", f"點 {i+1}") 

            # --------------------------------------------------
            # 根據 input_type，反查出 T, P, h, s, v
            # --------------------------------------------------
            try:
                if input_type == "T-P":
                    T_K = point["T_K"]
                    P_Pa = point["P_Pa"]
                    h_J_kg = safe_props("H", "T", T_K, "P", P_Pa, fluid, ref_state)
                    s_J_kgK = safe_props("S", "T", T_K, "P", P_Pa, fluid, ref_state)
                    v_m3_kg = 1 / safe_props("D", "T", T_K, "P", P_Pa, fluid, ref_state)
                
                elif input_type == "P-h":
                    P_Pa = point["P_Pa"]
                    h_J_kg = point["H_J_kg"]
                    T_K = safe_props("T", "P", P_Pa, "H", h_J_kg, fluid, ref_state)
                    s_J_kgK = safe_props("S", "P", P_Pa, "H", h_J_kg, fluid, ref_state)
                    v_m3_kg = 1 / safe_props("D", "P", P_Pa, "H", h_J_kg, fluid, ref_state)

                elif input_type == "T-s":
                    T_K = point["T_K"]
                    s_J_kgK = point["S_J_kgK"]
                    P_Pa = safe_props("P", "T", T_K, "S", s_J_kgK, fluid, ref_state)
                    h_J_kg = safe_props("H", "T", T_K, "S", s_J_kgK, fluid, ref_state)
                    v_m3_kg = 1 / safe_props("D", "T", T_K, "S", s_J_kgK, fluid, ref_state)

                elif input_type == "P-s":
                    P_Pa = point["P_Pa"]
                    s_J_kgK = point["S_J_kgK"]
                    T_K = safe_props("T", "P", P_Pa, "S", s_J_kgK, fluid, ref_state)
                    h_J_kg = safe_props("H", "P", P_Pa, "S", s_J_kgK, fluid, ref_state)
                    v_m3_kg = 1 / safe_props("D", "P", P_Pa, "S", s_J_kgK, fluid, ref_state)

                elif input_type == "P-v": 
                    P_Pa = point["P_Pa"]
                    v_m3_kg = point["V_m3_kg"] 
                    if v_m3_kg <= 0:
                        raise ValueError("比容必須大於 0")
                    D_kg_m3 = 1.0 / v_m3_kg # 轉換為密度
                    
                    # (修改) CoolProp 使用 'D' (密度) 而不是 'V' (比容) 作為輸入
                    T_K = safe_props("T", "P", P_Pa, "D", D_kg_m3, fluid, ref_state)
                    h_J_kg = safe_props("H", "P", P_Pa, "D", D_kg_m3, fluid, ref_state)
                    s_J_kgK = safe_props("S", "P", P_Pa, "D", D_kg_m3, fluid, ref_state)
                
                all_props = [T_K, P_Pa, h_J_kg, s_J_kgK, v_m3_kg]
                if np.isnan(all_props).any():
                    raise ValueError("無法解析點 (可能超出範圍或輸入無效)")

                plotted_points = True
                all_T_K.append(T_K) 

                # 轉換為繪圖單位
                h_plot = h_J_kg / 1000.0
                s_plot = s_J_kgK / 1000.0
                T_disp = unit_converter.convert_from_si("T", T_K, target_T_unit)
                P_disp = unit_converter.convert_from_si("P", P_Pa, target_P_unit) 
                v_plot = v_m3_kg 

                plot_x, plot_y = np.nan, np.nan
                if diagram == "P-h":
                    plot_x, plot_y = h_plot, P_disp
                elif diagram == "T-s":
                    plot_x, plot_y = s_plot, T_disp
                elif diagram == "P-v":
                    plot_x, plot_y = v_plot, P_disp
                elif diagram == "T-v":
                    plot_x, plot_y = v_plot, T_disp
                
                ax.plot(plot_x, plot_y, "mo", markersize=8) 
                
                text_offset = point.get("xytext", (5, 5)) 
                ax.annotate(point_label,
                            xy=(plot_x, plot_y), 
                            xytext=text_offset, 
                            textcoords='offset points', 
                            color="magenta", 
                            fontsize=9)
                
                plot_x_coords.append(plot_x)
                plot_y_coords.append(plot_y)

            except Exception as point_ex:
                print(f"繪製點 {point_label} 失敗: {point_ex}")
                ax.text(0.5, 0.5 - i*0.05, f"狀態點 {point_label} 計算失敗\n(輸入組合 {input_type} 可能無效)", 
                        ha='center', va='center', color='purple', 
                        transform=ax.transAxes, fontsize=10)

        # --------------------------------------------------
        # 執行自訂連線 (包含圖例修正)
        # --------------------------------------------------
        if connect_points and len(plot_x_coords) > 1:
            
            if input_mode == "Compressor" and len(plot_x_coords) == 3:
                ax.plot([plot_x_coords[0], plot_x_coords[1]], 
                        [plot_y_coords[0], plot_y_coords[1]], 
                        "m-", label="理想壓縮 (s=s1)", linewidth=1.5) 
                
                ax.plot([plot_x_coords[0], plot_x_coords[2]], 
                        [plot_y_coords[0], plot_y_coords[2]], 
                        "m--", label="實際壓縮", linewidth=1.5) 
            
            
            
            else:
                ax.plot(plot_x_coords, plot_y_coords, "m--", label="過程連線", linewidth=1.5)

        if plotted_points:
            ax.plot([], [], "mo", markersize=8, label="狀態點") 

    except Exception as e:
        ax.text(0.5, 0.5, f"繪製狀態點時發生錯誤: {e}", 
                ha='center', va='center', color='orange',
                transform=ax.transAxes)

    # (自動調整 T 軸範圍)
    if all_T_K:
        Tcrit_K = Tcrit if not np.isnan(Tcrit) else 300 
        T_K_max_input = max(all_T_K)
        T_max_K = max(Tcrit_K * 1.05, T_K_max_input * 1.2)
        if diagram in ["T-s", "T-v"]:
            current_ymin, current_ymax = ax.get_ylim()
            display_T_max = unit_converter.convert_from_si("T", T_max_K, target_T_unit)
            ax.set_ylim(bottom=None, top=max(current_ymax, display_T_max * 1.05)) .count
        
        # ---- 修正版：T-s 圖手動繪製等壓線 ----
        if diagram == "T-s" and connect_points and input_mode == "Compressor":
            if len(state_points_si) == 3:
                try:
                    P1_Pa = state_points_si[0]["P_Pa"]
                    P2_Pa = state_points_si[2]["P_Pa"]
                    T1 = state_points_si[0]["T_K"]
                    T2 = state_points_si[2]["T_K"]
        
                    target_T_unit = unit_converter.default_units["T"]
        
                    # === 低壓線（P1） ===
                    T_range = np.linspace(T1 * 0.8, T1 * 1.2, 40)
                    S_P1 = [safe_props("S", "T", T, "P", P1_Pa, fluid, ref_state) / 1000 for T in T_range]
                    T_P1_disp = [unit_converter.convert_from_si("T", T, target_T_unit) for T in T_range]
                    ax.plot(S_P1, T_P1_disp, "k-", linewidth=0.8)
                    P1_disp = unit_converter.convert_from_si("P", P1_Pa, "kPa")
                    ax.text(S_P1[-1], T_P1_disp[-1], f"{P1_disp:.0f} kPa", fontsize=8, color="k")
        
                    # === 高壓線（P2） ===
                    T_range = np.linspace(T2 * 0.8, T2 * 1.2, 40)
                    S_P2 = [safe_props("S", "T", T, "P", P2_Pa, fluid, ref_state) / 1000 for T in T_range]
                    T_P2_disp = [unit_converter.convert_from_si("T", T, target_T_unit) for T in T_range]
                    ax.plot(S_P2, T_P2_disp, "k-", linewidth=0.8)
                    P2_disp = unit_converter.convert_from_si("P", P2_Pa, "kPa")
                    ax.text(S_P2[-1], T_P2_disp[-1], f"{P2_disp:.0f} kPa", fontsize=8, color="k")
        
                except Exception as e:
                    print(f"繪製等壓線失敗: {e}")

    ax.set_title(f"{diagram} 圖 ({fluid})", fontsize=14, fontweight="bold")
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    
    ax.legend(fontsize=9) 
    ax.grid(True, which='major', linestyle='--', alpha=0.6)
    fig.tight_layout()
    return fig