import os
import json
import telebot
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# ========= CONFIGURATION =========
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID', '@yourchannel')  # Can be ID or @username

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

def format_telegram_message(data):
    """Parse your strategy's JSON into readable Telegram format"""
    try:
        if isinstance(data, str):
            data = json.loads(data)
        
        # Enhanced format parsing (from your strategy)
        if 'pair' in data:
            action = data.get('action', 'ALERT')
            pair = data.get('pair', 'N/A')
            price = data.get('price', 'N/A')
            reason = data.get('reason', '')
            
            # Determine emoji
            emoji = "⚡"
            if "LONG" in action:
                emoji = "🟢"
            elif "SHORT" in action:
                emoji = "🔴"
            elif "EXIT" in action:
                emoji = "🟡"
            
            # Format message
            message = f"{emoji} *{action}* {emoji}\n"
            message += f"• *Pair:* {pair}\n"
            message += f"• *Price:* ${price}\n"
            message += f"• *Timeframe:* {data.get('timeframe', 'N/A')}\n"
            message += f"• *Reason:* {reason}\n"
            
            # Add SL/TP if present
            if 'sl_price' in data:
                message += f"• *SL:* ${data['sl_price']}\n"
            if 'tp_price' in data:
                message += f"• *TP:* ${data['tp_price']}\n"
            
            # Add indicators
            message += f"• *ADX:* {data.get('adx_val', 'N/A')}\n"
            message += f"• *ATR:* {data.get('atr', 'N/A')}\n"
            message += f"• *Volatility:* {data.get('volatility', 'N/A')}%\n"
            
            # Add timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"\n`{timestamp}`"
            
            return message, True
        
        return str(data), False
        
    except Exception as e:
        return f"Alert received but formatting failed: {str(data)[:200]}", False

@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint that TradingView calls"""
    try:
        # Get data from TradingView
        data = request.get_json()
        
        if not data:
            data = request.get_data(as_text=True)
            try:
                data = json.loads(data)
            except:
                pass
        
        # Format and send to Telegram
        message, is_formatted = format_telegram_message(data)
        
        # Send to Telegram
        bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        return jsonify({'status': 'success', 'sent': True}), 200
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'alive'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)