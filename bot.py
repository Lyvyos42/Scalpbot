import os
import re
import json
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ========= PRODUCTION CONFIG =========
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Force production mode if PORT is set (Railway environment)
IS_PRODUCTION = bool(os.getenv('PORT'))
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true' and not IS_PRODUCTION

# Risk Parameters
RISK_PARAMS = {
    'forex': {'tp1_pips': 15, 'tp2_pips': 30, 'tp3_pips': 50, 'sl_pips': 20, 'pip_value': 0.0001},
    'indices': {'tp1_points': 30, 'tp2_points': 60, 'tp3_points': 100, 'sl_points': 40, 'point_value': 1.0},
    'commodities': {'tp1_pips': 50, 'tp2_pips': 100, 'tp3_pips': 150, 'sl_pips': 75, 'pip_value': 0.01}
}
# =====================================

def log_message(msg):
    """Safe logging that works in production"""
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")

def get_current_time():
    return datetime.now(timezone.utc).strftime('%H:%M UTC')

def format_timeframe(interval):
    if not interval:
        return "N/A"
    
    timeframe_map = {
        '1': '1m', '5': '5m', '15': '15m', '30': '30m',
        '60': '1H', '120': '2H', '240': '4H', '360': '6H',
        '480': '8H', '720': '12H', '1440': '1D', 'D': '1D',
        'W': '1W', 'M': '1M'
    }
    
    interval_str = str(interval).upper()
    return timeframe_map.get(interval_str, interval_str)

