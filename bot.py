import os
import re
import json
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ========= CONFIGURATION =========
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '').strip()
# =================================

class Logger:
    """Unified logging with consistent formatting"""
    @staticmethod
    def log(message):
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] {message}")

def detect_instrument_type(pair):
    """Detect instrument type with improved accuracy"""
    pair = str(pair).upper()
    
    # Indices
    indices = ['GER30', 'NAS100', 'SPX500', 'US30', 'UK100', 'JPN225', 'DXY']
    if any(index in pair for index in indices):
        return 'indices'
    
    # Commodities
    commodities = ['XAU', 'GOLD', 'XAG', 'SILVER', 'OIL', 'BRENT', 'WTI', 'XPT', 'PLATINUM']
    if any(comm in pair for comm in commodities):
        return 'commodities'
    
    # Forex (6 letters like EURUSD, or XXX/YYY format)
    if len(pair) == 6 or '/' in pair:
        return 'forex'
    
    # Crypto
    cryptos = ['BTC', 'ETH', 'XRP', 'ADA', 'SOL', 'DOT']
    if any(crypto in pair for crypto in cryptos):
        return 'crypto'
    
    return 'forex'  # Default

def format_timeframe(tf):
    """Convert TradingView timeframe to readable format"""
    if not tf or tf == 'N/A':
        return 'N/A'
    
    tf = str(tf).upper().strip()
    
    # Map of common timeframes
    tf_map = {
        '1': '1m', '2': '2m', '3': '3m', '4': '4m', '5': '5m',
        '10': '10m', '15': '15m', '30': '30m',
        '60': '1H', '120': '2H', '240': '4H', '360': '6H', '480': '8H', '720': '12H',
        'D': '1D', '1D': '1D', '1440': '1D',
        'W': '1W', '1W': '1W', '10080': '1W',
        'M': '1M', '1M': '1M'
    }
    
    # Try exact match
    if tf in tf_map:
        return tf_map[tf]
    
    # If it's a number, try to interpret as minutes
    try:
        minutes = int(tf)
        if minutes < 60:
            return f"{minutes}m"
        elif minutes == 60:
            return "1H"
        elif minutes < 1440:
            hours = minutes // 60
            return f"{hours}H"
        elif minutes == 1440:
            return "1D"
        elif minutes <= 10080:
            return "1W"
        else:
            return f"{minutes}M"
    except:
        return tf

def calculate_tp_sl(entry_price, direction, instrument_type):
    """Calculate TP/SL levels with instrument-specific logic"""
    try:
        entry = float(entry_price)
        
        # Risk parameters per instrument type
        risk_params = {
            'forex': {
                'tp1': 15, 'tp2': 30, 'tp3': 50, 'sl': 20,
                'pip_value': 0.0001, 'decimals': 5
            },
            'indices': {
                'tp1': 30, 'tp2': 60, 'tp3': 100, 'sl': 40,
                'point_value': 1.0, 'decimals': 0
            },
            'commodities': {
                'tp1': 0.50, 'tp2': 1.00, 'tp3': 1.50, 'sl': 0.75,
                'pip_value': 0.01, 'decimals': 2
            },
            'crypto': {
                'tp1': 50, 'tp2': 100, 'tp3': 200, 'sl': 75,
                'pip_value': 0.01, 'decimals': 2
            }
        }
        
        # Get params for instrument type, default to forex
        params = risk_params.get(instrument_type, risk_params['forex'])
        
        # Calculate levels based on direction
        if direction == 'LONG':
            if instrument_type == 'forex':
                tp1 = entry + (params['tp1'] * params['pip_value'])
                tp2 = entry + (params['tp2'] * params['pip_value'])
                tp3 = entry + (params['tp3'] * params['pip_value'])
                sl = entry - (params['sl'] * params['pip_value'])
            elif instrument_type == 'indices':
                tp1 = entry + params['tp1']
                tp2 = entry + params['tp2']
                tp3 = entry + params['tp3']
                sl = entry - params['sl']
            else:  # commodities/crypto
                tp1 = entry + params['tp1']
                tp2 = entry + params['tp2']
                tp3 = entry + params['tp3']
                sl = entry - params['sl']
        else:  # SHORT
            if instrument_type == 'forex':
                tp1 = entry - (params['tp1'] * params['pip_value'])
                tp2 = entry - (params['tp2'] * params['pip_value'])
                tp3 = entry - (params['tp3'] * params['pip_value'])
                sl = entry + (params['sl'] * params['pip_value'])
            elif instrument_type == 'indices':
                tp1 = entry - params['tp1']
                tp2 = entry - params['tp2']
                tp3 = entry - params['tp3']
                sl = entry + params['sl']
            else:  # commodities/crypto
                tp1 = entry - params['tp1']
                tp2 = entry - params['tp2']
                tp3 = entry - params['tp3']
                sl = entry + params['sl']
        
        # Format based on instrument type
        def format_number(num, instr_type):
            if instr_type == 'indices':
                return f"{num:,.0f}"
            elif instr_type == 'forex':
                return f"{num:.5f}"
            else:  # commodities/crypto
                return f"{num:.2f}"
        
        return (
            format_number(tp1, instrument_type),
            format_number(tp2, instrument_type),
            format_number(tp3, instrument_type),
            format_number(sl, instrument_type)
        )
        
    except Exception as e:
        Logger.log(f"TP/SL calculation error: {e}")
        return ('N/A', 'N/A', 'N/A', 'N/A')

