# run.py (更新版)
# 專案主入口：選擇啟動 Flet GUI, Tkinter GUI, 或 Telegram Bot。

import sys
import flet as ft # 匯入 Flet 庫
import multiprocessing

# 匯入各個啟動函式
#from gui_app_tkinter import start_gui as start_tkinter_gui # 假設這是 Tkinter 舊版的啟動函式
#from Telegram_bot.bot_application import start_bot # 匯入 Telegram Bot 的啟動函式
from Flet_ui.flet_app import main as flet_main # 匯入 Flet GUI 的主函式

# 匯入設定和日誌
from Telegram_bot.config import setup_logging, logger

# 在程式一開始就設定好日誌系統 (雖然 config.py 已經設定，這裡確保流程)
setup_logging()

def print_usage():
    """列印程式的使用說明。"""
    print("--------------------------------------------------")
    print("使用方式：python run.py [模式]")
    print("模式:")
    print("  flet: 啟動 Flet GUI 模式 (推薦新版)")
    print("  gui / tkinter: 啟動 Tkinter GUI 模式 (舊版)")
    print("  bot: 啟動 Telegram Bot 模式")
    print("--------------------------------------------------")

def main():
    """主函數，根據使用者輸入選擇啟動模式。"""
    logger.info("應用程式啟動...")
     # 啟動 Flet 應用程式，target=flet_main 是 Flet 應用程式的進入點
    ft.app(target=flet_main)
    """
    # 檢查是否有命令列參數
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        if mode == 'flet':
            print("正在啟動 Flet GUI 模式 (新版)...")
            # 啟動 Flet 應用程式，target=flet_main 是 Flet 應用程式的進入點
            ft.app(target=flet_main)
              
        elif mode == 'gui' or mode == 'tkinter':
            print("正在啟動 Tkinter GUI 模式 (舊版)...")
            start_tkinter_gui() # 呼叫 Tkinter 啟動函式
                    
        elif mode == 'bot':
            print("正在啟動 Telegram Bot 模式...")
            multiprocessing.freeze_support() # 冻结支持
            start_bot() # 呼叫 Telegram Bot 啟動函式
        else:
            print(f"錯誤：未知的模式 '{sys.argv[1]}'")
            print_usage()
            sys.exit(1) # 退出程式
    else:
        # 如果沒有帶參數，提供互動式選擇
        while True:
            choice = input("請選擇要啟動的模式 (flet /  bot): ").lower()
            if choice == 'flet':
                print("正在啟動 Flet GUI 模式 (新版)...")
                ft.app(target=flet_main)
                break
                 
            elif choice == 'gui' or choice == 'tkinter':
                print("正在啟動 Tkinter GUI 模式 (舊版)...")
                start_tkinter_gui()
                break
                    
            elif choice == 'bot':
                print("正在啟動 Telegram Bot 模式...")
                start_bot()
                break
            else:
                print("無效的輸入，請重新輸入 'flet'、 'bot'。")
        """
if __name__ == '__main__':
    main()