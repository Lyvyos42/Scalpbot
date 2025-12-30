import os
import re
import json
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ========= CONFIGURATION =========
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'YOUR_BOT_TOKEN_HERE')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '-100YOUR_CHAT_ID_HERE')
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
# =================================

def get_current_time():
    """Get current UTC time in HH:MM format"""
    return datetime.now(timezone.utc).strftime('%H:%M UTC')

def parse_malformed_string(message):
    """
    Parse TradingView's malformed strings like:
    ["pair":"GBPUSD","price":1.35,"action":"LONG"]
    ["pair":"GBPUSD","price":1.35,"action":"LONG_EXIT"]
    """
    result = {}
    try:
        # Remove brackets and split
        content = message.strip('[]')
        # Find all key:value patterns
        pattern = r'"([^"]+)"\s*:\s*"?([^",}\]]+)"?'
        matches = re.findall(pattern, content)
        
        for key, value in matches:
            # Clean and convert
            key = key.strip()
            value = value.strip().replace('"', '').replace("'", "")
            
            # Try to convert numbers
            try:
                if '.' in value:
                    value = float(value)
                else:
                    value = int(value)
            except:
                pass
            
            result[key] = value
    except Exception as e:
        if DEBUG_MODE:
            print(f"Failed to parse malformed string: {e}")
    
    return result

def determine_signal_type(action, message, data):
    """
    Determine if signal is ENTRY or EXIT
    Returns: (is_exit, clean_action, detail_action)
    """
    action_str = str(action).lower()
    message_str = str(message).lower()
    
    # Check for exit indicators
    exit_keywords = ['exit', 'close', 'flat', 'stop', 'target', 'tp', 'sl']
    entry_keywords = ['entry', 'enter', 'open', 'buy', 'sell', 'long', 'short']
    
    # Priority 1: Explicit position size
    if 'position_size' in data:
        try:
            pos_size = float(data.get('position_size', 1))
            if pos_size == 0:
                return True, "EXIT", "POSITION CLOSED"
        except:
            pass
    
    # Priority 2: Action contains exit
    if any(keyword in action_str for keyword in exit_keywords):
        # Determine direction from action
        if 'long' in action_str or 'buy' in action_str:
            return True, "EXIT", "LONG EXIT"
        elif 'short' in action_str or 'sell' in action_str:
            return True, "EXIT", "SHORT EXIT"
        else:
            return True, "EXIT", "EXIT"
    
    # Priority 3: Message contains exit
    if any(keyword in message_str for keyword in exit_keywords):
        if 'long' in message_str:
            return True, "EXIT", "LONG EXIT"
        elif 'short' in message_str:
            return True, "EXIT", "SHORT EXIT"
        else:
            return True, "EXIT", "EXIT"
    
    # Default: Entry signal
    if 'buy' in action_str or 'long' in action_str:
        return False, "LONG", "LONG ENTRY"
    elif 'sell' in action_str or 'short' in action_str:
        return False, "SHORT", "SHORT ENTRY"
    else:
        return False, action_str.upper(), f"{action_str.upper()} ENTRY"

def parse_tradingview_alert(data):
    """
    Extract signal from TradingView webhook.
    Handles all formats:
    1. Structured fields (strategy.order.action, ticker, close)
    2. Malformed JSON strings
    3. Placeholder garbage
    """
    # Initialize defaults
    pair = 'N/A'
    price = 'N/A'
    action = 'N/A'
    message = data.get('message', '')
    
    # ===== EXTRACT PAIR =====
    # Try structured fields first
    pair = data.get('ticker') or data.get('symbol') or data.get('pair')
    
    # Try parsing from malformed string
    if not pair or pair == 'N/A':
        if message and message.startswith('['):
            parsed = parse_malformed_string(message)
            pair = parsed.get('pair', parsed.get('ticker'))
    
    # Try regex from message
    if not pair or pair == 'N/A':
        if message:
            # Look for 6-letter forex pair or 5-letter with digit
            pair_match = re.search(r'([A-Z]{6}|[A-Z]{3}/[A-Z]{3}|[A-Z]{5})', message)
            if pair_match:
                pair = pair_match.group(1)
    
    # ===== EXTRACT PRICE =====
    # Try structured fields
    price = data.get('close') or data.get('price')
    
    # Try parsing from malformed string
    if not price or price == 'N/A':
        if message and message.startswith('['):
            parsed = parse_malformed_string(message)
            price = parsed.get('price')
    
    # Try regex from message
    if not price or price == 'N/A':
        if message:
            price_match = re.search(r'([0-9]+\.?[0-9]*)', str(price) or message)
            if price_match:
                price = price_match.group(1)
    
    # ===== EXTRACT ACTION =====
    # Try structured fields
    action = data.get('strategy.order.action') or data.get('action')
    
    # Try parsing from malformed string
    if not action or action == 'N/A':
        if message and message.startswith('['):
            parsed = parse_malformed_string(message)
            action = parsed.get('action')
    
    # Clean up pair (remove .P, .C for indices)
    if pair:
        pair = str(pair).replace('.P', '').replace('.C', '').replace(' ', '')
    
    # Clean up price formatting
    if price and price != 'N/A':
        try:
            price = float(price)
            # Format with appropriate decimal places
            if price > 1000:  # Indices
                price = f"{price:,.2f}"
            else:  # Forex
                price = f"{price:.5f}"
        except:
            pass
    
    # Determine signal type
    is_exit, clean_action, detail_action = determine_signal_type(action, message, data)
    
    return {
        'pair': pair or 'N/A',
        'price': price or 'N/A',
        'action': clean_action,
        'detail': detail_action,
        'is_exit': is_exit,
        'raw_action': action
    }

