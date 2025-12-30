import time
import logging
import requests
from typing import Dict, List
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
            
            # Format based on symbol type
            symbol_upper = symbol.upper().replace("/", "")
            if any(x in symbol_upper for x in ["XAU", "XAG"]):
                # Commodities - show 2 decimal places
                entry_fmt = f"{entry:.2f}"
                sl_fmt = f"{sl:.2f}"
                tp1_fmt = f"{tp1:.2f}"
                tp2_fmt = f"{tp2:.2f}"
                tp3_fmt = f"{tp3:.2f}"
            elif any(x in symbol_upper for x in ["BTC", "ETH", "SOL"]):
                # Crypto - show 2 decimal places
                entry_fmt = f"{entry:.2f}"
                sl_fmt = f"{sl:.2f}"
                tp1_fmt = f"{tp1:.2f}"
                tp2_fmt = f"{tp2:.2f}"
                tp3_fmt = f"{tp3:.2f}"
            else:
                # Forex - show 5 decimal places
                entry_fmt = f"{entry:.5f}"
                sl_fmt = f"{sl:.5f}"
                tp1_fmt = f"{tp1:.5f}"
                tp2_fmt = f"{tp2:.5f}"
                tp3_fmt = f"{tp3:.5f}"
            
            message = f"""
<b>{direction_emoji} TRADE SIGNAL {direction_emoji}</b>
━━━━━━━━━━━━━━━━━━━━

<b>📍 Pair:</b> {symbol}
<b>📊 Direction:</b> <b>{direction_text}</b>
<b>⏰ Timeframe:</b> {timeframe}

<b>💰 Entry Price:</b> <code>{entry_fmt}</code>
<b>🛑 Stop Loss:</b> <code>{sl_fmt}</code>

<b>🎯 Take Profit 1:</b> <code>{tp1_fmt}</code>
<b>🎯 Take Profit 2:</b> <code>{tp2_fmt}</code>
<b>🎯 Take Profit 3:</b> <code>{tp3_fmt}</code>

<b>⏱️ Signal Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

━━━━━━━━━━━━━━━━━━━━
<b>#TradeSignal #{symbol.replace('/', '')} #{direction}</b>
"""
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Error creating trade signal message: {e}")
            return False

