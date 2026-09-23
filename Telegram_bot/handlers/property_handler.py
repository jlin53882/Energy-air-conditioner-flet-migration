# handlers/property_handler.py
# 處理所有「熱力性質查詢」相關的對話流程。

from enum import Enum, auto
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
)
# 從共享的 context 模組中導入 calculator 實例，用於屬性計算
from Telegram_bot.thermo_calculator import ThermoCalculator
calculator = ThermoCalculator()

# 導入通用的取消處理器
from Telegram_bot.handlers.common_handlers import cancel_handler

# === 狀態定義 ===
# 使用 Enum 來定義對話中的各個狀態，讓程式碼更具可讀性和可維護性。
class PropStates(Enum):
    SELECTING_FLUID = auto() # 狀態 1: 等待使用者輸入流體名稱
    SELECTING_PROP1 = auto() # 狀態 2: 等待使用者選擇第一個性質
    ENTERING_VALUE1 = auto() # 狀態 3: 等待使用者輸入第一個性質的數值
    SELECTING_UNIT1 = auto() # 狀態 4: 等待使用者選擇第一個性質的單位
    SELECTING_PROP2 = auto() # 狀態 5: 等待使用者選擇第二個性質
    ENTERING_VALUE2 = auto() # 狀態 6: 等待使用者輸入第二個性質的數值
    SELECTING_UNIT2 = auto() # 狀態 7: 等待使用者選擇第二個性質的單位

# === 輔助函式 ===

def get_property_keyboard(prop_list, columns=3):
    """
    根據提供的屬性列表（字典），動態生成一個 InlineKeyboardMarkup。
    
    Args:
        prop_list (dict): 屬性字典，格式為 {'代碼': '名稱', ...}。
        columns (int): 鍵盤每行顯示的按鈕數量，預設為 3。
        
    回傳：
        InlineKeyboardMarkup: 生成的鍵盤物件。
    """
    # 根據字典生成所有按鈕物件
    buttons = [InlineKeyboardButton(name, callback_data=code) for code, name in prop_list.items()]
    
    # 【核心】將一個長列表的按鈕，分割成多個子列表（每行）
    # 這是個很聰明的寫法，可以自動將按鈕排版成多行多列的網格。
    # 例如 [b1, b2, b3, b4, b5] 且 columns=3 -> [[b1, b2, b3], [b4, b5]]
    menu_layout = [buttons[i:i + columns] for i in range(0, len(buttons), columns)]
    
    # 直接使用 menu_layout 來建立鍵盤
    return InlineKeyboardMarkup(menu_layout)

def get_units_keyboard(prop_code, columns=3):
    """
    動態從 calculator 獲取指定性質的可用單位，
    並生成每行最多顯示 3 個按鈕的鍵盤。
    """
    # 1. 從 calculator 動態獲取單位列表
    units = calculator.get_available_units(prop_code)
    
    # 2. 根據單位列表生成所有按鈕物件
    buttons = [InlineKeyboardButton(unit, callback_data=unit) for unit in units]
    
    # 3. 【核心修改】將按鈕列表分割成多個子列表（每行最多 columns 個）
    #    這段程式碼與 get_property_keyboard 中的邏輯完全相同。
    menu_layout = [buttons[i:i + columns] for i in range(0, len(buttons), columns)]
    
    # 4. 使用分行後的新佈局來建立鍵盤
    return InlineKeyboardMarkup(menu_layout)

# === 對話流程處理函式 ===

async def prop_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PropStates:
    """對話的進入點。當使用者點擊「性質查詢」按鈕時觸發。

參數：
    update (Update): 函數輸入值。
    context (ContextTypes.DEFAULT_TYPE): 函數輸入值。

回傳：
    PropStates：函數計算或處理後的結果。"""
    query = update.callback_query
    await query.answer() # 回應 callback query，讓客戶端知道機器人已收到請求
    context.user_data.clear() # 清空之前的對話資料，確保一個乾淨的開始
    
    # 編輯原訊息，引導使用者輸入流體名稱
    await query.edit_message_text(
        text="好的，讓我們開始<b>性質查詢</b>。\n\n請直接輸入您想查詢的<b>流體名稱</b> (例如: <code>R32</code> 或 <code>Water</code>)：",
        parse_mode='HTML'
    )
    # 返回下一個狀態，告訴 ConversationHandler 接下來應由 SELECTING_FLUID 狀態的處理器接手
    return PropStates.SELECTING_FLUID

