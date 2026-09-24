# UnitConverter.py
from domain.units.converter import CanonicalUnitConverter
# 職責：只處理單位轉換。不認識 CoolProp，也不執行任何熱力學計算。

class UnitConverter:
    def __init__(self):
        """
        初始化單位轉換器。
        SI 基礎單位為:
        - 壓力 (P): Pa (帕)
        - 溫度 (T): K (凱氏)
        - 焓/內能 (H, U): J/kg (焦耳/公斤)
        - 熵 (S): J/(kg.K) (焦耳/公斤·凱氏)
        - 密度 (D): kg/m³ (公斤/立方米)
        - 比容 (V): m³/kg (立方米/公斤)
        - 長度/高度 (L): m (米)
        - 質量 (Mass): kg (公斤)
        - 質量流率 (MassFlow): kg/s (公斤/秒)
        - 功率 (Power): W (瓦特, 即 J/s)
        - 能量 (E): J (焦耳)  <--- 新增
        - 乾度 (Q): - (無單位)
        - 相對濕度 (RH): % (百分比)
        """
        
        # --- 單位定義 (使用者介面預設顯示) ---
        self.default_units = {
            "P": "kPa", "T": "°C", "H": "kJ/kg", "S": "kJ/(kg.K)",
            "D": "kg/m³", "Q": "-", "V": "m³/kg", "U": "kJ/kg",
            "L": "m", "Mass": "kg", "MassFlow": "kg/s", "Power": "kW",
            "E": "kJ", "RH": "%", "W": "g/kg",# --- ↓↓↓ 請添加以下 ↓↓↓ ---
            "Area": "m²",
            "Velocity": "m/s",
            "VolumeFlow": "m³/s",
            "EntropyFlow": "kW/K",
            "Eff": "%",
            "DeltaT": "K",
            
        }
        self.imperial_units = {
            "P": "psia", "T": "°F", "H": "Btu/lbm", "S": "Btu/(lbm.R)",
            "D": "lbm/ft³", "Q": "-", "V": "ft³/lbm", "U": "Btu/lbm",
            "L": "ft", "Mass": "lbm", "MassFlow": "lbm/s", "Power": "Btu/h",
            "E": "Btu", "RH": "%", "W": "gr/lbm",
            # --- ↓↓↓ 請添加以下 ↓↓↓ ---
            "Area": "m²",
            "Velocity": "m/s",
            "VolumeFlow": "m³/s",
            "EntropyFlow": "kW/K",
            "Eff": "%",
            "DeltaT": "°F",
        }
        
        # 定義從 SI 基礎單位 (Pa, K, J/kg...) 的轉換
        # 格式: { 系統名稱: { 屬性代碼: (轉換函數/因子, 單位標籤) } }
        self._from_si_conversions = {
            "SI": {
                "P": (lambda pa: pa * 1e-6, "MPa"),                 # Pa -> MPa
                "T": (lambda k: k - 273.15, "°C"),                  # K -> °C
                "H": (lambda j_kg: j_kg * 1e-3, "kJ/kg"),            # J/kg -> kJ/kg
                "U": (lambda j_kg: j_kg * 1e-3, "kJ/kg"),            # J/kg -> kJ/kg
                "S": (lambda j_kgK: j_kgK * 1e-3, "kJ/(kg.K)"),      # J/(kg.K) -> kJ/(kg.K)
                "D": (lambda v: v, "kg/m³"),                        # kg/m³ -> kg/m³
                "V": (lambda v: v, "m³/kg"),                        # m³/kg -> m³/kg
                "L": (lambda m: m, "m"),                            # m -> m
                "Mass": (lambda kg: kg, "kg"),                      # kg -> kg
                "MassFlow": (lambda kg_s: kg_s, "kg/s"),            # kg/s -> kg/s
                "Power": (lambda w: w * 1e-3, "kW"),                # W -> kW
                "E": (lambda j: j * 1e-3, "kJ"),                    # J -> kJ   <--- 新增
                # --- ↓↓↓ 請添加以下 ↓↓↓ ---
                "Area": (lambda v: v, "m²"),
                "Velocity": (lambda v: v, "m/s"),
                "VolumeFlow": (lambda v: v, "m³/s"),
                "EntropyFlow": (lambda w_k: w_k * 1e-3, "kW/K"), # W/K -> kW/K
            },
            "Imperial": {
                "P": (lambda pa: pa * 0.0001450377, "psia"),         # Pa -> psia
                "T": (lambda k: (k - 273.15) * 9/5 + 32, "°F"),      # K -> °F
                "H": (lambda j_kg: j_kg * 0.00043020, "Btu/lbm"),    # J/kg -> Btu/lbm
                "U": (lambda j_kg: j_kg * 0.00043020, "Btu/lbm"),    # J/kg -> Btu/lbm
                "S": (lambda j_kgK: j_kgK * 0.0002389, "Btu/(lbm.R)"), # J/(kg.K) -> Btu/(lbm.R)
                "D": (lambda kg_m3: kg_m3 * 0.062428, "lbm/ft³"),     # kg/m³ -> lbm/ft³
                "V": (lambda m3_kg: m3_kg * 16.0185, "ft³/lbm"),     # m³/kg -> ft³/lbm
                "L": (lambda m: m * 3.28084, "ft"),                  # m -> ft
                "Mass": (lambda kg: kg * 2.20462, "lbm"),            # kg -> lbm
                "MassFlow": (lambda kg_s: kg_s * 2.20462, "lbm/s"),  # kg/s -> lbm/s
                "Power": (lambda w: w * 3.41214, "Btu/h"),           # W -> Btu/h
                "E": (lambda j: j * 0.000947817, "Btu"),             # J -> Btu  <--- 新增
                # --- ↓↓↓ 請修改以下 ↓↓↓ ---
                "Area": (lambda m2: m2 * 10.7639, "ft²"), # 1 / 0.092903
                "Velocity": (lambda m_s: m_s * 3.28084, "ft/s"), # 1 / 0.3048
                "VolumeFlow": (lambda m3_s: m3_s * 2118.88, "ft³/min"), # 1 / 0.000471947
                "EntropyFlow": (lambda w_k: w_k * 1.89551, "Btu/(h.R)"), # 1 / 0.527528
            }
        }

        # --- 新增：定義單位的首選顯示順序 ---
        # 這裡的順序將決定下拉選單中的順序
        self.unit_order = {
            "P": ["Pa","kPa","MPa", "bar", "psia"],
            "T": ["K", "°C", "°F"],
            "H": ["J/kg", "kJ/kg", "Btu/lbm"],
            "U": ["J/kg", "kJ/kg", "Btu/lbm"],
            "S": ["J/(kg.K)", "kJ/(kg.K)", "Btu/(lbm.R)"],
            "D": ["kg/m³", "lbm/ft³"],
            "V": ["m³/kg", "ft³/lbm"],
            "L": ["m", "ft"],
            "Mass": ["kg", "lbm"],
            "MassFlow": ["kg/s", "lbm/s"],
            "Power": ["W", "kW", "Btu/h", "RT", "kcal/h"],
            "DeltaT": ["K", "°C", "°F"],
            "E": ["J", "kJ", "Btu"],
            "W": ["kg/kg", "g/kg", "lbm/lbm", "gr/lbm"],
            "RH": ["%"],
            "Q": ["-"],
            # --- ↓↓↓ 請添加以下 ↓↓↓ ---
            "Area": ["m²", "cm²", "mm²", "ft²", "in²"],
            "Velocity": ["m/s", "ft/min", "ft/s"],
            "VolumeFlow": ["m³/s","m³/min","m³/h", "L/s", "ft³/min"], # ft³/min (CFM)
            "EntropyFlow": ["W/K", "kW/K", "Btu/(h.R)"], # Btu/(h.R) (CFM)
        }
        
        # 建立完整的轉換映射表
        self.conversion_map = self._build_conversion_map()
        self._canonical_converter = CanonicalUnitConverter()

    def _build_conversion_map(self):
        """
        (內部輔助函式)
        建立一個易於查詢的轉換映射表 (conversion_map)，
        包含 "to_si" 和 "from_si" 的所有轉換 lambda 函數。
        """
        cmap = {}
        
        # SI 基礎單位 (無轉換)
        base_si_units = {
            "P": "Pa", "T": "K", "H": "J/kg", "S": "J/(kg.K)", "D": "kg/m³",
            "V": "m³/kg", "U": "J/kg", "L": "m", "Mass": "kg", "MassFlow": "kg/s",
            "Power": "W", "E": "J", "RH": "%", "Q": "-", "W": "kg/kg",# --- ↓↓↓ 請添加以下 ↓↓↓ ---
            "Area": "m²",
            "Velocity": "m/s",
            "VolumeFlow": "m³/s",
            "EntropyFlow": "W/K",
            "Eff": "%",
            "DeltaT": "K",
        }

        # 收集所有屬性代碼
        all_props = set(self.default_units.keys()) | set(self.imperial_units.keys())

        for prop_code in all_props:
            if prop_code not in cmap:
                cmap[prop_code] = {"to_si": {}, "from_si": {}}

            # 1. 處理 SI 基礎單位 (例如 Pa, K, J/kg)
            base_unit = base_si_units.get(prop_code)
            if base_unit:
                cmap[prop_code]["to_si"][base_unit] = lambda x: x
                cmap[prop_code]["from_si"][base_unit] = lambda x: x
                
            # 2. 處理 _from_si_conversions 中定義的單位 (SI 和 Imperial 顯示單位)
            for system_map in self._from_si_conversions.values():
                if prop_code in system_map:
                    convert_func, unit_label = system_map[prop_code]
                    
                    # from_si: SI 基礎單位 -> 顯示單位
                    cmap[prop_code]["from_si"][unit_label] = convert_func
                    
                    # to_si: 顯示單位 -> SI 基礎單位 (反向操作)
                    # 透過 "測試轉換" 1.0 單位來找到反轉換因子
                    factor = convert_func(1.0) - convert_func(0.0)
                    if abs(factor) > 1e-12:
                         # 處理 K -> °C, K -> °F 的特殊偏移
                        if prop_code == 'T' and unit_label == '°C':
                            cmap[prop_code]["to_si"][unit_label] = lambda c: c + 273.15
                        elif prop_code == 'T' and unit_label == '°F':
                            cmap[prop_code]["to_si"][unit_label] = lambda f: (f - 32) * 5/9 + 273.15
                        else:
                            # 處理 Pa -> MPa, J/kg -> kJ/kg 等
                            inv_factor = 1.0 / factor
                            cmap[prop_code]["to_si"][unit_label] = (lambda v, inv=inv_factor: v * inv)
                    else:
                        # 處理 m -> m, kg -> kg 等
                        cmap[prop_code]["to_si"][unit_label] = lambda x: x
                        
        # --- 處理手動添加的單位 (不在 SI 或 Imperial 預設中的) ---
        
        # 壓力 (P), SI: Pa
        cmap["P"]["to_si"]["bar"] = lambda x: x * 1e5
        cmap["P"]["from_si"]["bar"] = lambda x: x * 1e-5
        cmap["P"]["to_si"]["kPa"] = lambda x: x * 1e3
        cmap["P"]["from_si"]["kPa"] = lambda x: x * 1e-3

        # 焓/內能 (H, U), SI: J/kg
        cmap["H"]["to_si"]["kJ/kg"] = lambda x: x * 1e3
        cmap["H"]["from_si"]["kJ/kg"] = lambda x: x * 1e-3
        cmap["U"]["to_si"]["kJ/kg"] = lambda x: x * 1e3
        cmap["U"]["from_si"]["kJ/kg"] = lambda x: x * 1e-3
        
        # 熵 (S), SI: J/(kg.K)
        cmap["S"]["to_si"]["kJ/(kg.K)"] = lambda x: x * 1e3
        cmap["S"]["from_si"]["kJ/(kg.K)"] = lambda x: x * 1e-3

        # 功率 (Power), SI: W
        cmap["Power"]["to_si"]["kW"] = lambda x: x * 1e3
        cmap["Power"]["from_si"]["kW"] = lambda x: x * 1e-3
        
        # 能量 (E), SI: J  <--- 新增
        cmap["E"]["to_si"]["kJ"] = lambda x: x * 1e3
        cmap["E"]["from_si"]["kJ"] = lambda x: x * 1e-3
        
        # 濕度比 (W), SI: kg/kg
        if "W" not in cmap: cmap["W"] = {"to_si": {}, "from_si": {}} # 確保 W 存在
        cmap["W"]["to_si"]["g/kg"] = lambda x: x / 1000.0
        cmap["W"]["from_si"]["g/kg"] = lambda x: x * 1000.0
        cmap["W"]["to_si"]["lbm/lbm"] = lambda x: x
        cmap["W"]["from_si"]["lbm/lbm"] = lambda x: x
        cmap["W"]["to_si"]["gr/lbm"] = lambda x: x / 7000.0
        cmap["W"]["from_si"]["gr/lbm"] = lambda x: x * 7000.0

        # 面積 (Area), SI: m²
        if "Area" not in cmap: cmap["Area"] = {"to_si": {}, "from_si": {}}
        cmap["Area"]["to_si"]["cm²"] = lambda x: x * 1e-4
        cmap["Area"]["from_si"]["cm²"] = lambda x: x * 1e4
        cmap["Area"]["to_si"]["mm²"] = lambda x: x * 1e-6
        cmap["Area"]["from_si"]["mm²"] = lambda x: x * 1e6
        cmap["Area"]["to_si"]["ft²"] = lambda x: x * 0.092903
        cmap["Area"]["from_si"]["ft²"] = lambda x: x / 0.092903
        cmap["Area"]["to_si"]["in²"] = lambda x: x * 0.00064516
        cmap["Area"]["from_si"]["in²"] = lambda x: x / 0.00064516
        
        # 速度 (Velocity), SI: m/s
        if "Velocity" not in cmap: cmap["Velocity"] = {"to_si": {}, "from_si": {}}
        cmap["Velocity"]["to_si"]["ft/s"] = lambda x: x * 0.3048
        cmap["Velocity"]["from_si"]["ft/s"] = lambda x: x / 0.3048
        cmap["Velocity"]["to_si"]["ft/min"] = lambda x: x * 0.00508 # (0.3048 / 60)
        cmap["Velocity"]["from_si"]["ft/min"] = lambda x: x / 0.00508

        # 體積流率 (VolumeFlow), SI: m³/s
        if "VolumeFlow" not in cmap: cmap["VolumeFlow"] = {"to_si": {}, "from_si": {}}
        # m³/h (正確)
        cmap["VolumeFlow"]["to_si"]["m³/h"] = lambda x: x / 3600.0
        cmap["VolumeFlow"]["from_si"]["m³/h"] = lambda x: x * 3600.0
        # m³/min (正確)
        cmap["VolumeFlow"]["to_si"]["m³/min"] = lambda x: x / 60.0
        cmap["VolumeFlow"]["from_si"]["m³/min"] = lambda x: x * 60.0
        # L/h (公升/小時)
        # 修正後的 to_si: L/h -> m³/s (除以 1000 再除以 3600，即除以 3,600,000)
        cmap["VolumeFlow"]["to_si"]["L/h"] = lambda x: x / 3600000.0 # 3600 * 1000
        # 修正後的 from_si: m³/s -> L/h (乘以 3600 再乘以 1000，即乘以 3,600,000)
        cmap["VolumeFlow"]["from_si"]["L/h"] = lambda x: x * 3600000.0
        # L/s (公升/秒) (正確)
        cmap["VolumeFlow"]["to_si"]["L/s"] = lambda x: x * 1e-3
        cmap["VolumeFlow"]["from_si"]["L/s"] = lambda x: x * 1e3
        # ft³/min (CFM) (正確)
        cmap["VolumeFlow"]["to_si"]["ft³/min"] = lambda x: x * 0.000471947
        cmap["VolumeFlow"]["from_si"]["ft³/min"] = lambda x: x / 0.000471947        
        
        # 熵流率 (EntropyFlow), SI: W/K
        if "EntropyFlow" not in cmap: cmap["EntropyFlow"] = {"to_si": {}, "from_si": {}}
        cmap["EntropyFlow"]["to_si"]["kW/K"] = lambda x: x * 1e3
        cmap["EntropyFlow"]["from_si"]["kW/K"] = lambda x: x * 1e-3
        cmap["EntropyFlow"]["to_si"]["Btu/(h.R)"] = lambda x: x * 0.527528
        cmap["EntropyFlow"]["from_si"]["Btu/(h.R)"] = lambda x: x / 0.527528

        # **效率 (Eff), SI: 小數 (無單位)**
        if "Eff" not in cmap: cmap["Eff"] = {"to_si": {}, "from_si": {}}
        # 顯示: % (例如 80) -> SI: 小數 (例如 0.8)
        cmap["Eff"]["to_si"]["%"] = lambda x: x / 100.0 
        # SI: 小數 (例如 0.8) -> 顯示: % (例如 80)
        cmap["Eff"]["from_si"]["%"] = lambda x: x * 100.0


        # **相對濕度 (RH), SI: 小數 (無單位)**
        if "RH" not in cmap: cmap["RH"] = {"to_si": {}, "from_si": {}}
        # 顯示: % (例如 80) -> SI: 小數 (例如 0.8)
        cmap["RH"]["to_si"]["%"] = lambda x: x / 100.0 
        # SI: 小數 (例如 0.8) -> 顯示: % (例如 80)
        cmap["RH"]["from_si"]["%"] = lambda x: x * 100.0
        
        # 冷凍噸 (US RT) 與 kcal/h 為冷凍空調實務常用的能力單位。SI: W
        cmap["Power"]["to_si"]["RT"] = lambda x: x * 3516.853
        cmap["Power"]["from_si"]["RT"] = lambda x: x / 3516.853
        cmap["Power"]["to_si"]["kcal/h"] = lambda x: x * 1.163
        cmap["Power"]["from_si"]["kcal/h"] = lambda x: x / 1.163

        # 溫差 (DeltaT), SI: K。溫差沒有零點偏移，°C 差值等於 K，°F 差值乘以 5/9。
        cmap["DeltaT"]["to_si"]["°C"] = lambda x: x
        cmap["DeltaT"]["from_si"]["°C"] = lambda x: x
        cmap["DeltaT"]["to_si"]["°F"] = lambda x: x * 5.0 / 9.0
        cmap["DeltaT"]["from_si"]["°F"] = lambda x: x * 9.0 / 5.0

        return cmap

    def convert_to_si(self, prop_code, value, unit_code):
        """將顯示單位值轉換為 SI 基礎單位 (比性質)。

參數：
    prop_code (未指定型別): 函數輸入值。
    value (未指定型別): 函數輸入值。
    unit_code (未指定型別): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
        if prop_code in self._canonical_converter.CORE_PROPERTIES:
            return self._canonical_converter.convert_to_si(prop_code, value, unit_code)
        if prop_code in self.conversion_map and unit_code in self.conversion_map[prop_code]["to_si"]:
            return self.conversion_map[prop_code]["to_si"][unit_code](value)
        return value # 如果找不到轉換，返回原值

    def convert_from_si(self, prop_code, value_si, unit_code):
        """將 SI 單位值轉換為目標顯示單位 (比性質)。

