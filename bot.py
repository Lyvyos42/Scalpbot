import time
import logging
import math
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MarketType(Enum):
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    COMMODITIES = "COMMODITIES"

class TimeFrame(Enum):
    M1 = "1M"
    M3 = "3M"
    M5 = "5M"
    M15 = "15M"
    M30 = "30M"
    H1 = "1H"
    H4 = "4H"
    D1 = "1D"

@dataclass
class MarketProfile:
    """Market-specific volatility and characteristics"""
    symbol: str
    market_type: MarketType
    spread: float
    pip_value: float = 10.0

class TelegramNotifier:
    """Handle Telegram notifications"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}/"
        
    def send_message(self, text: str, parse_mode: str = "HTML", disable_notification: bool = False):
        """Send message to Telegram"""
        try:
            url = f"{self.base_url}sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_notification": disable_notification
            }
            
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram message sent")
                return True
            else:
                logger.error(f"Failed to send Telegram message: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    def send_trade_signal(self, trade_plan: Dict):
        """Send trade signal to Telegram"""
        try:
            symbol = trade_plan['symbol']
            direction = trade_plan['direction']
            entry = trade_plan['entry_price']
            sl = trade_plan['stop_loss']
            tp1 = trade_plan['take_profits'][0]['price']
            tp2 = trade_plan['take_profits'][1]['price']
            tp3 = trade_plan['take_profits'][2]['price']
            timeframe = trade_plan['timeframe']
            
            direction_emoji = "🟢" if direction == "LONG" else "🔴"
            direction_text = "BUY/LONG" if direction == "LONG" else "SELL/SHORT"
            
            message = f"""
<b>{direction_emoji} TRADE SIGNAL {direction_emoji}</b>
━━━━━━━━━━━━━━━━━━━━

<b>📍 Pair:</b> <code>{symbol}</code>
<b>📊 Direction:</b> <b>{direction_text}</b>
<b>⏰ Timeframe:</b> {timeframe}

<b>💰 Entry Price:</b> <code>{entry:.5f}</code>
<b>🛑 Stop Loss:</b> <code>{sl:.5f}</code>
<b>🎯 Take Profit 1:</b> <code>{tp1:.5f}</code>
<b>🎯 Take Profit 2:</b> <code>{tp2:.5f}</code>
<b>🎯 Take Profit 3:</b> <code>{tp3:.5f}</code>

<b>⏱️ Signal Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

