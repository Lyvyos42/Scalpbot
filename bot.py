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

def log(msg):
    """Log to Railway logs"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def detect_instrument_type(pair):
    """Detect instrument type"""
    pair = str(pair).upper()
    if any(idx in pair for idx in ['GER30', 'NAS100', 'SPX500', 'US30', 'UK100']):
        return 'indices'
    elif any(comm in pair for comm in ['XAU', 'GOLD', 'XAG', 'SILVER', 'OIL']):
        return 'commodities'
    else:
        return 'forex'

def calculate_tp_sl(entry_price, direction, instrument_type):
    """Calculate TP/SL levels"""
    try:
        entry = float(entry_price)
        
        # Risk parameters
        if instrument_type == 'forex':
            pip = 0.0001
            if direction == 'LONG':
                tp1 = entry + (15 * pip)
                tp2 = entry + (30 * pip)
                tp3 = entry + (50 * pip)
                sl = entry - (20 * pip)
            else:
                tp1 = entry - (15 * pip)
                tp2 = entry - (30 * pip)
                tp3 = entry - (50 * pip)
                sl = entry + (20 * pip)
                
        elif instrument_type == 'indices':
            if direction == 'LONG':
                tp1 = entry + 30
                tp2 = entry + 60
                tp3 = entry + 100
                sl = entry - 40
            else:
                tp1 = entry - 30
                tp2 = entry - 60
                tp3 = entry - 100
                sl = entry + 40
                
        else:  # commodities
            pip = 0.01
            if direction == 'LONG':
                tp1 = entry + (50 * pip)
                tp2 = entry + (100 * pip)
                tp3 = entry + (150 * pip)
                sl = entry - (75 * pip)
            else:
                tp1 = entry - (50 * pip)
                tp2 = entry - (100 * pip)
                tp3 = entry - (150 * pip)
                sl = entry + (75 * pip)
        
        # Format based on instrument
        if instrument_type == 'forex':
            return f"{tp1:.5f}", f"{tp2:.5f}", f"{tp3:.5f}", f"{sl:.5f}"
        elif instrument_type == 'indices':
            return f"{tp1:,.0f}", f"{tp2:,.0f}", f"{tp3:,.0f}", f"{sl:,.0f}"
        else:
            return f"{tp1:.2f}", f"{tp2:.2f}", f"{tp3:.2f}", f"{sl:.2f}"
        
    except Exception as e:
        log(f"TP/SL calculation error: {e}")
        return 'N/A', 'N/A', 'N/A', 'N/A'

def parse_tradingview_text(raw_text):
    """Parse TradingView's plain text format"""
    log(f"Parsing text: {raw_text}")
    
    result = {
        'pair': 'N/A',
        'price': 'N/A', 
        'action': 'N/A',
        'timeframe': 'N/A'
    }
    
    try:
        text = raw_text.strip()
        
        # Format: "PAIR ACTION @ PRICE on TIMEFRAME"
        if '@' in text:
            left_part, right_part = text.split('@', 1)
            
            # Parse left: "PAIR ACTION"
            left_parts = left_part.strip().split()
            if len(left_parts) >= 2:
                result['pair'] = left_parts[0].upper()
                result['action'] = left_parts[1].upper()
            
            # Parse right: "PRICE on TIMEFRAME"
            if 'on' in right_part:
                price_part, timeframe_part = right_part.split('on', 1)
                result['price'] = price_part.strip()
                result['timeframe'] = timeframe_part.strip()
            else:
                result['price'] = right_part.strip()
                
        # Clean action
        action_map = {'BUY': 'LONG', 'SELL': 'SHORT'}
        if result['action'] in action_map:
            result['action'] = action_map[result['action']]
        
        # Format price
        try:
            price_float = float(result['price'])
            if detect_instrument_type(result['pair']) == 'indices':
                result['price'] = f"{int(price_float):,}"
            elif len(result['pair']) == 6:  # Forex
                result['price'] = f"{price_float:.5f}"
        except:
            pass
            
        log(f"Parsed result: {result}")
        return result
        
    except Exception as e:
        log(f"Text parsing error: {e}")
        return result