def send_telegram_signal(signal_data):
    """Send formatted signal to Telegram group"""
    
    if signal_data['pair'] == 'N/A' or signal_data['price'] == 'N/A':
        if DEBUG_MODE:
            print("Skipping signal - missing critical data")
        return False
    
    # Format based on signal type
    if signal_data['is_exit']:
        emoji = "🔴" if "LOSS" in signal_data['detail'] else "🟡"
        signal = f"{emoji} *EXIT SIGNAL* {emoji}\n\n"
        signal += f"• *PAIR*: `{signal_data['pair']}`\n"
        signal += f"• *ACTION*: `{signal_data['detail']}`\n"
        signal += f"• *EXIT PRICE*: `{signal_data['price']}`\n"
    else:
        emoji = "🟢" if "LONG" in signal_data['detail'] else "🔵"
        signal = f"{emoji} *ENTRY SIGNAL* {emoji}\n\n"
        signal += f"• *PAIR*: `{signal_data['pair']}`\n"
        signal += f"• *DIRECTION*: `{signal_data['detail']}`\n"
        signal += f"• *ENTRY PRICE*: `{signal_data['price']}`\n"
    
    signal += f"• *TIME*: `{get_current_time()}`\n"
    signal += f"• *SOURCE*: `Quantum Scalper v10`"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": signal,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
        "disable_notification": False
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            if DEBUG_MODE:
                print(f"Telegram API error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        if DEBUG_MODE:
            print(f"Failed to send Telegram message: {e}")
        return False

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Main webhook endpoint for TradingView"""
    try:
        # Get JSON data
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
        
        # Log incoming data if in debug mode
        if DEBUG_MODE:
            print("=" * 50)
            print("INCOMING WEBHOOK DATA:")
            print(json.dumps(data, indent=2))
            print("=" * 50)
        
        # Parse the alert
        signal_data = parse_tradingview_alert(data)
        
        # Log parsed data
        if DEBUG_MODE:
            print(f"PARSED SIGNAL: {signal_data}")
        
        # Send to Telegram
        success = send_telegram_signal(signal_data)
        
        if success:
            response = {
                "status": "success",
                "signal_type": "exit" if signal_data['is_exit'] else "entry",
                "pair": signal_data['pair'],
                "action": signal_data['detail'],
                "price": signal_data['price']
            }
            return jsonify(response), 200
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to send signal to Telegram"
            }), 500
            
    except Exception as e:
        error_msg = f"Webhook processing error: {str(e)}"
        if DEBUG_MODE:
            print(error_msg)
        return jsonify({"error": error_msg}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "alive",
        "service": "QuantumScalperBot",
        "version": "2.0",
        "timestamp": get_current_time()
    }), 200

@app.route('/test', methods=['GET', 'POST'])
def test_endpoint():
    """Test endpoint for debugging"""
    if request.method == 'POST':
        data = request.get_json() or {}
        signal_data = parse_tradingview_alert(data)
        return jsonify({
            "received_data": data,
            "parsed_signal": signal_data
        }), 200
    
    return jsonify({
        "message": "Send POST request with TradingView payload to test parsing",
        "example": {
            "ticker": "EURUSD",
            "close": 1.09876,
            "strategy.order.action": "buy",
            "message": '["pair":"EURUSD","price":1.09876,"action":"LONG"]'
        }
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=DEBUG_MODE)