# handlers/common_handlers.py
# 存放通用的指令處理函式，如 /start, /cancel 等。

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler
from Telegram_bot.config import logger # 匯入日誌實例 (假設在 config.py 中有定義)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    處理 /start 指令或返回主選單的回呼 (callback)，顯示主選單。

    :param update: Telegram Update 物件，包含使用者訊息或回呼查詢。
    :param context: Telegram ContextTypes 物件，用於儲存狀態和傳遞資料。
    :return: ConversationHandler.END，表示當前對話流程結束。
    """
    # 定義主選單的按鈕
    keyboard = [
        [InlineKeyboardButton("🌡️ 熱力學性質查詢", callback_data='start_prop_calc')],
        [InlineKeyboardButton("⚙️ 冷凍空調原理分析", callback_data='start_analysis_calc')],
    ]
    # 建立內聯鍵盤標記 (InlineKeyboardMarkup)
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    start_message = "👋 <b>歡迎使用熱力學性質與分析 Bot!</b>\n\n請選擇您要執行的功能："
    
    # 判斷是來自按鈕回呼 (callback_query) 還是新的訊息 (message)
    if update.callback_query:
        # 如果是回呼，先響應查詢
        await update.callback_query.answer()
        # 編輯原訊息，將其內容替換為新的主選單
        await update.callback_query.edit_message_text(
            start_message,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    else:
        # 如果是新的 /start 訊息，則發送新的訊息
        await update.message.reply_text(
            start_message,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    logger.info(f"使用者 {update.effective_user.id} 進入主選單。")
    # 返回 END 確保如果有 ConversationHandler 嵌套，也會結束當前對話
    return ConversationHandler.END

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    處理 /cancel 指令，中斷當前對話流程並返回主選單。

    :return: ConversationHandler.END，用於結束對話。
    """
    user_id = update.effective_user.id
    
    # 清除使用者儲存的所有暫存資料
    context.user_data.clear()
    
    logger.info(f"使用者 {user_id} 中斷了對話流程。")
    
    # 判斷是來自回呼還是訊息，以響應用戶操作
    if update.callback_query:
        await update.callback_query.answer()
        # 編輯訊息告知中斷
        await update.callback_query.message.edit_text("❌ <b>操作已中斷。</b>", parse_mode='HTML')
        
    else:
        # 發送新的訊息告知中斷
        await update.message.reply_text("❌ <b>操作已中斷。</b>", parse_mode='HTML')

    # 重新呼叫 start_command 導引使用者回到主選單
    await start_command(update, context)
    
    # 返回 END，通知 ConversationHandler 終止當前對話
    return ConversationHandler.END

# 將 /cancel 指令註冊為 CommandHandler，以便在 ConversationHandler 的 fallbacks 中使用
cancel_handler = CommandHandler("cancel", cancel_command)