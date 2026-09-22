# handlers/analysis_handler.py
# 處理所有「冷凍空調原理分析」相關的對話流程。

from enum import Enum, auto
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
)
from Telegram_bot.thermo_calculator import ThermoCalculator # 匯入 ThermoCalculator

from Telegram_bot.handlers.common_handlers import cancel_handler # 匯入 /cancel 處理器
import logging

logger = logging.getLogger(__name__)
calculator = ThermoCalculator()

# --- 1. 定義對話狀態 (Enum) ---
class AnalysisStates(Enum):
    """定義冷凍空調原理分析的各個對話狀態"""
    SELECTING_TYPE = auto() # 選擇分析類型 (Win, CR, Qe)
    
    # 壓縮機功 (Win) 流程
    WIN_ENTERING_MDOT = auto() # 輸入質量流率
    WIN_ENTERING_H1 = auto()   # 輸入入口焓
    WIN_ENTERING_H2 = auto()   # 輸入出口焓
    
    # 壓縮比 (CR) 流程
    CR_ENTERING_PIN = auto()        # 輸入入口壓力數值
    CR_SELECTING_PIN_TYPE = auto()  # 選擇入口壓力類型 (絕對/錶壓力)
    CR_SELECTING_PIN_UNIT = auto()  # 選擇入口壓力單位
    CR_ENTERING_POUT = auto()       # 輸入出口壓力數值
    CR_SELECTING_POUT_TYPE = auto() # 選擇出口壓力類型
    CR_SELECTING_POUT_UNIT = auto() # 選擇出口壓力單位 (會檢查與 Pin 單位是否一致)
    CR_ENTERING_PATM = auto()       # 輸入大氣壓力 (只有在選擇錶壓力時會用到)
    
    # 蒸發器熱交換率 (Qe) 流程 (此處省略，但結構與 Win 相似)
    QE_ENTERING_MDOT = auto()
    QE_ENTERING_HIN = auto()
    QE_ENTERING_HOUT = auto()

# --- 2. 輔助函式 ---

def get_pressure_units_keyboard(columns: int = 3) -> InlineKeyboardMarkup:
    """
    動態產生壓力單位的鍵盤，從 ThermoCalculator 實例中獲取所有可用的壓力單位。
    
    :param columns: 每行按鈕的最大數量，預設為 3。
    :return: 包含壓力單位按鈕和中斷按鈕的 InlineKeyboardMarkup。
    """
    # 確保 shared_context.calculator 已匯入
    # 假設 calculator 實例 (ThermoCalculator) 已經存在且可用
    try:
        # 使用 get_available_units 函式獲取所有壓力單位
        units = calculator.get_available_units('P')
    except AttributeError:
        # 備援：如果獲取失敗，使用舊的預設值
        units = ["MPa", "kPa", "bar", "psia"]
    
    # 過濾掉可能存在的重複值 (雖然 get_available_units 應該返回唯一值)
    units = sorted(list(set(units)), key=units.index)
         
    # 1. 建立所有單位按鈕
    unit_buttons = [InlineKeyboardButton(unit, callback_data=unit) for unit in units]
    
    # 2. 將按鈕列表分割成多個子列表 (行)，每行最多 columns 個
    keyboard_rows = [unit_buttons[i:i + columns] for i in range(0, len(unit_buttons), columns)]
    
    # 3. 加上 /cancel 按鈕作為最後一行 (通常獨佔一行)
    keyboard_rows.append([InlineKeyboardButton("❌ 中斷 / 返回主選單", callback_data='go_to_start')])

    # 4. 使用 InlineKeyboardMarkup(keyboard_rows) 構建多行鍵盤
    return InlineKeyboardMarkup(keyboard_rows)


# 輔助函式：檢查並轉換輸入的數值
def check_and_get_float(text: str):
    """嘗試將文字轉換為浮點數，如果失敗則拋出 ValueError。"""
    try:
        return float(text.strip())
    except ValueError:
        raise ValueError("輸入的數值無效，請確保您只輸入數字。")

# --- 3. 處理函式 (Handlers) ---

