import os
import json
import telebot
from flask import Flask, request, jsonify

app = Flask(__name__)
bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data'}), 400
        
        # Format message
        pair = data.get('pair', 'Unknown')
        action = data.get('action', 'ALERT')
        price = data.get('price', 'N/A')
        
        msg = f"*{action}* {pair} @ ${price}"
        
        # Send to Telegram
        bot.send_message(
            chat_id=os.getenv('TELEGRAM_CHANNEL_ID'),
            text=msg,
            parse_mode='Markdown'
        )
        
        return jsonify({'status': 'sent'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))