round_number=9 #round=四捨五入到小數點第x位
def cal_p(z):#海拔高度壓力(P)
    """
    cal_p:計算壓力P，單位(kPa)
    輸入參數:float，z=海拔高度(m)
    輸出參數:float，p=壓力(kPa)

    說明:藉由輸入海拔高度(z)計算求得壓力(p)
    
    """
    
    p=101.325*((1-2.25577*10**(-5)*z)**(5.2559))
    p_round=round(p,round_number)
    return p_round

def cal_Pws(T_db):#飽和水蒸氣分壓(Pws)
    """
    計算飽和狀態之水蒸氣分壓(Pws)，單位(kPa)
    輸入參數:float，T_db=乾球溫度(C)
    輸出參數:float，Pws=該溫度球的飽和水蒸汽分壓

    說明:藉由輸入乾球溫度(C)計算求得飽和水蒸汽分壓
    """
    TK = T_db+273.15

    n1 = 0.11670521452767*(10**4)
    n2 = -0.72421316703206*(10**6)
    n3 = -0.17073846940092*(10**2)
    n4 = 0.1202082470247*(10**5)
    n5 = -0.32325550322333*(10**7)
    n6 = 0.1491510861353*(10**2)
    n7 = -0.48232657361591*(10**4)
    n8 = 0.40511340542057*(10**6)
    n9 = -0.23855557567849*(10**0)
    n10 = 0.65017534844798*(10**3)

    theta = TK + n9/(TK-n10)

    a = theta**2+n1*theta+n2
    b = n3*theta**2+ n4 *theta +n5
    c= n6*theta**2+n7*theta+n8

    Pws= 1000*(2*c/(-1*b+(b**2-4*a*c)**0.5))**4
    Pws_round=round(Pws,round_number)
    return Pws_round

def cal_Ws(P1,P2):#飽和濕空氣之濕度比(Ws)
    """
    cal_Ws(P1,P2):計算飽和濕空氣之濕度比，單位(kg/kg)
    輸入參數:
    float，P1=大氣壓力、全壓(kPa)
    float，P2=水蒸氣分壓、飽和狀態下水蒸氣分壓（kPa）
    
    輸出參數:
    float,Ws=濕度比(kg/kg)

    說明:藉由輸入兩種壓力(P1、P2)計算求得濕空氣之濕度比

    """
    Ws=(0.621945*P2)/(P1-P2)
    Ws_round=round(Ws,round_number)
    return Ws_round

def cal_W(Wss,T_db,T_wb):#濕度比(W)
    """
    cal_W(P1,P2):計算濕度比，單位(kg/kg)
    輸入參數:
    float，Wss= 濕求溫度條件下之飽和狀態濕度比(kg/kg)
    float，T_db=乾球溫度(C)
    float，P_wb=濕球溫度(C)
    輸出參數:float,W=濕求溫度比(kg/kg)

    說明:藉由輸入兩種壓力(P1、P2)計算求得濕度比
    """

    W=(((2501-2.326*T_wb)*Wss-1.006*(T_db-T_wb))/((2501+(1.86*T_db))-(4.186*T_wb)))
    W_round=round(W,round_number)
    return W_round

def cal_RH(P1,P2):#相對溼度(RH)
    '''
    cal_RH(P1,W):計算相對溼度，單位(%)
    輸入參數: 
    float，P1= 水蒸氣分壓（kPa)
    float，P2=飽和狀態下之水蒸氣分壓（kPa）  ()
    輸出參數:float,RH=相對溼度(%)
    說明:藉由輸入兩種壓力(P1、P2)計算相對溼度
    '''
    RH=P1/P2*100
    return RH


def cal_Pw(P1,W):#水蒸氣分壓(Pw)
    '''
    cal_RH(P1,W):計算水蒸氣分壓、單位(kPa))
    輸入參數: 
    float，P1= 大氣壓力、全壓（kPa)
    float，W=濕度比（kg/kg）
    輸出參數:float,Pw=水蒸氣分壓(kPa)
    說明:藉由輸入兩種壓力(P1、P2)計算水蒸氣分壓
    '''
    Pw=(P1*W)/(0.621945+W)
    Pw_round=round(Pw,round_number)
    return Pw_round

def cal_v(T_db,P1,P2):#比容(v)
    '''
    cal_v(T_db,P1,P2):計算比容，單位(m^3/kg)
    輸入參數: 
    float，T_db=乾求溫度(C)
    float，P1=大氣壓力、全壓(kPa))
    float，P2=水蒸氣分壓（kPa）
    輸出參數:float,v=比容(m^3/kg)
    說明:藉由輸入乾球溫度(T_db)與兩種壓力(P1、P2)計算求得比容
    '''
    R=8314.742
    T=T_db+273.15
    v=(R*T/(28.966*(P1-P2)))/1000
    v_round=round(v,round_number)
    return v_round

def cal_h(T_db,W):#焓(h)
    """
    cal_v(T_db,W):計算焓，單位(kj/kg)
    輸入參數: 
    float，T_db=乾求溫度(C)
    float，w=濕度比(kg/kg))
    輸出參數:float,h=焓(kj/kg)
    說明:藉由輸入乾求溫度與濕求溫度計算求得焓值
    """
    h=1.006*T_db+W*(2501+1.86*T_db)
    h_round=round(h,round_number)
    return h_round

