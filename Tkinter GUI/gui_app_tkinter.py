# gui_app.py
# 結合了 gui_app.py 的完整功能與 thermo_calculator.py 的強大計算核心，並採用清晰的多類別架構。
import tkinter as tk
from tkinter import ttk, messagebox
# 確保您的 thermo_calculator.py 與此檔案在同一目錄下
from thermo_calculator import ThermoCalculator 

# ==============================================================================
# TAB 1: 熱力性質查詢分頁
# ==============================================================================
class PropertyTab(ttk.Frame):
    def __init__(self, parent, calculator: ThermoCalculator):
        super().__init__(parent, padding="10")
        self.calculator = calculator

        # --- 從 calculator 獲取設定，而不是在 GUI 中寫死 ---
        self.prop_names_map = {code: f"{name}" for code, name in self.calculator.prop_names.items()}
        
        # --- 介面佈局 ---
        self.create_widgets()
        self.on_mode_change() # 初始化介面狀態

    def create_widgets(self):
        # 模式選擇
        frame_mode = ttk.Frame(self)
        frame_mode.pack(fill="x", pady=(0, 10))
        ttk.Label(frame_mode, text="模式選擇:").pack(side="left")
        self.mode_var = tk.StringVar(value="CoolProp (冷媒)")
        mode_combo = ttk.Combobox(frame_mode, textvariable=self.mode_var, values=["CoolProp (冷媒)", "Water (水/水蒸氣)"], state="readonly")
        mode_combo.pack(side="left", fill="x", expand=True, padx=5)
        mode_combo.bind("<<ComboboxSelected>>", self.on_mode_change)
        
        # 物質名稱
        frame_fluid = ttk.Frame(self)
        frame_fluid.pack(fill="x", pady=5)
        ttk.Label(frame_fluid, text="物質名稱:").pack(side="left")
        self.fluid_entry = ttk.Entry(frame_fluid)
        self.fluid_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.ideal_gas_var = tk.BooleanVar()
        self.ideal_gas_check = ttk.Checkbutton(frame_fluid, text="理想氣體計算", variable=self.ideal_gas_var)
        
        # 輸入區
        input_frame = ttk.LabelFrame(self, text="輸入區", padding="10")
        input_frame.pack(fill="x", pady=5)
        self.prop_vars, self.value_entries, self.unit_vars, self.unit_menus = [], [], [], []
        for i in range(3):
            frame = ttk.Frame(input_frame)
            frame.pack(fill="x", pady=5)
            # 使用來自 calculator 的預設性質順序
            initial_prop_code = self.calculator.properties[i] if i < len(self.calculator.properties) else "T"
            prop_var = tk.StringVar(value=self.prop_names_map[initial_prop_code])
            self.prop_vars.append(prop_var)
            
            prop_menu = ttk.Combobox(frame, textvariable=prop_var, values=list(self.prop_names_map.values()), state="readonly", width=22)
            prop_menu.pack(side="left", padx=(0, 5))
            prop_menu.bind("<<ComboboxSelected>>", lambda e, pv=prop_var: self.update_units_menu_on_change(pv))
            
            value_entry = ttk.Entry(frame, width=15)
            value_entry.pack(side="left", fill="x", expand=True)
            self.value_entries.append(value_entry)
            
            unit_var = tk.StringVar()
            self.unit_vars.append(unit_var)
            unit_menu = ttk.Combobox(frame, textvariable=unit_var, state="readonly", width=12)
            unit_menu.pack(side="left", padx=(5, 0))
            self.unit_menus.append(unit_menu) 
            self.update_units_menu(prop_var, unit_var) 
            
        # 廣延性質
        mass_frame = ttk.LabelFrame(self, text="廣延性質計算", padding="10")
        mass_frame.pack(fill="x", pady=5)
        ttk.Label(mass_frame, text="總質量:").pack(side="left")
        self.mass_entry = ttk.Entry(mass_frame, width=15)
        self.mass_entry.pack(side="left", padx=5)
        self.mass_unit_var = tk.StringVar(value="kg")
        ttk.Combobox(mass_frame, textvariable=self.mass_unit_var, values=["kg", "lbm"], width=5, state="readonly").pack(side="left")
        
        # 按鈕與輸出
        ttk.Button(self, text="計算性質", command=self.perform_calculation).pack(pady=10)
        output_frame = ttk.LabelFrame(self, text="輸出結果", padding="10")
        output_frame.pack(fill="both", expand=True, pady=5)
        self.result_text = tk.Text(output_frame, height=15, width=60, state='disabled', font=("Courier New", 10))
        self.result_text.pack(fill="both", expand=True)

    def on_mode_change(self, event=None):
        if self.mode_var.get() == "Water (水/水蒸氣)":
            self.fluid_entry.config(state='normal')
            self.fluid_entry.delete(0, tk.END)
            self.fluid_entry.insert(0, "Water")
            self.fluid_entry.config(state='disabled')
            self.ideal_gas_check.pack(side="left", padx=10)
        else: 
            self.fluid_entry.config(state='normal')
            self.fluid_entry.delete(0, tk.END)
            self.fluid_entry.insert(0, "R32")
            self.ideal_gas_check.pack_forget()
            self.ideal_gas_var.set(False)

    def get_prop_code(self, formatted_name):
        # 從 "中文名 (英文名)" 的格式中找到對應的 Code
        for code, name in self.prop_names_map.items():
            if name == formatted_name:
                return code
        return None

    def update_units_menu(self, prop_var, unit_var):
        prop_code = self.get_prop_code(prop_var.get())
        menu = self.unit_menus[self.prop_vars.index(prop_var)]
        # 從 calculator 獲取單位選項
        units = self.calculator.conversion_map.get(prop_code, {}).get("to_si", {}).keys() if prop_code != "Q" else ["-"]
        menu['values'] = list(units)
        if list(units):
            # 從 calculator 獲取預設單位
            default = self.calculator.default_units.get(prop_code)
            unit_var.set(default if default in units else list(units)[0])

    def update_units_menu_on_change(self, prop_var):
        unit_var = self.unit_vars[self.prop_vars.index(prop_var)]
        self.update_units_menu(prop_var, unit_var)

    def perform_calculation(self):
        fluid = self.fluid_entry.get().strip()
        if not fluid:
            messagebox.showerror("錯誤", "請提供物質名稱。")
            return
        
        known_props, display_inputs, use_imperial = [], [], False
        for i in range(3):
            prop_name, value_str = self.prop_vars[i].get(), self.value_entries[i].get().strip()
            if value_str:
                try:
                    prop_code = self.get_prop_code(prop_name)
                    unit = self.unit_vars[i].get()
                    if unit in self.calculator.imperial_units.values(): use_imperial = True
                    known_props.append((prop_code, float(value_str), unit))
                    display_inputs.append(f"{prop_name}={value_str} {unit}")
                except (ValueError, TypeError): pass

        if len(known_props) < 2:
            messagebox.showerror("輸入錯誤", "請至少輸入兩組有效的性質。")
            return

        self.result_text.config(state='normal')
        self.result_text.delete('1.0', tk.END)
        is_ideal = self.ideal_gas_var.get() and self.mode_var.get().startswith("Water")
        calc_type = " (理想氣體模型)" if is_ideal else ""
        self.result_text.insert(tk.END, f"--- 輸入 ---\n物質: {fluid}{calc_type}\n已知: {', '.join(display_inputs[:2])}\n\n")
        
        try:
            # === 核心計算呼叫 ===
            si_results = self.calculator.calculate_properties(fluid, known_props[:2], is_ideal)
            self.result_text.insert(tk.END, self.calculator.format_specific_properties(si_results, use_imperial))
            
            if mass_str := self.mass_entry.get().strip():
                total_mass_kg = float(mass_str) * (0.453592 if self.mass_unit_var.get() == 'lbm' else 1)
                self.result_text.insert(tk.END, self.calculator.format_extensive_properties(si_results, total_mass_kg, use_imperial))
        except Exception as e:
            messagebox.showerror("計算錯誤", str(e))
        finally:
            self.result_text.config(state='disabled')

