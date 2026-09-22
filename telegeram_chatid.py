import requests
import json

def get_telegram_chat_id(token):
    """
    自動從 Bot 的 getUpdates 取得第一個聊天的 Chat ID。

    參數:
    - token (str): 你的 Telegram Bot Token。

    回傳:
    - str or None: 如果成功取得 Chat ID，回傳該 ID 的字串；否則回傳 None。
    """
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('ok') and data.get('result'):
            # 取得最新的更新訊息
            chat_id = data['result'][-1]['message']['chat']['id']
            print(f"成功取得 Chat ID: {chat_id}")
            return str(chat_id)
        else:
            print("無法從 getUpdates 取得有效的 Chat ID。")
            print(f"伺服器回應：{data}")
            return None
    except requests.exceptions.RequestException as e:
        print("獲取 Chat ID 連線錯誤或請求失敗：")
        print(f"錯誤訊息：{e}")
        return None

def send_telegram_message(message, token, chat_id):
    """
    發送訊息至 Telegram 聊天室。

    參數:
    - message (str): 要發送的訊息文字。
    - token (str): 你的 Telegram Bot Token。
    - chat_id (str): Telegram 聊天 ID。
    
    回傳:
    - bool: 如果訊息成功發送，回傳 True；否則回傳 False。
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        response_data = response.json()

        if response_data.get('ok', False):
            print("訊息已成功發送至 Telegram。")
            return True
        else:
            print("Telegram API 請求失敗：")
            print(f"伺服器回應：{response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print("連線錯誤或請求失敗：")
        print(f"錯誤訊息：{e}")
        return False
    except json.JSONDecodeError as e:
        print("API 回應解析失敗：")
        print(f"錯誤訊息：{e}")
        return False


### 使用範例與測試邏輯

if __name__ == "__main__":
    # 請替換成你自己的 Bot Token
    TELEGRAM_BOT_TOKEN = "8347803327:AAFi3sImbvz1XVTHjTIa3Fw2mnNNPoyd5O8"
    MESSAGE_TEXT = "你好，這是一則自動獲取 Chat ID 後發送的測試訊息！"

    # 步驟 1: 嘗試自動獲取 Chat ID
    # 注意：請先在 Telegram 上與你的 Bot 至少發送過一次訊息，
    # 這樣 getUpdates 才能找到你的聊天資訊。
    chat_id = get_telegram_chat_id(TELEGRAM_BOT_TOKEN)

    if chat_id:
        # 步驟 2: 如果成功獲取 Chat ID，則發送訊息
        is_sent = send_telegram_message(MESSAGE_TEXT, TELEGRAM_BOT_TOKEN, chat_id)
        if is_sent:
            print("測試發送流程：發送成功！")
        else:
            print("測試發送流程：發送失敗，請檢查 Token 和網路連線。")
    else:
        print("無法執行發送測試。請確認 Bot Token 正確，並先與你的 Bot 聊天過。")