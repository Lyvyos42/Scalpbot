import os
import json
import traceback
from datetime import datetime
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Configuration - ENSURE THESE ARE SET IN RAILWAY
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '').strip()

def log(msg):
    """Log to Railway logs"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

@app.route('/webhook', methods=['POST', 'GET'])
def handle_webhook():
    """Handle TradingView webhooks"""
    log("=== WEBHOOK CALLED ===")
    
    # Log headers for debugging
    log(f"Method: {request.method}")
    log(f"Content-Type: {request.content_type}")
    log(f"Content-Length: {request.content_length}")
    
    # GET requests (TradingView sometimes sends GET for testing)
    if request.method == 'GET':
        log("GET request - returning OK")
        return jsonify({"status": "ready", "method": "GET"}), 200
    
    # POST requests
    raw_data = ""
    try:
        # Get raw data
        if request.data:
            raw_data = request.get_data(as_text=True)
            log(f"Raw data ({len(raw_data)} chars): {raw_data[:500]}...")
        else:
            log("No data in request")
            return jsonify({"status": "no_data"}), 200
        
        # Parse JSON - TradingView might send different formats
        data = {}
        
        # Method 1: Try standard JSON parse
        try:
            data = request.get_json(force=True)  # Force even if wrong content-type
            log("Parsed with get_json(force=True)")
        except:
            # Method 2: Try json.loads
            try:
                data = json.loads(raw_data)
                log("Parsed with json.loads")
            except json.JSONDecodeError:
                # Method 3: Try to extract from malformed format
                if 'alert_message' in raw_data or 'ticker' in raw_data:
                    # Try to extract key-value pairs
                    import re
                    pairs = re.findall(r'(\w+)\s*[:=]\s*([^,\s}]+)', raw_data)
                    data = {k: v.strip('"\'') for k, v in pairs}
                    log(f"Extracted with regex: {data}")
        
        log(f"Parsed data: {data}")
        
        # Extract information
        pair = (data.get('ticker') or data.get('symbol') or 
                data.get('pair') or data.get('exchange') or 'N/A')
        price = (data.get('close') or data.get('price') or 
                 data.get('strategy.order.price') or 'N/A')
        action = (data.get('strategy.order.action') or data.get('action') or 
                  data.get('side') or 'N/A')
        
        # Clean up
        pair = str(pair).replace('.P', '').replace('.C', '').strip()
        
        log(f"Extracted - Pair: {pair}, Price: {price}, Action: {action}")
        
        # Send to Telegram if credentials exist
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            # Format signal
            if 'exit' in str(action).lower() or 'close' in str(action).lower():
                signal = f"🔴 EXIT SIGNAL\nPair: {pair}\nPrice: {price}\nAction: {action}"
            else:
                signal = f"🟢 ENTRY SIGNAL\nPair: {pair}\nPrice: {price}\nAction: {action}"
            
            # Add timestamp
            signal += f"\nTime: {datetime.utcnow().strftime('%H:%M UTC')}"
            
            # Send to Telegram
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": signal,
                "parse_mode": "Markdown"
            }
            
            log(f"Sending to Telegram: {signal}")
            
            try:
                response = requests.post(url, json=payload, timeout=10)
                log(f"Telegram response: {response.status_code}")
                
                if response.status_code == 200:
                    log("Signal sent successfully")
                    return jsonify({"status": "success", "sent": True}), 200
                else:
                    log(f"Telegram error: {response.text}")
                    # Still return 200 so TradingView doesn't retry
                    return jsonify({"status": "telegram_failed"}), 200
                    
            except Exception as e:
                log(f"Telegram send exception: {str(e)}")
                return jsonify({"status": "send_exception"}), 200
        else:
            log("Missing Telegram credentials")
            return jsonify({"status": "no_credentials"}), 200
            
    except Exception as e:
        log(f"UNEXPECTED ERROR: {str(e)}")
        log(traceback.format_exc())
        # Always return 200 to prevent TradingView retries
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "alive",
        "telegram_configured": bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
        "time": datetime.utcnow().isoformat()
    }), 200

@app.route('/test', methods=['GET', 'POST'])
def test():
    """Test endpoint - send a test signal"""
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            signal = "✅ BOT TEST SIGNAL ✅\nThis is a test from your trading bot."
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": signal,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload)
            return jsonify({"status": "test_sent", "response": response.status_code}), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "no_credentials"}), 400

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    log(f"Starting server on port {port}, debug={debug}")
    app.run(host='0.0.0.0', port=port, debug=debug)