參數：
    prop_code (未指定型別): 函數輸入值。
    value_si (未指定型別): 函數輸入值。
    unit_code (未指定型別): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
        if prop_code in self._canonical_converter.CORE_PROPERTIES:
            return self._canonical_converter.convert_from_si(prop_code, value_si, unit_code)
        if prop_code in self.conversion_map and unit_code in self.conversion_map[prop_code]["from_si"]:
            return self.conversion_map[prop_code]["from_si"][unit_code](value_si)
        return value_si # 如果找不到轉換，返回原值
        
    # --- 修改 ---
    def get_available_units(self, prop_code):
        """安全地返回所有可用的單位列表，並依照 self.unit_order 排序。

參數：
    prop_code (未指定型別): 函數輸入值。

回傳：
    未指定型別：函數計算或處理後的結果。"""
        if prop_code in self.conversion_map:
            # 獲取所有已定義的單位 (來自 conversion_map)
            defined_units = set(self.conversion_map[prop_code]["to_si"].keys())
            
            # 獲取首選的順序
            preferred_order = self.unit_order.get(prop_code, [])
            
            # 1. 按照首選順序排列
            ordered_list = [unit for unit in preferred_order if unit in defined_units]
            
            # 2. 附加上任何在 preferred_order 中 "遺漏" 但
            #    在 conversion_map 中 "已定義" 的單位
            #    (以防我們忘記更新 unit_order)
            missing_units = [unit for unit in defined_units if unit not in ordered_list]
            ordered_list.extend(missing_units)
            
            return ordered_list
        
        return [] # 如果 prop_code 無效