async def prop_received_fluid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PropStates:
    """接收並驗證使用者輸入的流體名稱。

參數：
    update (Update): 函數輸入值。
    context (ContextTypes.DEFAULT_TYPE): 函數輸入值。

回傳：
    PropStates：函數計算或處理後的結果。"""
    fluid_name = update.message.text.strip() # 獲取使用者輸入的文字並去除頭尾空白

    # --- 呼叫 calculator 進行驗證 ---
    if calculator.is_fluid_valid(fluid_name):
        # 驗證成功：儲存流體名稱到 user_data 中，以便後續步驟使用
        context.user_data['fluid'] = fluid_name
        # 產生性質選擇鍵盤
        keyboard = get_property_keyboard(calculator.prop_names)
        await update.message.reply_text(
            f"✅ 流體 <code>{fluid_name}</code> 有效。\n\n請選擇<b>第一個</b>已知性質：",
            reply_markup=keyboard, 
            parse_mode='HTML'
        )
        # 進入下一個狀態：選擇第一個性質
        return PropStates.SELECTING_PROP1
    else:
        # 驗證失敗：回傳錯誤訊息，並停留在當前步驟，讓使用者重新輸入
        await update.message.reply_text(
            f"❌ 找不到流體 <code>{fluid_name}</code>。\n\n請檢查拼字或輸入一個有效的流體名稱 (例如: <code>R32</code>, <code>Water</code>)：",
            parse_mode='HTML'
        )
        # 保持在「選擇流體」的狀態，等待使用者再次輸入
        return PropStates.SELECTING_FLUID

async def prop_received_prop1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PropStates:
    """處理使用者選擇的第一個性質。

參數：
    update (Update): 函數輸入值。
    context (ContextTypes.DEFAULT_TYPE): 函數輸入值。

回傳：
    PropStates：函數計算或處理後的結果。"""
    query = update.callback_query
    await query.answer()
    
    # 從 callback_data 中獲取性質代碼 (例如 'P', 'T')
    prop1_code = query.data
    context.user_data['prop1_code'] = prop1_code
    
    # 從 calculator 獲取性質的完整名稱
    prop1_name = calculator.prop_names[prop1_code]
    
    await query.edit_message_text(
        text=f"好的，第一個性質是 <b>{prop1_name}</b>。\n\n現在請輸入它的 <b>數值</b>：",
        parse_mode='HTML'
    )
    # 進入下一個狀態：輸入數值
    return PropStates.ENTERING_VALUE1

async def prop_received_value1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PropStates:
    """處理使用者輸入的第一個數值，並驗證其是否為數字。

參數：
    update (Update): 函數輸入值。
    context (ContextTypes.DEFAULT_TYPE): 函數輸入值。

回傳：
    PropStates：函數計算或處理後的結果。"""
    try:
        # 嘗試將使用者輸入轉換為浮點數
        value1 = float(update.message.text.strip())
        context.user_data['value1'] = value1
        
        # 獲取前面步驟儲存的性質代碼和名稱
        prop1_code = context.user_data['prop1_code']
        prop1_name = calculator.prop_names[prop1_code]
        
        # 產生對應的單位鍵盤
        keyboard = get_units_keyboard(prop1_code)
        
        await update.message.reply_text(
            f"已設定 <b>{prop1_name}</b> = <code>{value1}</code>\n\n請選擇它的 <b>單位</b>：",
            parse_mode='HTML', 
            reply_markup=keyboard
        )
        # 進入下一個狀態：選擇單位
        return PropStates.SELECTING_UNIT1
    except ValueError:
        # 如果轉換失敗（例如，使用者輸入了文字），則提示錯誤
        await update.message.reply_text("❌ 輸入無效，請輸入一個純數字。請再試一次：", parse_mode='HTML')
        # 保持在「輸入數值」的狀態
        return PropStates.ENTERING_VALUE1

