# telegram_utils.py
# 存放與 Telegram API 互動的底層函式 (例如發送訊息、圖片)。
import os
import requests
from .config import Config, logger

def send_telegram_message(message, silent=False):
    if 'YOUR' in Config.TELEGRAM_BOT_TOKEN or 'YOUR' in Config.TELEGRAM_CHAT_ID:
        if not silent: logger.warning("Telegram 設定包含預設值，跳過訊息發送。")
        return False
    max_length = 4096
    if len(message) > max_length: message = message[:max_length - 10] + "\n...(略)..."
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    # *** 已修改為 HTML ***
    payload = {'chat_id': Config.TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        if not silent: logger.info("[Telegram] 訊息發送成功。")
        return True
    except requests.exceptions.RequestException as e:
        if not silent: logger.error(f"[Telegram] 訊息發送失敗: {e}")
        return False

def send_telegram_photo(image_path, caption=""):
    if 'YOUR' in Config.TELEGRAM_BOT_TOKEN or 'YOUR' in Config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram 設定包含預設值，跳過圖片發送。")
        return False
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(image_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            # *** 已修改為 HTML ***
            data = {'chat_id': Config.TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}
            response = requests.post(url, files=files, data=data, timeout=60)
            response.raise_for_status()
        logger.info(f"[Telegram] 圖片 {os.path.basename(image_path)} 發送成功。")
        try:
            os.remove(image_path)
            logger.info(f"  -> 已刪除本地暫存截圖: {os.path.basename(image_path)}")
        except OSError as e:
            logger.warning(f"  -> 刪除本地截圖失敗: {e}")
        return True
    except (requests.exceptions.RequestException, FileNotFoundError) as e:
        logger.error(f"[Telegram] 圖片發送失敗: {e}")
        return False

def check_telegram_config():
    logger.info("正在檢查 Telegram 設定...")
    # *** 已修改為 HTML ***
    if not send_telegram_message("✅ <b>程式</b> 正在啟動並進行 Telegram 健康檢查...", silent=True):
        logger.critical("="*60)
        logger.critical("!!! TELEGRAM 健康檢查失敗 !!!")
        logger.critical("無法發送測試訊息。請檢查 .env 中的 TOKEN 和 CHAT_ID。")
        logger.critical("腳本將繼續運行，但您將 <b>無法收到任何通知</b>。")
        logger.critical("="*60)
        return False
    logger.info("Telegram 設定看起來是正確的。")
    return True