def detect_instrument_type(pair):
    pair = str(pair).upper()
    
    forex_pairs = ['EUR', 'USD', 'GBP', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF']
    if any(currency in pair for currency in forex_pairs) and len(pair) >= 6:
        return 'forex'
    
    indices = ['GER30', 'NAS100', 'SPX500', 'US30', 'UK100', 'JPN225']
    if any(index in pair for index in indices):
        return 'indices'
    
    commodities = ['XAU', 'GOLD', 'XAG', 'SILVER', 'OIL', 'BRENT', 'WTI']
    if any(comm in pair for comm in commodities):
        return 'commodities'
    
    return 'forex'

def calculate_tp_sl(entry_price, direction, instrument_type):
    try:
        entry = float(entry_price)
        params = RISK_PARAMS.get(instrument_type, RISK_PARAMS['forex'])
        
        if instrument_type == 'forex':
            pip = params['pip_value']
            if direction == 'LONG':
                tp1 = entry + (params['tp1_pips'] * pip)
                tp2 = entry + (params['tp2_pips'] * pip)
                tp3 = entry + (params['tp3_pips'] * pip)
                sl = entry - (params['sl_pips'] * pip)
            else:
                tp1 = entry - (params['tp1_pips'] * pip)
                tp2 = entry - (params['tp2_pips'] * pip)
                tp3 = entry - (params['tp3_pips'] * pip)
                sl = entry + (params['sl_pips'] * pip)
                
        elif instrument_type == 'indices':
            point = params['point_value']
            if direction == 'LONG':
                tp1 = entry + params['tp1_points']
                tp2 = entry + params['tp2_points']
                tp3 = entry + params['tp3_points']
                sl = entry - params['sl_points']
            else:
                tp1 = entry - params['tp1_points']
                tp2 = entry - params['tp2_points']
                tp3 = entry - params['tp3_points']
                sl = entry + params['sl_points']
                
        else:
            pip = params['pip_value']
            if direction == 'LONG':
                tp1 = entry + (params['tp1_pips'] * pip)
                tp2 = entry + (params['tp2_pips'] * pip)
                tp3 = entry + (params['tp3_pips'] * pip)
                sl = entry - (params['sl_pips'] * pip)
            else:
                tp1 = entry - (params['tp1_pips'] * pip)
                tp2 = entry - (params['tp2_pips'] * pip)
                tp3 = entry - (params['tp3_pips'] * pip)
                sl = entry + (params['sl_pips'] * pip)
        
        # Format numbers
        def format_price(price):
            if instrument_type == 'forex':
                return f"{price:.5f}"
            elif instrument_type == 'indices':
                return f"{price:,.0f}"
            else:
                return f"{price:.2f}"
        
        return format_price(tp1), format_price(tp2), format_price(tp3), format_price(sl)
        
    except Exception as e:
        log_message(f"TP/SL error: {e}")
        return ('N/A', 'N/A', 'N/A', 'N/A')

def parse_tradingview_alert(data):
    """Simplified, robust parsing"""
    pair = data.get('ticker') or data.get('symbol') or 'N/A'
    price = data.get('close') or data.get('price') or 'N/A'
    action = data.get('strategy.order.action') or data.get('action') or 'N/A'
    interval = data.get('interval') or 'N/A'
    
    # Clean data
    if pair and pair != 'N/A':
        pair = str(pair).replace('.P', '').replace('.C', '').strip()
    
    # Determine if exit
    is_exit = False
    action_lower = str(action).lower()
    if 'exit' in action_lower or 'close' in action_lower:
        is_exit = True
    
    # Clean action for display
    if 'buy' in action_lower or 'long' in action_lower:
        clean_action = 'LONG'
    elif 'sell' in action_lower or 'short' in action_lower:
        clean_action = 'SHORT'
    else:
        clean_action = action.upper()
    
    return {
        'pair': pair,
        'price': price,
        'raw_price': float(price) if price != 'N/A' and price.replace('.', '', 1).isdigit() else None,
        'action': clean_action,
        'timeframe': format_timeframe(interval),
        'is_exit': is_exit,
        'detail': f"{clean_action} {'EXIT' if is_exit else 'ENTRY'}"
    }

def send_telegram_signal(signal_data):
    """Send to Telegram with error handling"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log_message("Missing Telegram credentials")
        return False
    
    try:
        if signal_data['is_exit']:
            signal = f"🔴 *EXIT SIGNAL* 🔴\n\n"
            signal += f"• *PAIR*: `{signal_data['pair']}`\n"
            signal += f"• *ACTION*: `{signal_data['detail']}`\n"
            signal += f"• *PRICE*: `{signal_data['price']}`\n"
        else:
            signal = f"🟢 *ENTRY SIGNAL* 🟢\n\n"
            signal += f"• *PAIR*: `{signal_data['pair']}`\n"
            signal += f"• *DIRECTION*: `{signal_data['detail']}`\n"
            signal += f"• *ENTRY*: `{signal_data['price']}`\n"
            
            if signal_data['raw_price']:
                instrument = detect_instrument_type(signal_data['pair'])
                tp1, tp2, tp3, sl = calculate_tp_sl(
                    signal_data['raw_price'], 
                    signal_data['action'], 
                    instrument
                )
                signal += f"• *STOP LOSS*: `{sl}`\n"
                signal += f"• *TAKE PROFIT 1*: `{tp1}`\n"
                signal += f"• *TAKE PROFIT 2*: `{tp2}`\n"
                signal += f"• *TAKE PROFIT 3*: `{tp3}`\n"
        
        signal += f"• *TIMEFRAME*: `{signal_data['timeframe']}`\n"
        signal += f"• *TIME*: `{get_current_time()}`"
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": signal,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
        
    except Exception as e:
        log_message(f"Telegram send error: {e}")
        return False

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Robust webhook handler"""
    try:
        if not request.is_json:
            return jsonify({"error": "JSON required"}), 400
        
        data = request.get_json()
        log_message(f"Received: {json.dumps(data, indent=2)[:500]}")
        
        signal_data = parse_tradingview_alert(data)
        success = send_telegram_signal(signal_data)
        
        if success:
            return jsonify({"status": "success", "signal": signal_data}), 200
        else:
            return jsonify({"status": "error", "message": "Telegram failed"}), 500
            
    except Exception as e:
        log_message(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "alive",
        "service": "QuantumScalperBot",
        "production": IS_PRODUCTION,
        "debug": DEBUG_MODE,
        "time": get_current_time()
    }), 200

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "Quantum Scalper Trading Bot",
        "endpoints": {
            "webhook": "POST /webhook",
            "health": "GET /health"
        },
        "status": "operational"
    }), 200

# PRODUCTION CONFIGURATION
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    
    # Force production mode if PORT is set (Railway/cloud)
    if os.getenv('PORT'):
        debug_mode = False
    else:
        debug_mode = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
    
    log_message(f"Starting server: port={port}, debug={debug_mode}, production={IS_PRODUCTION}")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)