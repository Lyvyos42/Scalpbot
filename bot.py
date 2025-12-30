import os
import json
import re
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ========= CONFIG =========
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'YOUR_BOT_TOKEN_HERE')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '-100YOUR_CHAT_ID')
# ==========================

def parse_tradingview_alert(data):
    """
    Extract signal from TradingView webhook.
    Handles:
    1. Structured fields (strategy.order.action, ticker, close)
    2. Malformed strings like ["pair":"EURUSD","price":1.17709,"action":"LONG_MR_EXIT"]
    3. Placeholder garbage like {alert_message}
    """
    
    # Priority 1: Structured fields (most reliable)
    pair = data.get('ticker') or data.get('symbol') or data.get('pair') or 'N/A'
    price = data.get('close') or data.get('price') or 'N/A'
    action = data.get('strategy.order.action') or data.get('action') or 'N/A'
    
    # Priority 2: Parse message field if structured fields missing
    message = data.get('message', '')
    
    if 'N/A' in [pair, price, action] and message:
        # Case 1: Malformed array string
        if message.startswith('[') and ':' in message:
            try:
                # Clean: remove brackets, split by commas
                clean = message.strip('[]')
                # Find all key:value patterns
                pattern = r'"([^"]+)"\s*:\s*"?([^",}]+)"?'
                matches = re.findall(pattern, clean)
                for key, value in matches:
                    if key == 'pair': pair = value
                    if key == 'price': price = value
                    if key == 'action': action = value
            except:
                pass
        
        # Case 2: Contains actual signal words
        elif any(word in message.upper() for word in ['LONG', 'SHORT', 'BUY', 'SELL']):
            # Extract pair (6-letter forex code)
            pair_match = re.search(r'([A-Z]{6})', message)
            if pair_match: pair = pair_match.group(1)
            
            # Extract price
            price_match = re.search(r'([0-9]+\.[0-9]+)', message)
            if price_match: price = price_match.group(1)
            
            # Extract action
            if 'LONG' in message.upper() or 'BUY' in message.upper():
                action = 'LONG'
            elif 'SHORT' in message.upper() or 'SELL' in message.upper():
                action = 'SHORT'
    
    return pair, price, action

def send_telegram_signal(pair, price, action):
    """Send formatted signal to Telegram group"""
    if action == 'N/A' or pair == 'N/A':
        return False
    
    # Format: QS | EURUSD | LONG @ 1.09876
    signal = f"🚨 *QS SIGNAL* 🚨\n\n"
    signal += f"• *PAIR*: `{pair}`\n"
    signal += f"• *ACTION*: `{action}`\n"
    signal += f"• *PRICE*: `{price}`\n"
    signal += f"• *TIME*: `{get_current_time()}`"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": signal,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.status_code == 200
    except:
        return False

def get_current_time():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%H:%M UTC')

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Main webhook endpoint for TradingView"""
    try:
        # Get JSON data
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON received"}), 400
        
        # Parse the alert
        pair, price, action = parse_tradingview_alert(data)
        
        # Send to Telegram
        success = send_telegram_signal(pair, price, action)
        
        if success:
            return jsonify({
                "status": "success",
                "signal": f"{pair} {action} @ {price}"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to send signal"
            }), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "alive", "service": "QuantumScalperBot"}), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)