class DynamicRiskManager:
    """Dynamic risk management with PROPER realistic calculations"""
    
    def __init__(self):
        # REALISTIC stop distances for each timeframe and market
        self.timeframe_config = {
            TimeFrame.M1: {
                "forex_pips": 2,      # 2 pips for forex
                "crypto_points": 5,   # $5 for crypto
                "gold_points": 2      # $2 for gold
            },
            TimeFrame.M3: {
                "forex_pips": 3,      # 3 pips for forex
                "crypto_points": 10,  # $10 for crypto
                "gold_points": 3      # $3 for gold
            },
            TimeFrame.M5: {
                "forex_pips": 5,      # 5 pips for forex
                "crypto_points": 15,  # $15 for crypto
                "gold_points": 5      # $5 for gold
            },
            TimeFrame.M15: {
                "forex_pips": 8,      # 8 pips for forex
                "crypto_points": 20,  # $20 for crypto
                "gold_points": 8      # $8 for gold
            },
            TimeFrame.M30: {
                "forex_pips": 12,     # 12 pips for forex
                "crypto_points": 30,  # $30 for crypto
                "gold_points": 12     # $12 for gold
            },
            TimeFrame.H1: {
                "forex_pips": 15,     # 15 pips for forex
                "crypto_points": 40,  # $40 for crypto
                "gold_points": 15     # $15 for gold
            },
            TimeFrame.H4: {
                "forex_pips": 25,     # 25 pips for forex
                "crypto_points": 60,  # $60 for crypto
                "gold_points": 20     # $20 for gold (NOT 25)
            },
            TimeFrame.D1: {
                "forex_pips": 40,     # 40 pips for forex
                "crypto_points": 100, # $100 for crypto
                "gold_points": 30     # $30 for gold
            }
        }
        
        # REALISTIC Risk/Reward ratios (lower for higher timeframes)
        self.timeframe_rr_ratios = {
            TimeFrame.M1: [1.0, 1.5, 2.0],   # M1: 1:1, 1.5:1, 2:1
            TimeFrame.M3: [1.0, 2.0, 3.0],   # M3: 1:1, 2:1, 3:1
            TimeFrame.M5: [1.5, 2.0, 2.5],   # M5: 1.5:1, 2:1, 2.5:1
            TimeFrame.M15: [1.5, 2.0, 2.5],  # M15: 1.5:1, 2:1, 2.5:1
            TimeFrame.M30: [1.5, 2.0, 2.5],  # M30: 1.5:1, 2:1, 2.5:1
            TimeFrame.H1: [2.0, 2.5, 3.0],   # H1: 2:1, 2.5:1, 3:1
            TimeFrame.H4: [2.0, 2.5, 3.0],   # H4: 2:1, 2.5:1, 3:1 (NOT 3:1, 4:1, 6:1)
            TimeFrame.D1: [2.0, 2.5, 3.0]    # D1: 2:1, 2.5:1, 3:1
        }
    
    def calculate_pip_size(self, symbol: str) -> float:
        """Calculate pip size based on symbol"""
        symbol_upper = symbol.upper().replace("/", "")
        
        if "JPY" in symbol_upper:
            return 0.01
        elif "XAU" in symbol_upper or "XAG" in symbol_upper:
            return 0.01  # Gold: 1 pip = $0.01
        elif "BTC" in symbol_upper:
            return 1.0   # Bitcoin: 1 pip = $1.00
        elif "ETH" in symbol_upper:
            return 0.1   # Ethereum: 1 pip = $0.10
        elif "SOL" in symbol_upper:
            return 0.01  # Solana: 1 pip = $0.01
        else:
            return 0.0001  # Standard forex
    
    def get_stop_config(self, symbol: str, timeframe: TimeFrame, market_type: MarketType):
        """Get stop configuration based on symbol, timeframe, and market type"""
        config = self.timeframe_config.get(timeframe, {
            "forex_pips": 10,
            "crypto_points": 30,
            "gold_points": 10
        })
        
        if market_type == MarketType.CRYPTO:
            stop_distance = config["crypto_points"]
            stop_units = "points"  # In dollars
        elif market_type == MarketType.COMMODITIES:
            stop_distance = config["gold_points"]
            stop_units = "points"  # In dollars
        else:  # FOREX
            stop_distance = config["forex_pips"]
            stop_units = "pips"
        
        return stop_distance, stop_units
    
    def calculate_stop_loss(self, 
                           symbol: str,
                           entry_price: float,
                           direction: str,
                           timeframe: TimeFrame,
                           market_type: MarketType) -> Dict:
        """Calculate PROPER realistic stop loss"""
        stop_distance, stop_units = self.get_stop_config(symbol, timeframe, market_type)
        
        # Calculate stop price distance
        if stop_units == "pips":
            pip_size = self.calculate_pip_size(symbol)
            stop_price_distance = stop_distance * pip_size
        else:  # "points" (dollars)
            stop_price_distance = stop_distance
        
        # Calculate stop price
        if direction.upper() == "SHORT":
            stop_price = entry_price + stop_price_distance
        else:
            stop_price = entry_price - stop_price_distance
        
        # Round appropriately
        symbol_upper = symbol.upper().replace("/", "")
        if any(x in symbol_upper for x in ["XAU", "BTC", "ETH"]):
            stop_price = round(stop_price, 2)
        else:
            stop_price = round(stop_price, 5)
        
        return {
            "stop_loss": stop_price,
            "stop_distance": stop_distance,  # In pips or points
            "stop_units": stop_units,
            "price_distance": stop_price_distance
        }
    
    def calculate_take_profits(self,
                              entry_price: float,
                              stop_distance: float,
                              stop_units: str,
                              direction: str,
                              timeframe: TimeFrame,
                              symbol: str) -> List[Dict]:
        """Calculate REALISTIC take-profit levels"""
        rr_ratios = self.timeframe_rr_ratios.get(timeframe, [1.0, 1.5, 2.0])
        
        tp_levels = []
        for i, ratio in enumerate(rr_ratios):
            if stop_units == "pips":
                pip_size = self.calculate_pip_size(symbol)
                tp_price_distance = stop_distance * ratio * pip_size
                tp_pips = stop_distance * ratio
            else:  # "points" (dollars)
                tp_price_distance = stop_distance * ratio
                tp_pips = stop_distance * ratio  # Actually points, but we'll call it pips for display
            
            if direction.upper() == "SHORT":
                tp_price = entry_price - tp_price_distance
            else:
                tp_price = entry_price + tp_price_distance
            
            # Round appropriately
            symbol_upper = symbol.upper().replace("/", "")
            if any(x in symbol_upper for x in ["XAU", "BTC", "ETH"]):
                tp_price = round(tp_price, 2)
                tp_pips = round(tp_pips, 1)
            else:
                tp_price = round(tp_price, 5)
                tp_pips = round(tp_pips, 1)
            
            tp_levels.append({
                "level": i + 1,
                "price": tp_price,
                "pips": tp_pips,
                "rr_ratio": ratio,
                "distance": tp_price_distance
            })
        
        return tp_levels