@app.route('/webhook', methods=['POST', 'GET'])
def handle_webhook():
    """Handle TradingView webhooks"""
    log("=== WEBHOOK CALLED ===")
    
    # Log request details
    log(f"Method: {request.method}")
    log(f"Content-Type: {request.content_type}")
    
    # GET requests
    if request.method == 'GET':
        return jsonify({"status": "ready"}), 200
    
    # POST requests
    try:
        # Get raw data
        raw_data = request.get_data(as_text=True)
        log(f"Raw data: {raw_data}")
        
        # Parse data
        parsed_data = {}
        if 'application/json' in str(request.content_type):
            try:
                parsed_data = request.get_json(force=True)
            except:
                parsed_data = parse_tradingview_text(raw_data)
        else:
            parsed_data = parse_tradingview_text(raw_data)
        
        # Extract fields
        pair = parsed_data.get('pair', 'N/A')
        price = parsed_data.get('price', 'N/A')
        action = parsed_data.get('action', 'N/A')
        timeframe = parsed_data.get('timeframe', 'N/A')
        
        log(f"Extracted: {pair} | {price} | {action} | {timeframe}")
        
        # Send to Telegram
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID and pair != 'N/A':
            # Format signal
            if action in ['LONG', 'BUY']:
                signal = f"🟢 *ENTRY SIGNAL* 🟢\n\n"
                signal += f"• *PAIR*: `{pair}`\n"
                signal += f"• *DIRECTION*: `LONG`\n"
                signal += f"• *ENTRY*: `{price}`\n"
                
                # Calculate TP/SL
                try:
                    price_clean = float(price.replace(',', ''))
                    instrument = detect_instrument_type(pair)
                    tp1, tp2, tp3, sl = calculate_tp_sl(price_clean, 'LONG', instrument)
                    
                    signal += f"• *STOP LOSS*: `{sl}`\n"
                    signal += f"• *TAKE PROFIT 1*: `{tp1}`\n"
                    signal += f"• *TAKE PROFIT 2*: `{tp2}`\n"
                    signal += f"• *TAKE PROFIT 3*: `{tp3}`\n"
                except:
                    pass
                    
            elif action in ['SHORT', 'SELL']:
                signal = f"🔵 *ENTRY SIGNAL* 🔵\n\n"
                signal += f"• *PAIR*: `{pair}`\n"
                signal += f"• *DIRECTION*: `SHORT`\n"
                signal += f"• *ENTRY*: `{price}`\n"
                
                # Calculate TP/SL
                try:
                    price_clean = float(price.replace(',', ''))
                    instrument = detect_instrument_type(pair)
                    tp1, tp2, tp3, sl = calculate_tp_sl(price_clean, 'SHORT', instrument)
                    
                    signal += f"• *STOP LOSS*: `{sl}`\n"
                    signal += f"• *TAKE PROFIT 1*: `{tp1}`\n"
                    signal += f"• *TAKE PROFIT 2*: `{tp2}`\n"
                    signal += f"• *TAKE PROFIT 3*: `{tp3}`\n"
                except:
                    pass
            else:
                signal = f"⚠️ *SIGNAL* ⚠️\n\n"
                signal += f"• *PAIR*: `{pair}`\n"
                signal += f"• *ACTION*: `{action}`\n"
                signal += f"• *PRICE*: `{price}`\n"
            
            # Add timeframe and time
            if timeframe != 'N/A':
                signal += f"• *TIMEFRAME*: `{timeframe}`\n"
            signal += f"• *TIME*: `{datetime.now(timezone.utc).strftime('%H:%M UTC')}`"
            
            # Send to Telegram
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": signal,
                "parse_mode": "Markdown"
            }
            
            log(f"Sending to Telegram")
            response = requests.post(url, json=payload, timeout=10)
            log(f"Telegram response: {response.status_code}")
            
            if response.status_code == 200:
                log("Signal sent successfully")
                return jsonify({"status": "success"}), 200
            else:
                log(f"Telegram error: {response.text}")
                return jsonify({"status": "telegram_error"}), 200
        else:
            log("Missing credentials or invalid data")
            return jsonify({"status": "invalid_data"}), 200
            
    except Exception as e:
        log(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "alive",
        "telegram_configured": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)
    }), 200

@app.route('/test', methods=['POST'])
def test():
    """Test endpoint with TradingView format"""
    test_data = "USDCAD buy @ 1.36890 on 5"
    parsed = parse_tradingview_text(test_data)
    return jsonify({
        "test": test_data,
        "parsed": parsed
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    log(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)