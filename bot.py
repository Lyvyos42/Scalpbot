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

# Risk Parameters (adjust these based on your strategy)
RISK_PARAMS = {
    'forex': {
        'tp1_pips': 15,    # Take Profit 1 in pips
        'tp2_pips': 30,    # Take Profit 2 in pips  
        'tp3_pips': 50,    # Take Profit 3 in pips
        'sl_pips': 20,     # Stop Loss in pips
        'pip_value': 0.0001  # 1 pip for most forex
    },
    'indices': {
        'tp1_points': 30,   # GER30, NAS100, SPX500
        'tp2_points': 60,
        'tp3_points': 100,
        'sl_points': 40,
        'point_value': 1.0
    },
    'commodities': {
        'tp1_pips': 50,     # Gold, Silver, Oil
        'tp2_pips': 100,
        'tp3_pips': 150,
        'sl_pips': 75,
        'pip_value': 0.01   # Gold/Silver pip = $0.01
    }
}
# =================================

def get_current_time():
    """Get current UTC time in HH:MM format"""
    return datetime.now(timezone.utc).strftime('%H:%M UTC')

def format_timeframe(interval):
    """
    Convert TradingView interval to readable format.
    TradingView sends: 1, 5, 15, 30, 60, 120, 240, 360, 480, 720, 1440, "D", "W", "M"
    """
    if not interval:
        return "N/A"
    
    interval_str = str(interval).upper()
    
    timeframe_map = {
        '1': '1m', '5': '5m', '15': '15m', '30': '30m',
        '60': '1H', '120': '2H', '240': '4H', '360': '6H',
        '480': '8H', '720': '12H', '1440': '1D', 'D': '1D',
        'W': '1W', 'M': '1M', '365': '1D', '10080': '1W'
    }
    
    # Check for exact matches
    if interval_str in timeframe_map:
        return timeframe_map[interval_str]
    
    # Check if it's a number of minutes
    try:
        minutes = int(interval_str)
        if minutes < 60:
            return f"{minutes}m"
        elif minutes == 60:
            return "1H"
        elif minutes < 1440:
            return f"{minutes//60}H"
        elif minutes == 1440:
            return "1D"
        else:
            days = minutes // 1440
            return f"{days}D"
    except:
        return interval_str  # Return as-is if unknown

