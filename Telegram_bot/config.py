# config.py
# 負責所有設定、路徑管理和日誌系統的初始化。

import os
import sys
import logging
import zipfile
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv

# --- 1. 動態路徑與初始設定 ---
try:
    # 處理 PyInstaller 打包後的路徑問題
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 如果是打包後的執行檔，基礎路徑為執行檔所在目錄
        APPLICATION_PATH = os.path.dirname(sys.executable)
    else:
        # 否則，基礎路徑為腳本所在的目錄
        APPLICATION_PATH = os.path.dirname(os.path.abspath(sys.argv[0]))
except Exception:
    # 處理特殊情況，回退到當前工作目錄
    APPLICATION_PATH = os.getcwd()

# 設定設定檔 (.env) 的路徑
CONFIG_PATH = os.path.join(APPLICATION_PATH, 'config.env')
# 從設定檔載入環境變數
load_dotenv(dotenv_path=CONFIG_PATH)
# 設定日誌檔案的目錄
LOGS_DIR = os.path.join(APPLICATION_PATH, 'logs')
# 如果日誌目錄不存在則創建它
os.makedirs(LOGS_DIR, exist_ok=True)

# --- 2. 專案設定 ---
class Config:
    """專案設定，從 .env 檔案讀取"""
    # 從環境變數讀取 Telegram Bot Token，提供預設值 'YOUR_TELEGRAM_BOT_TOKEN' 
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')
    # 從環境變數讀取 Telegram Chat ID，提供預設值
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', 'YOUR_TELEGRAM_CHAT_ID')
    # TELEGRAM_CHAT_ID 在一對一的 Bot 中不是必需的，可以移除 (註解)

# --- 3. 進階日誌管理系統 ---
def zip_namer(default_name: str) -> str:
    """日誌壓縮檔的命名函式：在預設名稱後加上 .zip"""
    return default_name + ".zip"

def log_rotator_zip(source: str, dest: str):
    """日誌輪替時的壓縮函式：將舊日誌檔案壓縮成 ZIP 檔案並刪除原檔"""
    with zipfile.ZipFile(dest, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        # 將日誌檔案寫入 ZIP 檔案，arcname 確保壓縮包內只有檔名
        zf.write(source, arcname=os.path.basename(source))
    # 刪除原始的日誌檔案
    os.remove(source)

def setup_logging():
    """設定日誌系統，使用 TimedRotatingFileHandler 實現定時輪替和壓縮"""
    log_file_path = os.path.join(LOGS_DIR, 'ThermoBot.log') # 更改日誌檔名
    logger = logging.getLogger("ThermoBot") # 給予一個獨立的 logger 名稱
    logger.setLevel(logging.INFO) # 設定日誌級別為 INFO
    
    if not logger.handlers: # 避免重複加入 handler
        # 檔案 handler (每天輪替一次，保留7份壓縮備份)
        file_handler = TimedRotatingFileHandler(
            log_file_path, when='midnight', interval=1, backupCount=7, encoding='utf-8'
        )
        # 設定日誌輪替時的壓縮和命名函式
        file_handler.rotator = log_rotator_zip
        file_handler.namer = zip_namer
        
        # 設定日誌格式
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # 標準輸出 handler (用於輸出到控制台)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        
        # 將 handlers 加入 logger
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

# 執行日誌設定
setup_logging()
# 為了方便在其他模組中取用，這裡定義一個全域 logger 實例
logger = logging.getLogger("ThermoBot")