class TradingBot:
    """Trading bot with PROPER realistic calculations"""
    
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
            
            # Cryptocurrencies
            "BTCUSD": MarketProfile("BTCUSD", MarketType.CRYPTO, 5.0, 1.0),
            "ETHUSD": MarketProfile("ETHUSD", MarketType.CRYPTO, 0.5, 1.0),
            "SOLUSD": MarketProfile("SOLUSD", MarketType.CRYPTO, 0.1, 1.0),
            
            # Commodities
            "XAUUSD": MarketProfile("XAUUSD", MarketType.COMMODITIES, 0.5, 1.0),
        }
    
    def get_market_profile(self, symbol: str) -> MarketProfile:
        """Get market profile for symbol"""
        symbol_clean = symbol.upper().replace("/", "")
        
        if symbol_clean in self.market_profiles:
            return self.market_profiles[symbol_clean]
        
        # Auto-detect for unknown symbols
        if any(crypto in symbol_clean for crypto in ["BTC", "ETH", "SOL"]):
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
        """Calculate complete trade plan with PROPER values"""
        market_profile = self.get_market_profile(symbol)
        
        stop_data = self.risk_manager.calculate_stop_loss(
            symbol=symbol,
            entry_price=entry_price,
            direction=direction,
            timeframe=timeframe,
            market_type=market_profile.market_type
        )
        
        tp_levels = self.risk_manager.calculate_take_profits(
            entry_price=entry_price,
            stop_distance=stop_data["stop_distance"],
            stop_units=stop_data["stop_units"],
            direction=direction,
            timeframe=timeframe,
            symbol=symbol
        )
        
        trade_plan = {
            "symbol": symbol,
            "direction": direction,
            "timeframe": timeframe.value,
            "entry_price": entry_price,
            "stop_loss": stop_data["stop_loss"],
            "stop_distance": stop_data["stop_distance"],
            "stop_units": stop_data["stop_units"],
            "take_profits": tp_levels,
            "position_size": 1.0,
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
            
            # Display in console for debugging
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
        """Display formatted trade plan for debugging"""
        print("\n" + "="*80)
        print("📊 TRADE SIGNAL DETAILS")
        print("="*80)
        print(f"Symbol: {trade_plan['symbol']}")
        print(f"Direction: {trade_plan['direction']}")
        print(f"Timeframe: {trade_plan['timeframe']}")
        print(f"Entry Price: {trade_plan['entry_price']}")
        print(f"Stop Loss: {trade_plan['stop_loss']}")
        
        symbol_upper = trade_plan['symbol'].upper().replace("/", "")
        stop_units = trade_plan['stop_units']
        
        if stop_units == "pips":
            print(f"Stop Distance: {trade_plan['stop_distance']:.1f} pips")
        else:
            print(f"Stop Distance: ${trade_plan['stop_distance']:.1f}")
        
        print("\n🎯 TAKE PROFIT LEVELS:")
        print("-"*40)
        for tp in trade_plan["take_profits"]:
            if stop_units == "pips":
                print(f"TP{tp['level']}: {tp['price']:.5f} ({tp['pips']:.1f} pips, {tp['rr_ratio']}:1 RR)")
            else:
                print(f"TP{tp['level']}: {tp['price']:.2f} (${tp['pips']:.1f}, {tp['rr_ratio']}:1 RR)")
        
        print("="*80)

def main():
    """Main function - sends PROPER realistic signals"""
    
    # Your Telegram Credentials
    TELEGRAM_BOT_TOKEN = "8276762810:AAFR_9TxacZPIhx_n3ohc_tdDgp6p1WQFOI"
    TELEGRAM_CHAT_ID = "-1003587493551"
    
    print("\n" + "="*80)
    print("🤖 QUANTUM SCALPER PRO - PROPER REALISTIC CALCULATIONS")
    print("="*80)
    print("Fixing unrealistic take profit calculations...")
    print("="*80)
    
    # Initialize bot
    bot = TradingBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    
    print("\n📡 Sending PROPER Signals to Telegram...")
    print("-"*40)
    
    # Signals with PROPER calculations
    signals = [
        # Signal 1: EURCAD Short (3-minute)
        ("EURCAD", "SHORT", 1.61159, "3M"),
        
        # Signal 2: BTCUSD Long (1-hour)
        ("BTCUSD", "LONG", 87832.0, "1H"),
        
        # Signal 3: ETHUSD Short (15-minute)
        ("ETHUSD", "SHORT", 2985.60, "15M"),
        
        # Signal 4: XAUUSD Long (4-hour) - FIXED
        ("XAUUSD", "LONG", 1835.0, "4H"),
    ]
    
    success_count = 0
    for i, (symbol, direction, price, timeframe) in enumerate(signals, 1):
        print(f"\n{i}. {symbol} {direction} Signal ({timeframe})")
        print(f"   Entry Price: {price}")
        
        success = bot.send_signal(symbol, direction, price, timeframe)
        
        if success:
            print(f"   ✅ Signal sent successfully")
            success_count += 1
        else:
            print(f"   ❌ Failed to send signal")
        
        # Small delay between signals
        if i < len(signals):
            time.sleep(3)
    
    # Show what to expect with PROPER calculations
    print("\n" + "="*80)
    print("📊 PROPER REALISTIC CALCULATIONS:")
    print("="*80)
    print("1. EURCAD (3M Short):")
    print("   - Stop: 3 pips above = 1.61159 + 0.0003 = 1.61189")
    print("   - TP1: 3 pips below = 1.61159 - 0.0003 = 1.61129 (1:1 RR)")
    print("   - TP2: 6 pips below = 1.61159 - 0.0006 = 1.61099 (2:1 RR)")
    print("   - TP3: 9 pips below = 1.61159 - 0.0009 = 1.61069 (3:1 RR)")
    
    print("\n2. BTCUSD (1H Long):")
    print("   - Stop: $40 below = 87832.0 - 40 = 87792.0")
    print("   - TP1: $80 above = 87832.0 + 80 = 87912.0 (2:1 RR)")
    print("   - TP2: $100 above = 87832.0 + 100 = 87932.0 (2.5:1 RR)")
    print("   - TP3: $120 above = 87832.0 + 120 = 87952.0 (3:1 RR)")
    
    print("\n3. ETHUSD (15M Short):")
    print("   - Stop: $20 above = 2985.60 + 20 = 3005.60")
    print("   - TP1: $30 below = 2985.60 - 30 = 2955.60 (1.5:1 RR)")
    print("   - TP2: $40 below = 2985.60 - 40 = 2945.60 (2:1 RR)")
    print("   - TP3: $50 below = 2985.60 - 50 = 2935.60 (2.5:1 RR)")
    
    print("\n4. XAUUSD (4H Long) - FIXED:")
    print("   - Stop: $20 below = 1835.0 - 20 = 1815.0")
    print("   - TP1: $40 above = 1835.0 + 40 = 1875.0 (2:1 RR)")
    print("   - TP2: $50 above = 1835.0 + 50 = 1885.0 (2.5:1 RR)")
    print("   - TP3: $60 above = 1835.0 + 60 = 1895.0 (3:1 RR)")
    print("   - NOT $75, $100, $150 like before!")
    print("="*80)
    
    print(f"\n📊 RESULTS: {success_count}/{len(signals)} signals sent successfully")
    print("📱 Check your Telegram channel for PROPER realistic signals")
    print("="*80)
    
    # Keep bot running briefly
    print("\n🔄 Bot staying active for 10 seconds...")
    for i in range(10, 0, -1):
        print(f"   Shutting down in {i} seconds...", end='\r')
        time.sleep(1)
    
    print("\n\n✅ Bot execution completed successfully!")
    print("="*80)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)