def parse_tradingview_text(raw_text):
    """Parse TradingView's plain text format with enhanced formatting"""
    Logger.log(f"Parsing: {raw_text}")
    
    result = {
        'pair': 'N/A',
        'price': 'N/A', 
        'action': 'N/A',
        'timeframe': 'N/A',
        'is_exit': False
    }
    
    try:
        text = raw_text.strip()
        
        # Check for exit signals
        exit_keywords = ['exit', 'close', 'stop', 'tp', 'sl', 'target']
        if any(keyword in text.lower() for keyword in exit_keywords):
            result['is_exit'] = True
        
        # Format: "PAIR ACTION @ PRICE on TIMEFRAME"
        if '@' in text:
            left_part, right_part = text.split('@', 1)
            
            # Parse left: "PAIR ACTION"
            left_parts = left_part.strip().split()
            if len(left_parts) >= 2:
                result['pair'] = left_parts[0].upper()
                action_word = left_parts[1].upper()
                
                # Clean action
                action_map = {
                    'BUY': 'LONG', 'LONG': 'LONG',
                    'SELL': 'SHORT', 'SHORT': 'SHORT'
                }
                result['action'] = action_map.get(action_word, action_word)
            
            # Parse right: "PRICE on TIMEFRAME"
            if 'on' in right_part:
                price_part, timeframe_part = right_part.split('on', 1)
                result['price'] = price_part.strip()
                result['timeframe'] = timeframe_part.strip()
            else:
                result['price'] = right_part.strip()
        
        # Format price based on instrument type
        if result['price'] != 'N/A':
            try:
                price_float = float(result['price'])
                instrument = detect_instrument_type(result['pair'])
                
                if instrument == 'indices':
                    # Format indices with commas (24,453)
                    result['price'] = f"{int(price_float):,}"
                elif instrument == 'forex':
                    # Format forex with 5 decimals (1.09876)
                    result['price'] = f"{price_float:.5f}"
                elif instrument == 'commodities':
                    # Format commodities with 2 decimals (74.70)
                    result['price'] = f"{price_float:.2f}"
                else:  # crypto or other
                    result['price'] = f"{price_float:.2f}"
                    
            except ValueError:
                pass
        
        # Format timeframe
        result['timeframe'] = format_timeframe(result['timeframe'])
        
        Logger.log(f"Parsed: {result['pair']} {result['action']} @ {result['price']} TF:{result['timeframe']}")
        return result
        
    except Exception as e:
        Logger.log(f"Parse error: {e}")
        return result

