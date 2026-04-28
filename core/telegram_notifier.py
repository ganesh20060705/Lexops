# LexOps | core/telegram_notifier.py
import os
import json
import urllib.request
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send_telegram(message: str, case_id: str = "", chat_id: str = None) -> dict:
    """
    Send a message via Telegram Bot API.

    Args:
        message:  Text to send
        case_id:  Optional case ID appended to message
        chat_id:  Override default chat ID from env

    Returns:
        Dict with success status, message_id (real) or simulated flag
    """
    token = TELEGRAM_BOT_TOKEN
    target_chat = chat_id or TELEGRAM_CHAT_ID

    full_message = "🏛️ *LexOps Legal Alert*"
    if case_id:
        full_message += f"\n🔖 Case: `{case_id[:8]}`"
    full_message += f"\n\n{message}\n\n📞 NALSA Helpline: *15100*"

    if not token or not target_chat:
        # Simulation mode — no credentials configured
        print(f"[Telegram SIMULATION] {full_message}")
        return {
            "success": True,
            "simulated": True,
            "message": full_message,
            "note": "Simulation mode — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
        }

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": target_chat,
            "text": full_message,
            "parse_mode": "Markdown"
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        if result.get("ok"):
            return {
                "success": True,
                "message_id": result["result"]["message_id"],
                "chat_id": target_chat,
                "note": "Sent via Telegram Bot API"
            }
        else:
            return {"success": False, "error": result.get("description", "Unknown error")}

    except Exception as e:
        return {"success": False, "error": str(e), "note": "Telegram API error"}