def Calculation_process_m_Tdb_Twb(m,T_db,T_wb):#空氣線圖計算過程 給高度 乾球溫度 濕球溫度
    P=cal_p(m)#計算海拔高度壓力
    Pws_db=cal_Pws(T_db)#計算飽和水蒸汽狀態分壓 乾球溫度
    Pws_wd=cal_Pws(T_wb)#濕球溫度，飽和狀態之水蒸氣分壓 (濕球溫度)
    Ws=cal_Ws(P,Pws_db)#飽和濕空氣，飽和狀態之濕度比 (壓力、飽和乾球水蒸氣壓力)
    Wss=cal_Ws(P,Pws_wd)#濕球溫度，飽和狀態之濕度比  (壓力、飽和濕球水蒸汽壓力)

    W=cal_W(Wss,T_db,T_wb)#計算濕度比 (濕球飽和濕度比、乾球溫度、濕球溫度)
    Pw=cal_Pw(P,W)#計算水蒸氣分壓 
    RH=cal_RH(Pw,Pws_db)#濕空氣之相對濕度 (水蒸氣壓、乾球飽和水蒸氣壓力)
    h=cal_h(T_db,W)  #濕空氣之焓值
    v=cal_v(T_db,P,Pw)#濕空氣之比容

    return P,Pw,Pws_db,Pws_wd,W,Ws,Wss,RH,h,v



def Calculation_process_m_Tdb_RH(m,T_db,RH):#空氣線圖計算過程

    P=cal_p(m)#計算海拔高度壓力
    Pws_db=cal_Pws(T_db)#計算飽和水蒸汽狀態分壓 乾球溫度
    Pw=cal_Pws_Rh(RH,Pws_db) #計算水蒸氣分壓
    W=cal_Ws(P,Pw) #計算濕度比 
    Ws=cal_Ws(P,Pws_db)#飽和濕空氣，飽和狀態之濕度比 (壓力、飽和乾球水蒸氣壓力)
    h=cal_h(T_db,W)  #濕空氣之焓值
    v=cal_v(T_db,P,Pw)#濕空氣之比容

    calculation_Twb=cal_twb(T_db,P,W)#計算濕球溫度

    Pws_wd=cal_Pws(calculation_Twb)#濕球溫度，飽和狀態之水蒸氣分壓 (濕球溫度)
    Wss=cal_Ws(P,Pws_wd)#濕球溫度，飽和狀態之濕度比  (壓力、飽和濕球水蒸汽壓力)
    return calculation_Twb,P,Pw,Pws_db,Pws_wd,W,Ws,Wss,RH,h,v


#老師解法
"""
def cal_twb(T_db,P,W):
    for Twb_test in range(-10000,35000,1):
        Twb_test=float(Twb_test/1000)
        pws_wb=cal_Pws(Twb_test)
        Wss=cal_Ws(P,pws_wb)

        W_test=cal_W(Wss,T_db,Twb_test)
        error_rate=((W_test-W)/W)*100
        #print(f"Twb_test: {Twb_test}, pws_wb: {pws_wb}, Pwss: {Wss}, W_test: {W_test}, error_rate: {error_rate}")
        if error_rate <= 0.01 and error_rate >=-0.01:
            return Twb_test
"""


#老師解法+二分法提高計算速度與更準確數值
def cal_twb(T_db, P, W):
    # 設定初始範圍
    low = -10000 / 1000  # 最低溫度（單位: 度C）
    high = 55000 / 1000  # 最高溫度（單位: 度C）
    epsilon = 0.001  # 精度範圍

    # 使用二分法逐步縮小範圍
    while (high - low) > epsilon:
        Twb_test = (low + high) / 2  # 計算中間點
        pws_wb = cal_Pws(Twb_test)  # 計算潛在溫度的飽和水蒸氣壓
        Wss = cal_Ws(P, pws_wb)  # 計算飽和水蒸氣
        W_test = cal_W(Wss, T_db, Twb_test)  # 計算試驗的濕球溫度
        error_rate = ((W_test - W) / W) * 100  # 計算誤差率

        # 檢查誤差範圍是否滿足條件
        if abs(error_rate) <= 0.01:
            break
        elif W_test < W:
            low = Twb_test  # 更新下限
        else:
            high = Twb_test  # 更新上限

    # 在縮小的範圍內使用逐步測試法
    for Twb_test in range(int(low * 1000), int(high * 1000), 1):
        Twb_test = float(Twb_test / 1000)  # 轉換單位
        pws_wb = cal_Pws(Twb_test)  # 計算潛在溫度的飽和水蒸氣壓
        Wss = cal_Ws(P, pws_wb)  # 計算飽和水蒸氣
        W_test = cal_W(Wss, T_db, Twb_test)  # 計算試驗的濕球溫度
        error_rate = ((W_test - W) / W) * 100  # 計算誤差率

        # 檢查誤差範圍是否滿足條件
        if error_rate <= 0.01 and error_rate >= -0.01:
            return Twb_test  # 返回滿足條件的濕球溫度

    return (low + high) / 2  # 返回最接近的濕球溫度









def cal_Pws_Rh(RH,Pws_db):
    """
    輸入相對濕度RH
    輸入乾球飽和水蒸氣分壓Pws_db
    輸出水蒸氣分壓
    
    """
    Pw=RH/100*Pws_db
    Pw_round=round(Pw,round_number)
    return Pw_round


def cal_Tdp_from_Pw(Pw):
    """
    根據水蒸氣分壓 (Pw) 反推露點溫度 (Tdp)。
    使用二分法進行求解。
    """
    low = -100.0  # 最低溫度
    high = 200.0  # 最高溫度
    epsilon = 0.001  # 精度

    while (high - low) > epsilon:
        Tdp_test = (low + high) / 2
        # 計算在測試溫度下的飽和水蒸氣壓
        Pws_test = cal_Pws(Tdp_test)
        
        if Pws_test < Pw:
            low = Tdp_test
        else:
            high = Tdp_test
            
    return (low + high) / 2