def detect_instrument_type(pair):
    """Detect instrument type based on pair name"""
    pair = str(pair).upper()
    
    # Forex pairs (6 letters or XXX/YYY format)
    forex_pairs = ['EUR', 'USD', 'GBP', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF']
    if any(currency in pair for currency in forex_pairs) and len(pair) >= 6:
        return 'forex'
    
    # Indices
    indices = ['GER30', 'NAS100', 'SPX500', 'US30', 'UK100', 'JPN225']
    if any(index in pair for index in indices):
        return 'indices'
    
    # Commodities
    commodities = ['XAU', 'GOLD', 'XAG', 'SILVER', 'OIL', 'BRENT', 'WTI']
    if any(comm in pair for comm in commodities):
        return 'commodities'
    
    # Default to forex
    return 'forex'

def calculate_tp_sl(entry_price, direction, instrument_type):
    """Calculate Take Profit and Stop Loss levels"""
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
            else:  # SHORT
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
            else:  # SHORT
                tp1 = entry - params['tp1_points']
                tp2 = entry - params['tp2_points']
                tp3 = entry - params['tp3_points']
                sl = entry + params['sl_points']
                
        else:  # commodities
            pip = params['pip_value']
            if direction == 'LONG':
                tp1 = entry + (params['tp1_pips'] * pip)
                tp2 = entry + (params['tp2_pips'] * pip)
                tp3 = entry + (params['tp3_pips'] * pip)
                sl = entry - (params['sl_pips'] * pip)
            else:  # SHORT
                tp1 = entry - (params['tp1_pips'] * pip)
                tp2 = entry - (params['tp2_pips'] * pip)
                tp3 = entry - (params['tp3_pips'] * pip)
                sl = entry + (params['sl_pips'] * pip)
        
        # Format numbers appropriately
        def format_price(price):
            if instrument_type == 'forex':
                return f"{price:.5f}"
            elif instrument_type == 'indices':
                return f"{price:,.0f}"
            else:  # commodities
                if price > 100:  # Gold
                    return f"{price:.2f}"
                else:  # Silver, Oil
                    return f"{price:.3f}"
        
        return (
            format_price(tp1),
            format_price(tp2), 
            format_price(tp3),
            format_price(sl)
        )
        
    except Exception as e:
        if DEBUG_MODE:
            print(f"TP/SL calculation error: {e}")
        return ('N/A', 'N/A', 'N/A', 'N/A')

def parse_malformed_string(message):
    """Parse TradingView's malformed strings"""
    result = {}
    try:
        content = message.strip('[]')
        pattern = r'"([^"]+)"\s*:\s*"?([^",}\]]+)"?'
        matches = re.findall(pattern, content)
        
        for key, value in matches:
            key = key.strip()
            value = value.strip().replace('"', '').replace("'", "")
            result[key] = value
    except Exception as e:
        if DEBUG_MODE:
            print(f"Failed to parse malformed string: {e}")
    
    return result

def determine_signal_type(action, message, data):
    """Determine if signal is ENTRY or EXIT"""
    action_str = str(action).lower()
    message_str = str(message).lower()
    
    # Check for exit indicators
    exit_keywords = ['exit', 'close', 'flat', 'stop', 'target', 'tp', 'sl']
    
    # Priority 1: Position size
    if 'position_size' in data:
        try:
            pos_size = float(data.get('position_size', 1))
            if pos_size == 0:
                return True, "EXIT", "POSITION CLOSED"
        except:
            pass
    
    # Priority 2: Action contains exit
    if any(keyword in action_str for keyword in exit_keywords):
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
    """Extract signal from TradingView webhook"""
    pair = 'N/A'
    price = 'N/A'
    raw_price = None
    action = 'N/A'
    timeframe = 'N/A'
    message = data.get('message', '')
    
    # ===== EXTRACT TIMEFRAME =====
    # TradingView sends interval in multiple possible fields
    interval = data.get('interval') or data.get('strategy.interval') or data.get('timeframe')
    if interval:
        timeframe = format_timeframe(interval)
    
    # ===== EXTRACT PAIR =====
    pair = data.get('ticker') or data.get('symbol') or data.get('pair')
    if not pair or pair == 'N/A':
        if message and message.startswith('['):
            parsed = parse_malformed_string(message)
            pair = parsed.get('pair', parsed.get('ticker'))
    
    if not pair or pair == 'N/A':
        if message:
            pair_match = re.search(r'([A-Z]{6}|[A-Z]{3}/[A-Z]{3}|[A-Z]{5,6})', message)
            if pair_match:
                pair = pair_match.group(1)
    
    # ===== EXTRACT PRICE =====
    price_str = data.get('close') or data.get('price') or data.get('strategy.order.price')
    if not price_str or price_str == 'N/A':
        if message and message.startswith('['):
            parsed = parse_malformed_string(message)
            price_str = parsed.get('price')
    
    if not price_str or price_str == 'N/A':
        if message:
            price_match = re.search(r'([0-9]+\.?[0-9]*)', str(price_str) or message)
            if price_match:
                price_str = price_match.group(1)
    
    # Convert to float for calculations
    try:
        raw_price = float(price_str)
        # Format for display
        instrument_type = detect_instrument_type(pair)
        if instrument_type == 'indices':
            price = f"{raw_price:,.0f}"
        elif instrument_type == 'forex':
            price = f"{raw_price:.5f}"
        else:
            price = f"{raw_price:.2f}"
    except:
        price = price_str or 'N/A'
        raw_price = None
    
    # ===== EXTRACT ACTION =====
    action = data.get('strategy.order.action') or data.get('action')
    if not action or action == 'N/A':
        if message and message.startswith('['):
            parsed = parse_malformed_string(message)
            action = parsed.get('action')
    
    # Clean pair
    if pair:
        pair = str(pair).replace('.P', '').replace('.C', '').replace(' ', '')
    
    # Determine signal type
    is_exit, clean_action, detail_action = determine_signal_type(action, message, data)
    
    return {
        'pair': pair or 'N/A',
        'price': price,
        'raw_price': raw_price,
        'action': clean_action,
        'detail': detail_action,
        'timeframe': timeframe,
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
        signal += f"• *PRICE*: `{signal_data['price']}`\n"
        signal += f"• *TIMEFRAME*: `{signal_data['timeframe']}`\n"
        signal += f"• *TIME*: `{get_current_time()}`"
    
    else:
        # ENTRY SIGNAL - Add TP/SL levels
        emoji = "🟢" if "LONG" in signal_data['detail'] else "🔵"
        signal = f"{emoji} *ENTRY SIGNAL* {emoji}\n\n"
        signal += f"• *PAIR*: `{signal_data['pair']}`\n"
        signal += f"• *DIRECTION*: `{signal_data['detail']}`\n"
        signal += f"• *ENTRY PRICE*: `{signal_data['price']}`\n"
        signal += f"• *TIMEFRAME*: `{signal_data['timeframe']}`\n"
        
        # Calculate TP/SL if we have raw price
        if signal_data['raw_price']:
            instrument_type = detect_instrument_type(signal_data['pair'])
            tp1, tp2, tp3, sl = calculate_tp_sl(
                signal_data['raw_price'], 
                signal_data['action'], 
                instrument_type
            )
            
            signal += f"• *STOP LOSS*: `{sl}`\n"
            signal += f"• *TAKE PROFIT 1*: `{tp1}`\n"
            signal += f"• *TAKE PROFIT 2*: `{tp2}`\n"
            signal += f"• *TAKE PROFIT 3*: `{tp3}`\n"
        
        signal += f"• *TIME*: `{get_current_time()}`"
    
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
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
        
        if DEBUG_MODE:
            print("=" * 50)
            print("INCOMING WEBHOOK DATA:")
            print(json.dumps(data, indent=2))
            print("=" * 50)
        
        signal_data = parse_tradingview_alert(data)
        
        if DEBUG_MODE:
            print(f"PARSED SIGNAL: {signal_data}")
        
        success = send_telegram_signal(signal_data)
        
        if success:
            response = {
                "status": "success",
                "signal_type": "exit" if signal_data['is_exit'] else "entry",
                "pair": signal_data['pair'],
                "action": signal_data['detail'],
                "price": signal_data['price'],
                "timeframe": signal_data['timeframe']
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
        "version": "4.0",
        "timestamp": get_current_time()
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=DEBUG_MODE)