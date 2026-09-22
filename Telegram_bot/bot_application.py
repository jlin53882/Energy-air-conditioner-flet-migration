# bot_application.py
# 負責建立並設定 Telegram Bot Application 物件，並將所有 handlers 組合起來。

from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from .config import Config, logger # 匯入設定和日誌
# 匯入輔助函式 (send_telegram_message 雖然沒用在主邏輯，但仍可能用於檢查/除錯)
from .telegram_utils import send_telegram_message 

# 從 handlers 模組中匯入各個功能的處理器 (此處假設 handlers 資料夾存在)
from .handlers.common_handlers import start_command
from .handlers.property_handler import prop_conv_handler
from .handlers.analysis_handler import analysis_conv_handler

def create_application() -> Application:
    """建立並回傳一個設定好的 Telegram Application 物件。"""
    
    # 安全檢查：確保 Bot Token 不是預設值
    if 'YOUR' in Config.TELEGRAM_BOT_TOKEN:
        logger.critical("錯誤：請在 .env 或環境變數中設定您的 TELEGRAM_BOT_TOKEN。")
        raise ValueError("TELEGRAM_BOT_TOKEN not set.")

    # 使用 Application.builder 建立 Bot 應用程式實例
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # --- 註冊所有處理器 ---
    
    # 1. 註冊通用指令 (例如 /start)
    application.add_handler(CommandHandler("start", start_command))
    # 註冊回呼查詢處理器 (例如按鈕的回調，pattern='^go_to_start$' 表示回到主選單的按鈕)
    application.add_handler(CallbackQueryHandler(start_command, pattern='^go_to_start$'))
    
    # 2. 註冊兩個主要的對話流程 (ConversationHandler)
    # prop_conv_handler 處理性質計算的對話流程
    application.add_handler(prop_conv_handler)
    # analysis_conv_handler 處理分析計算的對話流程
    application.add_handler(analysis_conv_handler)

    return application

def start_bot():
    """
    啟動 Telegram Bot 應用程式的主函式。
    """
    # 建立應用程式實例
    application = create_application()
    
    logger.info("Bot Application 建立完成，開始 Polling (長輪詢)...")
    send_telegram_message("ThermoBot 已啟動並開始運行 /start 指令以進入主選單。")
    
    # 檢查 Telegram 設定是否正常 (可選)
    # check_telegram_config() 
    
    # 以長輪詢模式啟動 Bot
    application.run_polling()