async def analysis_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates:
    """
    對話的起始點：詢問分析項目。
    """
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    
    # 分析項目的按鈕
    keyboard = [
        [InlineKeyboardButton("壓縮機功 (Win)", callback_data='Win')],
        [InlineKeyboardButton("壓縮比 (CR)", callback_data='CR')],
        [InlineKeyboardButton("蒸發器熱交換率 (Qe)", callback_data='Qe')],
        [InlineKeyboardButton("❌ 中斷 / 返回主選單", callback_data='go_to_start')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "⚙️ <b>冷凍空調原理分析</b>\n\n請選擇您要執行的分析項目：",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    # 進入 SELECTING_TYPE 狀態
    return AnalysisStates.SELECTING_TYPE

async def analysis_select_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates:
    """
    接收分析項目的選擇，並導向對應的輸入流程。
    """
    query = update.callback_query
    await query.answer()
    
    analysis_type = query.data
    context.user_data['analysis_type'] = analysis_type
    
    # 根據選擇的類型導向不同狀態
    if analysis_type == 'Win':
        await query.edit_message_text("您選擇了<b>壓縮機功 (Win)</b>。請輸入質量流率 <code>ṁ</code> (kg/s)：", parse_mode='HTML')
        return AnalysisStates.WIN_ENTERING_MDOT
        
    elif analysis_type == 'CR':
        # 壓縮比流程較複雜，從入口壓力數值開始
        await query.edit_message_text("您選擇了<b>壓縮比 (CR)</b>。請輸入入口壓力 <code>P_in</code> 的數值：", parse_mode='HTML')
        return AnalysisStates.CR_ENTERING_PIN
        
    elif analysis_type == 'Qe':
        await query.edit_message_text("您選擇了<b>蒸發器熱交換率 (Qe)</b>。請輸入質量流率 <code>ṁ</code> (kg/s)：", parse_mode='HTML')
        return AnalysisStates.QE_ENTERING_MDOT
        
    else:
        # 非預期選擇，重新回到 SELECTING_TYPE
        await query.message.reply_text("無效的選擇，請重新選擇分析項目。")
        return AnalysisStates.SELECTING_TYPE

# --- 壓縮機功 (Win) 流程處理 ---

async def win_received_mdot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates:
    """接收質量流率，並詢問 h1。"""
    try:
        context.user_data['m_dot'] = check_and_get_float(update.message.text)
        await update.message.reply_text("請輸入入口焓 <code>h1</code> (kJ/kg)：", parse_mode='HTML')
        return AnalysisStates.WIN_ENTERING_H1
    except ValueError as e:
        await update.message.reply_text(f"❌ {e} 請重新輸入質量流率 <code>ṁ</code> (kg/s)：", parse_mode='HTML')
        return AnalysisStates.WIN_ENTERING_MDOT

async def win_received_h1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates:
    """接收 h1，並詢問 h2。"""
    try:
        context.user_data['h1'] = check_and_get_float(update.message.text)
        await update.message.reply_text("請輸入出口焓 <code>h2</code> (kJ/kg)：", parse_mode='HTML')
        return AnalysisStates.WIN_ENTERING_H2
    except ValueError as e:
        await update.message.reply_text(f"❌ {e} 請重新輸入入口焓 <code>h1</code> (kJ/kg)：", parse_mode='HTML')
        return AnalysisStates.WIN_ENTERING_H1

async def win_calculate_and_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """接收 h2，執行 Win 計算並結束對話。"""
    try:
        h2 = check_and_get_float(update.message.text)
        m_dot, h1 = context.user_data['m_dot'], context.user_data['h1']
        
        # 執行計算
        result = calculator.calculate_compressor_work(m_dot, h1, h2)
        
        # 格式化結果
        result_message = (
            f"✅ <b>壓縮機功 (Win) 計算結果</b>\n\n"
            f"輸入: ṁ={m_dot:.3f}, h1={h1:.3f}, h2={h2:.3f}\n"
            f"Win = ṁ * (h2 - h1)\n"
            f"Win = <b>{result:.4f} kW</b>"
        )
        await update.message.reply_text(result_message, parse_mode='HTML')
        
    except ValueError as e:
        await update.message.reply_text(f"❌ 錯誤: {e}", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ 計算發生錯誤: {e}", parse_mode='HTML')
        
    context.user_data.clear()
    # 結束流程，顯示返回主選單按鈕
    await update.message.reply_text("操作完成，請選擇下一步：", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主選單", callback_data='go_to_start')]]))
    return ConversationHandler.END

# --- 壓縮比 (CR) 流程處理 ---

async def cr_received_pin_val(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates:
    """接收 P_in 數值，並詢問壓力類型 (絕對/錶)。"""
    try:
        context.user_data['P_in_val'] = check_and_get_float(update.message.text)
        
        keyboard = [[InlineKeyboardButton("絕對壓力", callback_data='abs'), InlineKeyboardButton("錶壓力", callback_data='gauge')]]
        await update.message.reply_text("請選擇入口壓力 <code>P_in</code> 的類型：", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return AnalysisStates.CR_SELECTING_PIN_TYPE
    except ValueError as e:
        await update.message.reply_text(f"❌ {e} 請重新輸入入口壓力 <code>P_in</code> 的數值：", parse_mode='HTML')
        return AnalysisStates.CR_ENTERING_PIN

async def cr_received_pin_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates:
    """接收 P_in 類型，並詢問 P_in 單位。"""
    query = update.callback_query
    await query.answer()
    context.user_data['P_in_type'] = query.data # 'abs' or 'gauge'
    
    await query.edit_message_text("請選擇入口壓力 <code>P_in</code> 的單位：", reply_markup=get_pressure_units_keyboard(), parse_mode='HTML')
    return AnalysisStates.CR_SELECTING_PIN_UNIT

async def cr_received_pin_unit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates:
    """接收 P_in 單位，並詢問 P_out 數值。"""
    query = update.callback_query
    await query.answer()
    context.user_data['P_in_unit'] = query.data
    
    await query.edit_message_text("✅ 已接收 P_in。請輸入出口壓力 <code>P_out</code> 的數值：", parse_mode='HTML')
    return AnalysisStates.CR_ENTERING_POUT

async def cr_received_pout_val(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates:
    """接收 P_out 數值，並詢問壓力類型。"""
    try:
        context.user_data['P_out_val'] = check_and_get_float(update.message.text)
        
        keyboard = [[InlineKeyboardButton("絕對壓力", callback_data='abs'), InlineKeyboardButton("錶壓力", callback_data='gauge')]]
        await update.message.reply_text("請選擇出口壓力 <code>P_out</code> 的類型：", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return AnalysisStates.CR_SELECTING_POUT_TYPE
    except ValueError as e:
        await update.message.reply_text(f"❌ {e} 請重新輸入出口壓力 <code>P_out</code> 的數值：", parse_mode='HTML')
        return AnalysisStates.CR_ENTERING_POUT

async def cr_received_pout_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates:
    """接收 P_out 類型，並詢問 P_out 單位。"""
    query = update.callback_query
    await query.answer()
    context.user_data['P_out_type'] = query.data # 'abs' or 'gauge'
    
    await query.edit_message_text("請選擇出口壓力 <code>P_out</code> 的單位 (應與 P_in 單位一致)：", reply_markup=get_pressure_units_keyboard(), parse_mode='HTML')
    return AnalysisStates.CR_SELECTING_POUT_UNIT

async def cr_check_and_calculate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates | int:
    """
    接收 P_out 單位，檢查單位是否一致。
    如果不需大氣壓力 (都是絕對壓力)，則直接計算並結束。
    如果需要大氣壓力，則導向輸入大氣壓力狀態。
    """
    query = update.callback_query
    await query.answer()
    context.user_data['P_out_unit'] = query.data
    
    p_in_unit = context.user_data['P_in_unit']
    p_out_unit = context.user_data['P_out_unit']
    p_in_type = context.user_data['P_in_type']
    p_out_type = context.user_data['P_out_type']
    
    # 檢查 P_in 和 P_out 單位是否一致 (CR 計算必須單位統一)
    if p_in_unit != p_out_unit:
        await query.edit_message_text(f"❌ 單位不一致！P_in 單位是 <code>{p_in_unit}</code>，P_out 單位是 <code>{p_out_unit}</code>。請重新選擇 P_out 單位：", reply_markup=get_pressure_units_keyboard(), parse_mode='HTML')
        return AnalysisStates.CR_SELECTING_POUT_UNIT # 導回 P_out 單位選擇
        
    # 如果任一為錶壓力，則需要大氣壓力
    if p_in_type == 'gauge' or p_out_type == 'gauge':
        # 預設值 101.325 kPa (或換算成選定單位)
        default_atm_val_si = calculator._convert_from_si('P', 101325, p_in_unit) # 101.325 kPa in selected unit
        
        await query.edit_message_text(
            f"由於您選擇了錶壓力，請輸入大氣壓力 <code>P_atm</code> 的數值 ({p_in_unit})：\n(預設值: {default_atm_val_si:.3f})", 
            parse_mode='HTML'
        )
        context.user_data['P_atm_default'] = default_atm_val_si
        return AnalysisStates.CR_ENTERING_PATM
    else:
        # 都是絕對壓力，直接計算
        return await cr_calculate_and_finish(update, context, no_patm=True)

async def cr_received_patm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """接收大氣壓力數值，執行 CR 計算並結束對話。"""
    try:
        # 如果使用者輸入了數值
        if update.message and update.message.text:
            p_atm = check_and_get_float(update.message.text)
        else:
            # 沒輸入則使用預設值 (此流程通常是收到訊息，但為了兼容性保留判斷)
            p_atm = context.user_data['P_atm_default'] 
            
        context.user_data['P_atm'] = p_atm
        
        # 導向計算並結束
        return await cr_calculate_and_finish(update, context, no_patm=False)
        
    except ValueError as e:
        await update.message.reply_text(f"❌ {e} 請重新輸入大氣壓力 <code>P_atm</code> 的數值：", parse_mode='HTML')
        return AnalysisStates.CR_ENTERING_PATM

async def cr_calculate_and_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, no_patm: bool) -> int:
    """
    執行壓縮比 (CR) 計算的核心邏輯，並結束對話。
    """
    
    # 處理 update 類型 (來自 Message 或 CallbackQuery)
    if update.callback_query:
        await update.callback_query.answer("計算中...")
        reply_func = update.callback_query.message.reply_text
    else:
        reply_func = update.message.reply_text
        
    data = context.user_data
    p_in_val, p_out_val = data['P_in_val'], data['P_out_val']
    p_in_type, p_out_type = data['P_in_type'], data['P_out_type']
    unit = data['P_in_unit'] # P_in 和 P_out 的單位已確認一致
    p_atm = data.get('P_atm', 0.0)

    try:
        # 1. 將所有輸入值轉換為 SI 絕對壓力
        p_in_abs_si = calculator._convert_to_si('P', p_in_val, unit)
        p_out_abs_si = calculator._convert_to_si('P', p_out_val, unit)
        
        # 2. 如果是錶壓力，加上大氣壓力 (也要先轉成 SI)
        if p_in_type == 'gauge':
            p_atm_si = calculator._convert_to_si('P', p_atm, unit)
            p_in_abs_si += p_atm_si
        if p_out_type == 'gauge':
            p_atm_si = calculator._convert_to_si('P', p_atm, unit)
            p_out_abs_si += p_atm_si
            
        # 3. 執行計算
        result = calculator.calculate_compression_ratio(p_in_abs_si, p_out_abs_si)
        
        # 格式化輸入摘要
        patm_info = f", P_atm={p_atm:.3f} {unit}" if not no_patm else ""
        input_summary = (
            f"輸入: P_in={p_in_val:.3f} ({p_in_type}), P_out={p_out_val:.3f} ({p_out_type}) ({unit}{patm_info})"
        )
        
        # 格式化結果
        result_message = (
            f"✅ <b>壓縮比 (CR) 計算結果</b>\n\n"
            f"{input_summary}\n"
            f"CR = P_out_abs / P_in_abs\n"
            f"CR = <b>{result:.4f}</b>"
        )
        await reply_func(result_message, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"壓縮比計算錯誤: {e}, 數據: {data}")
        await reply_func(f"❌ 計算發生錯誤: {e}", parse_mode='HTML')
        
    context.user_data.clear()
    await reply_func("操作完成，請選擇下一步：", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主選單", callback_data='go_to_start')]]))
    return ConversationHandler.END


# --- 蒸發器熱交換率 (Qe) 流程處理 (結構與 Win 相似) ---

async def qe_received_mdot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates:
    """接收質量流率，並詢問 h_in。"""
    try:
        context.user_data['m_dot'] = check_and_get_float(update.message.text)
        await update.message.reply_text("請輸入入口焓 <code>h_in</code> (kJ/kg)：", parse_mode='HTML')
        return AnalysisStates.QE_ENTERING_HIN
    except ValueError as e:
        await update.message.reply_text(f"❌ {e} 請重新輸入質量流率 <code>ṁ</code> (kg/s)：", parse_mode='HTML')
        return AnalysisStates.QE_ENTERING_MDOT

async def qe_received_hin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AnalysisStates:
    """接收 h_in，並詢問 h_out。"""
    try:
        context.user_data['h_in'] = check_and_get_float(update.message.text)
        await update.message.reply_text("請輸入出口焓 <code>h_out</code> (kJ/kg)：", parse_mode='HTML')
        return AnalysisStates.QE_ENTERING_HOUT
    except ValueError as e:
        await update.message.reply_text(f"❌ {e} 請重新輸入入口焓 <code>h_in</code> (kJ/kg)：", parse_mode='HTML')
        return AnalysisStates.QE_ENTERING_HIN

async def qe_calculate_and_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """接收 h_out，執行 Qe 計算並結束對話。"""
    try:
        h_out = check_and_get_float(update.message.text)
        m_dot, h_in = context.user_data['m_dot'], context.user_data['h_in']
        
        # 執行計算
        result = calculator.calculate_evaporator_heat_rate(m_dot, h_in, h_out)
        
        # 格式化結果
        result_message = (
            f"✅ <b>蒸發器熱交換率 (Qe) 計算結果</b>\n\n"
            f"輸入: ṁ={m_dot:.3f}, h_in={h_in:.3f}, h_out={h_out:.3f}\n"
            f"Qe = ṁ * (h_out - h_in)\n"
            f"Qe = <b>{result:.4f} kW</b>"
        )
        await update.message.reply_text(result_message, parse_mode='HTML')
        
    except ValueError as e:
        await update.message.reply_text(f"❌ 錯誤: {e}", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ 計算發生錯誤: {e}", parse_mode='HTML')
        
    context.user_data.clear()
    await update.message.reply_text("操作完成，請選擇下一步：", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("返回主選單", callback_data='go_to_start')]]))
    return ConversationHandler.END


# --- 4. ConversationHandler 定義 ---

analysis_conv_handler = ConversationHandler(
    # 進入點：來自主選單中「冷凍空調原理分析」按鈕的回呼
    entry_points=[CallbackQueryHandler(analysis_start, pattern='^start_analysis_calc$')],
    
    # 狀態機
    states={
        AnalysisStates.SELECTING_TYPE: [CallbackQueryHandler(analysis_select_type)],
        
        # Win 流程
        AnalysisStates.WIN_ENTERING_MDOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, win_received_mdot)],
        AnalysisStates.WIN_ENTERING_H1: [MessageHandler(filters.TEXT & ~filters.COMMAND, win_received_h1)],
        AnalysisStates.WIN_ENTERING_H2: [MessageHandler(filters.TEXT & ~filters.COMMAND, win_calculate_and_finish)],
        
        # Qe 流程
        AnalysisStates.QE_ENTERING_MDOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, qe_received_mdot)],
        AnalysisStates.QE_ENTERING_HIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, qe_received_hin)],
        AnalysisStates.QE_ENTERING_HOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, qe_calculate_and_finish)],
        
        # CR 流程 (最複雜)
        AnalysisStates.CR_ENTERING_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, cr_received_pin_val)],
        AnalysisStates.CR_SELECTING_PIN_TYPE: [CallbackQueryHandler(cr_received_pin_type)],
        AnalysisStates.CR_SELECTING_PIN_UNIT: [CallbackQueryHandler(cr_received_pin_unit)],
        AnalysisStates.CR_ENTERING_POUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cr_received_pout_val)],
        AnalysisStates.CR_SELECTING_POUT_TYPE: [CallbackQueryHandler(cr_received_pout_type)],
        AnalysisStates.CR_SELECTING_POUT_UNIT: [CallbackQueryHandler(cr_check_and_calculate)],
        # CR 流程的最終輸入
        AnalysisStates.CR_ENTERING_PATM: [MessageHandler(filters.TEXT & ~filters.COMMAND, cr_received_patm)],
    },
    
    # 發生錯誤或中斷時的處理器
    fallbacks=[cancel_handler],
)