# ==============================================================================
# TAB 2: 冷凍空調原理分析分頁
# ==============================================================================

class AnalysisTab(ttk.Frame):
    def __init__(self, parent, calculator: ThermoCalculator):
        super().__init__(parent, padding="10")
        self.calculator = calculator
        self.create_widgets()

    def create_widgets(self):
        analysis_frame = ttk.Frame(self)
        analysis_frame.pack(fill='x', pady=5)
        ttk.Label(analysis_frame, text="分析項目:").pack(side='left')
        self.analysis_var = tk.StringVar(value="壓縮比 (CR)")
        analysis_combo = ttk.Combobox(analysis_frame, textvariable=self.analysis_var, values=["壓縮機功 (Win)", "壓縮比 (CR)"], state='readonly')
        analysis_combo.pack(side='left', fill='x', expand=True, padx=5)
        analysis_combo.bind("<<ComboboxSelected>>", self.on_analysis_change)

        self.win_frame = ttk.LabelFrame(self, text="壓縮機功 (Win) 輸入", padding="10")
        self.cr_frame = ttk.LabelFrame(self, text="壓縮比 (CR) 輸入", padding="10")

        self.create_win_widgets()
        self.create_cr_widgets()

        ttk.Button(self, text="執行分析", command=self.perform_analysis).pack(pady=20)
        result_frame = ttk.LabelFrame(self, text="分析結果", padding="10")
        result_frame.pack(fill='both', expand=True)
        self.analysis_result_var = tk.StringVar()
        ttk.Label(result_frame, textvariable=self.analysis_result_var, font=("Helvetica", 14, "bold")).pack(pady=20)
        
        self.on_analysis_change()

    def create_win_widgets(self):
        # (此部分無需修改)
        self.win_entries = {}
        params = {"mass_flow": "質量流率 (ṁ)", "h1": "入口焓 (h1)", "h2": "出口焓 (h2)"}
        units = {"mass_flow": "kg/s", "h1": "kJ/kg", "h2": "kJ/kg"}
        for key, label in params.items():
            frame = ttk.Frame(self.win_frame)
            frame.pack(fill='x', pady=5)
            ttk.Label(frame, text=f"{label}:", width=18).pack(side='left')
            entry = ttk.Entry(frame, width=15)
            entry.pack(side='left', fill='x', expand=True)
            ttk.Label(frame, text=units[key]).pack(side='left', padx=5)
            self.win_entries[key] = entry

    def create_cr_widgets(self):
        self.cr_entries = {}
        pressure_units = list(self.calculator.conversion_map["P"]["to_si"].keys())
        types = ["絕對壓力", "錶壓力"]

        p_in_frame = ttk.Frame(self.cr_frame); p_in_frame.pack(fill='x', pady=5)
        p_out_frame = ttk.Frame(self.cr_frame); p_out_frame.pack(fill='x', pady=5)
        self.atm_frame = ttk.Frame(self.cr_frame)

        # 建立一個所有壓力單位共享的變數
        self.cr_pressure_unit_var = tk.StringVar(value="kPa")
        
        # *** 核心修改：新增一個變數來追蹤上一次的單位 ***
        self._last_cr_unit = self.cr_pressure_unit_var.get()
        # *** 核心修改：綁定追蹤事件，當單位改變時觸發 on_cr_unit_change 函式 ***
        self.cr_pressure_unit_var.trace_add("write", self.on_cr_unit_change)

        def create_pressure_input(parent, label_text, shared_unit_var):
            ttk.Label(parent, text=f"{label_text}:", width=18).pack(side='left')
            entry = ttk.Entry(parent, width=10); entry.pack(side='left', fill='x', expand=True)
            type_var = tk.StringVar(value=types[0]); 
            ttk.Combobox(parent, textvariable=type_var, values=types, width=8, state='readonly').pack(side='left', padx=5)
            ttk.Combobox(parent, textvariable=shared_unit_var, values=pressure_units, width=8, state='readonly').pack(side='left', padx=5)
            return entry, type_var, shared_unit_var

        self.cr_entries["p_in"] = create_pressure_input(p_in_frame, "入口壓力 (P_in)", self.cr_pressure_unit_var)
        self.cr_entries["p_out"] = create_pressure_input(p_out_frame, "出口壓力 (P_out)", self.cr_pressure_unit_var)
        
        ttk.Label(self.atm_frame, text="大氣壓力 (P_atm):", width=18).pack(side='left')
        atm_e = ttk.Entry(self.atm_frame, width=10); atm_e.pack(side='left', fill='x', expand=True)
        atm_e.insert(0, "101.325")
        ttk.Combobox(self.atm_frame, textvariable=self.cr_pressure_unit_var, values=pressure_units, width=8, state='readonly').pack(side='left', padx=5)
        self.cr_entries["p_atm"] = (atm_e, self.cr_pressure_unit_var)
        
        self.cr_entries["p_in"][1].trace_add("write", self.sync_atm_pressure)
        self.cr_entries["p_out"][1].trace_add("write", self.sync_atm_pressure)

    def on_cr_unit_change(self, *args):
        """*** 核心修改：當單位改變時，自動換算數值 ***"""
        new_unit = self.cr_pressure_unit_var.get()
        old_unit = self._last_cr_unit

        # 如果單位沒有真的改變，或者舊單位不存在，就直接返回
        if new_unit == old_unit or not old_unit:
            return

        # 需要被換算的輸入框列表
        entries_to_convert = [
            self.cr_entries["p_in"][0],
            self.cr_entries["p_out"][0],
            self.cr_entries["p_atm"][0]
        ]

        for entry in entries_to_convert:
            val_str = entry.get()
            if val_str:
                try:
                    val_float = float(val_str)
                    # 步驟1: 將舊單位的數值轉成 SI 單位 (Pa)
                    val_si = self.calculator._convert_to_si("P", val_float, old_unit)
                    # 步驟2: 將 SI 單位的值轉成新單位的數值
                    new_val = self.calculator._convert_from_si("P", val_si, new_unit)
                    
                    # 更新輸入框的內容
                    entry.delete(0, tk.END)
                    entry.insert(0, f"{new_val:.6g}") # 使用 .6g 來自動選擇最佳顯示格式
                except (ValueError, TypeError):
                    # 如果輸入框內容不是數字，就忽略
                    pass
        
        # 更新「上一次的單位」記錄，為下一次變換做準備
        self._last_cr_unit = new_unit

    def on_analysis_change(self, event=None):
        # (此部分無需修改)
        is_win = self.analysis_var.get() == "壓縮機功 (Win)"
        if is_win:
            self.win_frame.pack(fill='x', pady=10)
            self.cr_frame.pack_forget()
        else:
            self.cr_frame.pack(fill='x', pady=10)
            self.win_frame.pack_forget()
            self.sync_atm_pressure()

    def sync_atm_pressure(self, *args):
        # (此部分無需修改)
        p_in_type, p_out_type = self.cr_entries["p_in"][1].get(), self.cr_entries["p_out"][1].get()
        if p_in_type == "錶壓力" or p_out_type == "錶壓力":
            self.atm_frame.pack(fill='x', pady=(10, 5))
        else:
            self.atm_frame.pack_forget()

    def perform_analysis(self):
        # (此部分無需修改)
        self.analysis_result_var.set("")
        try:
            if self.analysis_var.get() == "壓縮機功 (Win)":
                m_dot = float(self.win_entries["mass_flow"].get())
                h1, h2 = float(self.win_entries["h1"].get()), float(self.win_entries["h2"].get())
                result = self.calculator.calculate_compressor_work(m_dot, h1, h2)
                self.analysis_result_var.set(f"Win = {result:.4f} kW")
            else: 
                p_in_val, p_in_type, p_in_unit = (v.get() for v in self.cr_entries["p_in"])
                p_out_val, p_out_type, p_out_unit = (v.get() for v in self.cr_entries["p_out"])
                
                p_in_si = self.calculator._convert_to_si('P', float(p_in_val), p_in_unit)
                p_out_si = self.calculator._convert_to_si('P', float(p_out_val), p_out_unit)
                
                p_in_abs, p_out_abs = p_in_si, p_out_si
                if p_in_type == "錶壓力" or p_out_type == "錶壓力":
                    p_atm_val, p_atm_unit = (v.get() for v in self.cr_entries["p_atm"])
                    p_atm_si = self.calculator._convert_to_si('P', float(p_atm_val), p_atm_unit)
                    if p_in_type == "錶壓力": p_in_abs += p_atm_si
                    if p_out_type == "錶壓力": p_out_abs += p_atm_si
                
                result = self.calculator.calculate_compression_ratio(p_in_abs, p_out_abs)
                self.analysis_result_var.set(f"CR = {result:.4f}")
        except ValueError:
            messagebox.showerror("輸入錯誤", "請確保所有輸入欄位均為有效的數字。")
        except Exception as e:
            messagebox.showerror("計算錯誤", str(e))
# ==============================================================================
# MAIN APP: 主應用程式視窗
# ==============================================================================
class MainApplication:
    def __init__(self, master):
        self.master = master
        master.title("熱力學性質與分析工具 (最終版)")
        master.geometry("620x800")
        
        # 建立一個共享的計算引擎實例
        self.calculator = ThermoCalculator()
        
        notebook = ttk.Notebook(master)
        notebook.pack(expand=True, fill='both', padx=10, pady=10)

        # 將 calculator 實例傳遞給每個分頁
        prop_tab = PropertyTab(notebook, self.calculator)
        notebook.add(prop_tab, text='熱力學性質查詢')

        analysis_tab = AnalysisTab(notebook, self.calculator)
        notebook.add(analysis_tab, text='冷凍空調原理分析')

def start_gui():
    """啟動 GUI 應用程式的進入點函式。"""
    root = tk.Tk()
    app = MainApplication(root)
    root.mainloop()