@app.route('/webhook', methods=['POST', 'GET'])
def handle_webhook():
    """Handle TradingView webhooks with optimized formatting"""
    Logger.log("=" * 50)
    Logger.log("WEBHOOK RECEIVED")
    
    # GET requests (for testing)
    if request.method == 'GET':
        return jsonify({"status": "ready", "method": "GET"}), 200
    
    # POST requests
    try:
        # Get raw data
        raw_data = request.get_data(as_text=True)
        content_type = request.content_type
        Logger.log(f"Content-Type: {content_type}")
        Logger.log(f"Data: {raw_data[:100]}..." if len(raw_data) > 100 else f"Data: {raw_data}")
        
        # Parse data
        parsed_data = {}
        if 'application/json' in str(content_type):
            try:
                parsed_data = request.get_json(force=True)
                Logger.log("Parsed as JSON")
            except:
                parsed_data = parse_tradingview_text(raw_data)
                Logger.log("Fell back to text parsing")
        else:
            parsed_data = parse_tradingview_text(raw_data)
            Logger.log("Parsed as plain text")
        
        # Extract fields
        pair = parsed_data.get('pair', 'N/A')
        price = parsed_data.get('price', 'N/A')
        action = parsed_data.get('action', 'N/A')
        timeframe = parsed_data.get('timeframe', 'N/A')
        is_exit = parsed_data.get('is_exit', False)
        
        Logger.log(f"Extracted: {pair} | {action} | {price} | TF:{timeframe} | Exit:{is_exit}")
        
        # Validate data
        if pair == 'N/A' or action == 'N/A':
            Logger.log("Invalid data - missing pair or action")
            return jsonify({"status": "invalid_data"}), 200
        
        # Send to Telegram
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            # Format signal based on type
            if is_exit:
                signal = f"🔴 *EXIT SIGNAL* 🔴\n\n"
                signal += f"• *PAIR*: `{pair}`\n"
                signal += f"• *ACTION*: `{action} EXIT`\n"
                signal += f"• *PRICE*: `{price}`\n"
            else:
                # Entry signal
                if action == 'LONG':
                    signal = f"🟢 *ENTRY SIGNAL* 🟢\n\n"
                else:  # SHORT
                    signal = f"🔵 *ENTRY SIGNAL* 🔵\n\n"
                
                signal += f"• *PAIR*: `{pair}`\n"
                signal += f"• *DIRECTION*: `{action}`\n"
                signal += f"• *ENTRY*: `{price}`\n"
                
                # Calculate TP/SL for entries only
                try:
                    price_clean = float(price.replace(',', ''))
                    instrument = detect_instrument_type(pair)
                    tp1, tp2, tp3, sl = calculate_tp_sl(price_clean, action, instrument)
                    
                    signal += f"• *STOP LOSS*: `{sl}`\n"
                    signal += f"• *TAKE PROFIT 1*: `{tp1}`\n"
                    signal += f"• *TAKE PROFIT 2*: `{tp2}`\n"
                    signal += f"• *TAKE PROFIT 3*: `{tp3}`\n"
                except Exception as e:
                    Logger.log(f"TP/SL skipped: {e}")
            
            # Add timeframe and time
            if timeframe != 'N/A':
                signal += f"• *TIMEFRAME*: `{timeframe}`\n"
            
            signal += f"• *TIME*: `{datetime.now(timezone.utc).strftime('%H:%M UTC')}`"
            
            # Send to Telegram
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": signal,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
                "disable_notification": False
            }
            
            Logger.log("Sending to Telegram...")
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                Logger.log("✓ Signal sent successfully")
                return jsonify({
                    "status": "success",
                    "signal_type": "exit" if is_exit else "entry",
                    "pair": pair,
                    "action": action,
                    "price": price
                }), 200
            else:
                Logger.log(f"✗ Telegram error: {response.status_code}")
                return jsonify({"status": "telegram_error"}), 200
        else:
            Logger.log("✗ Missing Telegram credentials")
            return jsonify({"status": "no_credentials"}), 200
            
    except Exception as e:
        Logger.log(f"✗ Webhook error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 200
    
    finally:
        Logger.log("=" * 50)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "alive",
        "service": "QuantumScalperBot",
        "version": "5.0",
        "telegram_configured": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        "time": datetime.now(timezone.utc).strftime('%H:%M UTC')
    }), 200

@app.route('/test', methods=['GET', 'POST'])
def test():
    """Test endpoint with sample data"""
    if request.method == 'POST':
        data = request.get_json() or {}
        raw_text = data.get('text', 'EURUSD buy @ 1.09876 on 15')
        parsed = parse_tradingview_text(raw_text)
        return jsonify({"parsed": parsed}), 200
    
    return jsonify({
        "message": "Quantum Scalper Trading Bot",
        "status": "operational",
        "endpoints": {
            "POST /webhook": "TradingView alerts",
            "GET /health": "Health check",
            "POST /test": "Test parsing"
        }
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    Logger.log(f"Starting Quantum Scalper Bot v5.0 on port {port}")
    Logger.log(f"Telegram configured: {bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)}")
    app.run(host='0.0.0.0', port=port, debug=False)