async def prop_received_unit1_and_ask_prop2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PropStates:
    """處理使用者選擇的第一個單位，並引導使用者選擇第二個性質。

參數：
    update (Update): 函數輸入值。
    context (ContextTypes.DEFAULT_TYPE): 函數輸入值。

回傳：
    PropStates：函數計算或處理後的結果。"""
    query = update.callback_query
    await query.answer()
    context.user_data['unit1'] = query.data # 儲存單位
    
    # 從性質列表中移除已經選過的第一個性質，避免使用者重複選擇
    prop1_code = context.user_data['prop1_code']
    remaining_props = {k: v for k, v in calculator.prop_names.items() if k != prop1_code}
    
    # 產生剩餘性質的鍵盤
    keyboard = get_property_keyboard(remaining_props)
    await query.edit_message_text(
        text="第一組參數設定完成。\n\n現在，請選擇 <b>第二個</b> 已知性質：",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    # 進入下一個狀態：選擇第二個性質
    return PropStates.SELECTING_PROP2

# --- 第二組參數的處理函式 (prop_received_prop2, prop_received_value2) ---
# 這部分的邏輯與第一組參數的處理非常相似。

async def prop_received_prop2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PropStates:
    """處理使用者選擇的第二個性質。

參數：
    update (Update): 函數輸入值。
    context (ContextTypes.DEFAULT_TYPE): 函數輸入值。

回傳：
    PropStates：函數計算或處理後的結果。"""
    query = update.callback_query
    await query.answer()
    prop2_code = query.data
    context.user_data['prop2_code'] = prop2_code
    prop2_name = calculator.prop_names[prop2_code]
    await query.edit_message_text(
        text=f"好的，第二個性質是 <b>{prop2_name}</b>。\n\n現在請輸入它的 <b>數值</b>：",
        parse_mode='HTML'
    )
    return PropStates.ENTERING_VALUE2

async def prop_received_value2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PropStates:
    """處理使用者輸入的第二個數值。

參數：
    update (Update): 函數輸入值。
    context (ContextTypes.DEFAULT_TYPE): 函數輸入值。

回傳：
    PropStates：函數計算或處理後的結果。"""
    try:
        value2 = float(update.message.text.strip())
        context.user_data['value2'] = value2
        prop2_code = context.user_data['prop2_code']
        prop2_name = calculator.prop_names[prop2_code]
        keyboard = get_units_keyboard(prop2_code)
        await update.message.reply_text(
            f"已設定 <b>{prop2_name}</b> = <code>{value2}</code>\n\n請選擇它的 <b>單位</b>：",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return PropStates.SELECTING_UNIT2
    except ValueError:
        await update.message.reply_text("❌ 輸入無效，請輸入一個純數字。請再試一次：", parse_mode='HTML')
        return PropStates.ENTERING_VALUE2

async def prop_calculate_and_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """接收完所有參數後，進行最終計算並結束對話。

參數：
    update (Update): 函數輸入值。
    context (ContextTypes.DEFAULT_TYPE): 函數輸入值。

回傳：
    int：函數計算或處理後的結果。"""
    query = update.callback_query
    await query.answer()
    context.user_data['unit2'] = query.data
    
    # 先向使用者顯示正在計算的提示訊息
    await query.edit_message_text("⚙️ 收到所有參數，正在為您計算性質...", parse_mode='HTML')

    # 從 user_data 中提取所有已收集的資訊
    ud = context.user_data
    # 整理輸入參數的摘要，方便顯示
    input_summary = (
        f"<b>流體</b>: <code>{ud['fluid']}</code>\n"
        f"<b>已知 1</b>: {calculator.prop_names[ud['prop1_code']]} = <code>{ud['value1']} {ud['unit1']}</code>\n"
        f"<b>已知 2</b>: {calculator.prop_names[ud['prop2_code']]} = <code>{ud['value2']} {ud['unit2']}</code>"
    )

    try:
        # 準備傳遞給後端計算函式的參數
        known_props = [(ud['prop1_code'], ud['value1'], ud['unit1']), (ud['prop2_code'], ud['value2'], ud['unit2'])]
        # 呼叫後端進行計算
        si_results = calculator.calculate_properties(fluid=ud['fluid'], known_props=known_props)
        # 判斷使用者是否輸入了英制單位，以決定輸出格式
        use_imperial = any(p[2] in calculator.imperial_units.values() for p in known_props)
        # 將計算結果格式化為易於閱讀的字串
        formatted_results = calculator.format_specific_properties(si_results, use_imperial)
        # 組合最終的成功訊息
        final_message = f"✅ <b>計算完成</b>\n\n--- 輸入 ---\n{input_summary}\n\n{formatted_results}"
    except (ValueError, RuntimeError) as e:
        # 如果計算過程中發生錯誤 (例如，輸入的狀態無效)，則捕獲異常
        final_message = f"❌ <b>計算失敗</b>\n\n--- 輸入 ---\n{input_summary}\n\n<b>錯誤</b>: <code>{e}</code>"
    
    # 編輯訊息，顯示最終結果（成功或失敗）
    await query.edit_message_text(final_message, parse_mode='HTML')
    # 清理 user_data，為下一次對話做準備
    context.user_data.clear()

    # 提供一個「返回主選單」的按鈕，讓使用者可以方便地進行其他操作
    keyboard = [[InlineKeyboardButton("返回主選單", callback_data='go_to_start')]]
    await query.message.reply_text("操作完成，請選擇下一步：", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # 返回 ConversationHandler.END，正式結束此次對話
    return ConversationHandler.END

# === ConversationHandler 組裝 ===
# 這是整個對話流程的核心。
prop_conv_handler = ConversationHandler(
    # entry_points: 對話的入口，這裡設定為當使用者點擊 callback_data 為 'start_prop_calc' 的按鈕時，啟動 prop_start 函式。
    entry_points=[CallbackQueryHandler(prop_start, pattern='^start_prop_calc$')],
    
    # states: 定義了每個狀態（來自 PropStates Enum）應該由哪個處理器來處理。
    # 例如，在 SELECTING_FLUID 狀態時，只接受文字訊息 (MessageHandler)，並交由 prop_received_fluid 處理。
    # 在 SELECTING_PROP1 狀態時，只接受回呼查詢 (CallbackQueryHandler)，並交由 prop_received_prop1 處理。
    states={
        PropStates.SELECTING_FLUID: [MessageHandler(filters.TEXT & ~filters.COMMAND, prop_received_fluid)],
        PropStates.SELECTING_PROP1: [CallbackQueryHandler(prop_received_prop1)],
        PropStates.ENTERING_VALUE1: [MessageHandler(filters.TEXT & ~filters.COMMAND, prop_received_value1)],
        PropStates.SELECTING_UNIT1: [CallbackQueryHandler(prop_received_unit1_and_ask_prop2)],
        PropStates.SELECTING_PROP2: [CallbackQueryHandler(prop_received_prop2)],
        PropStates.ENTERING_VALUE2: [MessageHandler(filters.TEXT & ~filters.COMMAND, prop_received_value2)],
        PropStates.SELECTING_UNIT2: [CallbackQueryHandler(prop_calculate_and_finish)],
    },
    
    # fallbacks: 定義了如果使用者在任何狀態下輸入了非預期的指令（例如 /cancel），應該如何處理。
    # 這裡設定為呼叫 cancel_handler。
    fallbacks=[cancel_handler],
    
    # per_message=False: 這是一個重要的效能和體驗優化。
    # 設為 False 意味著同一個使用者的多個對話（例如，一個查詢性質，一個查詢週期）可以同時進行，
    # 只要它們的觸發訊息不同。如果設為 True，則使用者一次只能進行一個 ConversationHandler 的對話。
    # 對於這種情況，False 是更好的選擇。
    per_message=False
)