━━━━━━━━━━━━━━━━━━━━
<b>#TradeSignal #{symbol.replace('/', '')} #{direction}</b>
"""
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Error creating trade signal message: {e}")
            return False

class DynamicRiskManager:
    """Dynamic risk management across timeframes and markets"""
    
    def __init__(self):
        # Base stop loss in pips for each timeframe
        self.timeframe_stops = {
            TimeFrame.M1: 2,   TimeFrame.M3: 3,   TimeFrame.M5: 5,
            TimeFrame.M15: 8,  TimeFrame.M30: 12, TimeFrame.H1: 15,
            TimeFrame.H4: 25,  TimeFrame.D1: 40
        }
        
        # Risk/Reward ratios for each timeframe
        self.timeframe_rr_ratios = {
            TimeFrame.M1: [1.0, 1.5, 2.0],   TimeFrame.M3: [1.0, 2.0, 3.0],
            TimeFrame.M5: [1.5, 2.5, 3.5],   TimeFrame.M15: [2.0, 3.0, 4.0],
            TimeFrame.M30: [2.0, 3.0, 4.0],  TimeFrame.H1: [2.5, 3.5, 5.0],
            TimeFrame.H4: [3.0, 4.0, 6.0],   TimeFrame.D1: [3.0, 5.0, 8.0]
        }
    
    def calculate_pip_size(self, symbol: str) -> float:
        """Calculate pip size based on symbol"""
        symbol_upper = symbol.upper()
        
        if "JPY" in symbol_upper:
            return 0.01
        elif "XAU" in symbol_upper or "XAG" in symbol_upper:
            return 0.01
        elif any(crypto in symbol_upper for crypto in ["BTC", "ETH", "SOL"]):
            return 0.1  # Cryptos use smaller pip size
        else:
            return 0.0001  # Standard forex pairs
    
    def calculate_stop_loss(self, 
                           symbol: str,
                           entry_price: float,
                           direction: str,
                           timeframe: TimeFrame,
                           market_type: MarketType) -> Dict:
        """Calculate dynamic stop loss - FIXED VERSION"""
        base_stop = self.timeframe_stops.get(timeframe, 10)
        
        # Set multiplier based on market type
        if market_type == MarketType.CRYPTO:
            multiplier = 2.0
        elif market_type == MarketType.COMMODITIES:
            multiplier = 1.5
        else:  # FOREX
            multiplier = 1.0
            
        stop_pips = base_stop * multiplier
        
        pip_size = self.calculate_pip_size(symbol)
        stop_distance = stop_pips * pip_size
        
        # Calculate stop price
        if direction.upper() == "SHORT":
            stop_price = entry_price + stop_distance
        else:
            stop_price = entry_price - stop_distance
        
        return {
            "stop_loss": stop_price,
            "stop_pips": stop_pips,
            "stop_distance": stop_distance
        }
    
    def calculate_take_profits(self,
                              entry_price: float,
                              stop_pips: float,
                              direction: str,
                              timeframe: TimeFrame,
                              symbol: str) -> List[Dict]:
        """Calculate three take-profit levels"""
        rr_ratios = self.timeframe_rr_ratios.get(timeframe, [1.0, 2.0, 3.0])
        pip_size = self.calculate_pip_size(symbol)
        
        tp_levels = []
        for i, ratio in enumerate(rr_ratios):
            tp_pips = stop_pips * ratio
            tp_distance = tp_pips * pip_size
            
            if direction.upper() == "SHORT":
                tp_price = entry_price - tp_distance
            else:
                tp_price = entry_price + tp_distance
            
            tp_levels.append({
                "level": i + 1,
                "price": round(tp_price, 5),
                "pips": round(tp_pips, 1),
                "rr_ratio": ratio,
                "distance": tp_distance
            })
        
        return tp_levels
    
    def calculate_realistic_pnl(self, pips: float, position_size: float, pip_value: float) -> float:
        """Calculate realistic P&L without crazy numbers"""
        # Max P&L is 10x risk (1000%)
        max_pnl_multiplier = 10.0
        
        # Calculate base P&L
        base_pnl = pips * position_size * pip_value
        
        # Apply reasonable limits
        if abs(base_pnl) > 1000000:  # If over 1 million
            return 1000000 if base_pnl > 0 else -1000000
        elif abs(base_pnl) < 0.01:  # If under 1 cent
            return 0.0
            
        return round(base_pnl, 2)

class TradingBot:
    """Trading bot that only sends signals to Telegram"""
    
    def __init__(self, telegram_token: str, telegram_chat_id: str):
        self.risk_manager = DynamicRiskManager()
        self.market_profiles = self.initialize_market_profiles()
        
        # Initialize Telegram notifier
        self.telegram = TelegramNotifier(telegram_token, telegram_chat_id)
        
        # Test connection
        if self.telegram.send_message(
            "🤖 QuantumScalperPro Trading Bot Started!\n"
            "✅ Ready to receive signals...\n"
            f"⏰ Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        ):
            logger.info("✅ Telegram notifications ENABLED")
        else:
            logger.error("❌ Failed to initialize Telegram")
            sys.exit(1)
    
    def initialize_market_profiles(self) -> Dict[str, MarketProfile]:
        """Initialize market profiles"""
        return {
            # Forex
            "EURUSD": MarketProfile("EURUSD", MarketType.FOREX, 0.0001, 10.0),
            "GBPUSD": MarketProfile("GBPUSD", MarketType.FOREX, 0.00012, 10.0),
            "USDJPY": MarketProfile("USDJPY", MarketType.FOREX, 0.01, 9.27),
            "EURCAD": MarketProfile("EURCAD", MarketType.FOREX, 0.00015, 7.5),
            "AUDUSD": MarketProfile("AUDUSD", MarketType.FOREX, 0.0001, 10.0),
            "NZDUSD": MarketProfile("NZDUSD", MarketType.FOREX, 0.00012, 10.0),
            
            # Cryptocurrencies
            "BTCUSD": MarketProfile("BTCUSD", MarketType.CRYPTO, 5.0, 1.0),
            "ETHUSD": MarketProfile("ETHUSD", MarketType.CRYPTO, 0.5, 1.0),
            "SOLUSD": MarketProfile("SOLUSD", MarketType.CRYPTO, 0.1, 1.0),
            "XRPUSD": MarketProfile("XRPUSD", MarketType.CRYPTO, 0.0001, 1.0),
            
            # Commodities
            "XAUUSD": MarketProfile("XAUUSD", MarketType.COMMODITIES, 0.5, 1.0),
            "XAGUSD": MarketProfile("XAGUSD", MarketType.COMMODITIES, 0.01, 1.0),
        }
    
    def get_market_profile(self, symbol: str) -> MarketProfile:
        """Get market profile for symbol"""
        symbol_clean = symbol.upper().replace("/", "")
        
        if symbol_clean in self.market_profiles:
            return self.market_profiles[symbol_clean]
        
        # Auto-detect for unknown symbols
        if any(crypto in symbol_clean for crypto in ["BTC", "ETH", "SOL", "XRP"]):
            return MarketProfile(symbol_clean, MarketType.CRYPTO, 1.0, 1.0)
        elif "XAU" in symbol_clean or "XAG" in symbol_clean:
            return MarketProfile(symbol_clean, MarketType.COMMODITIES, 0.5, 1.0)
        else:
            return MarketProfile(symbol_clean, MarketType.FOREX, 0.0001, 10.0)
    
    def calculate_trade_plan(self,
                            symbol: str,
                            direction: str,
                            entry_price: float,
                            timeframe: TimeFrame) -> Dict:
        """Calculate complete trade plan - SIMPLIFIED VERSION"""
        market_profile = self.get_market_profile(symbol)
        
        stop_data = self.risk_manager.calculate_stop_loss(
            symbol=symbol,
            entry_price=entry_price,
            direction=direction,
            timeframe=timeframe,
            market_type=market_profile.market_type  # Pass the MarketType enum, not string
        )
        
        tp_levels = self.risk_manager.calculate_take_profits(
            entry_price=entry_price,
            stop_pips=stop_data["stop_pips"],
            direction=direction,
            timeframe=timeframe,
            symbol=symbol
        )
        
        # Fixed position size (no account balance tracking)
        position_size = 1.0  # Standard lot
        
        trade_plan = {
            "symbol": symbol,
            "direction": direction,
            "timeframe": timeframe.value,
            "entry_price": round(entry_price, 5),
            "stop_loss": round(stop_data["stop_loss"], 5),
            "stop_pips": round(stop_data["stop_pips"], 1),
            "take_profits": tp_levels,
            "position_size": position_size,
            "calculated_at": datetime.now()
        }
        
        return trade_plan
    
    def send_signal(self,
                   symbol: str,
                   direction: str,
                   entry_price: float,
                   timeframe: str = "3M") -> bool:
        """Send a trading signal to Telegram"""
        try:
            # Convert timeframe string to TimeFrame enum
            tf_map = {
                "1M": TimeFrame.M1, "3M": TimeFrame.M3, "5M": TimeFrame.M5,
                "15M": TimeFrame.M15, "30M": TimeFrame.M30, "1H": TimeFrame.H1,
                "4H": TimeFrame.H4, "1D": TimeFrame.D1
            }
            
            timeframe_enum = tf_map.get(timeframe.upper(), TimeFrame.M3)
            
            # Calculate trade plan
            trade_plan = self.calculate_trade_plan(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                timeframe=timeframe_enum
            )
            
            # Display in console
            self.display_trade_plan(trade_plan)
            
            # Send to Telegram
            success = self.telegram.send_trade_signal(trade_plan)
            
            if success:
                logger.info(f"✅ Signal sent: {symbol} {direction}")
                return True
            else:
                logger.error(f"❌ Failed to send signal: {symbol}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error processing signal for {symbol}: {e}")
            # Send error to Telegram
            error_msg = f"❌ Error processing signal for {symbol}:\n{str(e)}"
            self.telegram.send_message(error_msg)
            return False
    
    def display_trade_plan(self, trade_plan: Dict):
        """Display formatted trade plan"""
        print("\n" + "="*80)
        print("📊 TRADE SIGNAL GENERATED")
        print("="*80)
        print(f"Symbol: {trade_plan['symbol']}")
        print(f"Direction: {trade_plan['direction']}")
        print(f"Timeframe: {trade_plan['timeframe']}")
        print(f"Entry Price: {trade_plan['entry_price']:.5f}")
        print(f"Stop Loss: {trade_plan['stop_loss']:.5f} ({trade_plan['stop_pips']:.1f} pips)")
        print(f"Position Size: {trade_plan['position_size']:.2f} lots")
        
        print("\n🎯 TAKE PROFIT LEVELS:")
        print("-"*40)
        for tp in trade_plan["take_profits"]:
            print(f"TP{tp['level']}: {tp['price']:.5f} ({tp['pips']:.1f} pips, {tp['rr_ratio']}:1 RR)")
        
        print("="*80)

def main():
    """Main function - simplified and error-free"""
    
    # Your Telegram Credentials
    TELEGRAM_BOT_TOKEN = "8276762810:AAFR_9TxacZPIhx_n3ohc_tdDgp6p1WQFOI"
    TELEGRAM_CHAT_ID = "-1003587493551"
    
    print("\n" + "="*80)
    print("🤖 QUANTUM SCALPER PRO TRADING BOT")
    print("="*80)
    print("✅ Only sends signals to Telegram")
    print("✅ No account balance tracking")
    print("✅ No P&L calculations")
    print("✅ No user input required")
    print("="*80)
    
    # Initialize bot
    bot = TradingBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    
    print("\n📡 Sending Test Signals to Telegram...")
    print("-"*40)
    
    # Send test signals one by one
    signals = [
        ("EURCAD", "SHORT", 1.61159, "3M"),
        ("BTCUSD", "LONG", 87832.0, "1H"),
        ("ETHUSD", "SHORT", 2972.0, "15M"),
        ("XAUUSD", "LONG", 1835.0, "4H"),
    ]
    
    for i, (symbol, direction, price, timeframe) in enumerate(signals, 1):
        print(f"\n{i}. {symbol} {direction} Signal ({timeframe})")
        success = bot.send_signal(symbol, direction, price, timeframe)
        
        if success:
            print(f"   ✅ Signal sent successfully")
        else:
            print(f"   ❌ Failed to send signal")
        
        # Small delay between signals
        if i < len(signals):
            time.sleep(3)
    
    print("\n" + "="*80)
    print("✅ All signals processed!")
    print("📱 Check your Telegram channel for signals")
    print("="*80)
    
    # Keep bot running (optional - for continuous operation)
    print("\n🔄 Bot will stay active for 30 seconds...")
    print("Press Ctrl+C to exit immediately\n")
    
    try:
        # Keep bot alive for a while
        for i in range(30):
            time.sleep(1)
            if i % 10 == 0:
                print(f"⏰ Bot still running... ({30-i} seconds remaining)")
    except KeyboardInterrupt:
        print("\n\n🛑 Bot stopped by user")
    
    print("\n" + "="*80)
    print("✅ Bot execution completed successfully!")
    print("="*80)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)