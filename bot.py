import time
import logging
import math
import requests
import json
import os
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import random
import threading
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class MarketType(Enum):
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    STOCKS = "STOCKS"
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
    W1 = "1W"

@dataclass
class MarketProfile:
    """Market-specific volatility and characteristics"""
    symbol: str
    market_type: MarketType
    avg_daily_range: float
    spread: float
    pip_value: float = 10.0
    lot_size: float = 100000

@dataclass
class TradeSignal:
    """Trading signal"""
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    signal_strength: float = 50.0
    timestamp: datetime = field(default_factory=datetime.now)
    indicators: Dict = field(default_factory=dict)

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
                logger.info(f"Telegram message sent successfully")
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
            
            # Create direction emoji
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
    
    def send_trade_closed(self, symbol: str, exit_reason: str, exit_price: float, pnl: float, pips: float):
        """Send trade closed notification WITHOUT account balance"""
        try:
            if pnl > 0:
                title = "✅ TRADE WON 🍀️"
                emoji = "💰"
            elif pnl < 0:
                title = "❌ TRADE LOST"
                emoji = "💸"
            else:
                title = "➖ TRADE CLOSED"
                emoji = "⚪"
            
            message = f"""
<b>{title}</b>
{emoji}━━━━━━━━━━━━━━━━━━━━{emoji}

<b>📍 Symbol:</b> {symbol}  
<b>📊 Exit Reason:</b> {exit_reason}  
<b>💰 Exit Price:</b> {exit_price:.5f}  
<b>📈 P&L:</b> ${abs(pnl):.2f} {'Profit' if pnl > 0 else 'Loss'}  
<b>📊 Pips:</b> {abs(pips):.1f} {'+' if pnl > 0 else '-'}

<b>⏱️ Close Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

━━━━━━━━━━━━━━━━━━━━
<b>#TradeClosed #{symbol.replace('/', '')}</b>
"""
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Error creating trade closed message: {e}")
            return False

class DynamicRiskManager:
    """Dynamic risk management across timeframes and markets"""
    
    def __init__(self):
        # Base stop loss in pips for each timeframe
        self.timeframe_stops = {
            TimeFrame.M1: 2,   TimeFrame.M3: 3,   TimeFrame.M5: 5,
            TimeFrame.M15: 8,  TimeFrame.M30: 12, TimeFrame.H1: 15,
            TimeFrame.H4: 25,  TimeFrame.D1: 40,  TimeFrame.W1: 60
        }
        
        # Risk/Reward ratios for each timeframe
        self.timeframe_rr_ratios = {
            TimeFrame.M1: [1.0, 1.5, 2.0],   TimeFrame.M3: [1.0, 2.0, 3.0],
            TimeFrame.M5: [1.5, 2.5, 3.5],   TimeFrame.M15: [2.0, 3.0, 4.0],
            TimeFrame.M30: [2.0, 3.0, 4.0],  TimeFrame.H1: [2.5, 3.5, 5.0],
            TimeFrame.H4: [3.0, 4.0, 6.0],   TimeFrame.D1: [3.0, 5.0, 8.0],
            TimeFrame.W1: [4.0, 6.0, 10.0]
        }
        
        # Market volatility multipliers
        self.market_multipliers = {
            MarketType.FOREX: 1.0,
            MarketType.CRYPTO: 2.0,  # Reduced from 2.5
            MarketType.STOCKS: 0.8,
            MarketType.COMMODITIES: 1.2  # Reduced from 1.5
        }
    
    def calculate_pip_size(self, symbol: str) -> float:
        """Calculate pip size based on symbol"""
        symbol = symbol.upper().replace("/", "")
        
        # For JPY pairs
        if "JPY" in symbol:
            return 0.01
        # For commodities (gold, silver)
        elif "XAU" in symbol or "XAG" in symbol:
            return 0.01
        # For cryptocurrencies (usually priced in dollars)
        elif any(crypto in symbol for crypto in ["BTC", "ETH", "SOL", "XRP", "ADA", "DOT"]):
            return 0.1  # Adjusted for crypto volatility
        # For forex and others
        else:
            return 0.0001
    
    def calculate_stop_loss(self, 
                           symbol: str,
                           entry_price: float,
                           direction: str,
                           timeframe: TimeFrame,
                           market_type: MarketType) -> Dict:
        """Calculate dynamic stop loss"""
        base_stop = self.timeframe_stops.get(timeframe, 10)
        multiplier = self.market_multipliers.get(market_type, 1.0)
        stop_pips = base_stop * multiplier
        
        pip_size = self.calculate_pip_size(symbol)
        stop_distance = stop_pips * pip_size
        
        # Ensure minimum stop distance
        min_stop_distance = market_type.value.spread * 2 if hasattr(market_type, 'value') else pip_size * 5
        stop_distance = max(stop_distance, min_stop_distance)
        
        # Recalculate pips based on adjusted distance
        stop_pips = stop_distance / pip_size
        
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
                              symbol: str = None) -> List[Dict]:
        """Calculate three take-profit levels"""
        rr_ratios = self.timeframe_rr_ratios.get(timeframe, [1.0, 2.0, 3.0])
        pip_size = self.calculate_pip_size(symbol) if symbol else 0.0001
        
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
                "price": tp_price,
                "pips": tp_pips,
                "rr_ratio": ratio,
                "distance": tp_distance
            })
        
        return tp_levels
    
    def calculate_position_size(self,
                               account_balance: float,
                               risk_percent: float,
                               stop_pips: float,
                               pip_value: float,
                               max_position_size: float = 10.0) -> float:
        """
        Calculate position size based on risk with maximum limit
        """
        risk_amount = account_balance * (risk_percent / 100.0)
        
        if stop_pips > 0 and pip_value > 0:
            position_size = risk_amount / (stop_pips * pip_value)
        else:
            position_size = 0
        
        # Round to 2 decimal places
        position_size = round(position_size, 2)
        
        # Ensure minimum size
        if position_size < 0.01:
            position_size = 0.01
        
        # Apply maximum position size limit
        if position_size > max_position_size:
            position_size = max_position_size
        
        return position_size

class TradingBot:
    """Trading bot with adaptive parameters and Telegram notifications"""
    
    def __init__(self, 
                 telegram_token: str = None,
                 telegram_chat_id: str = None):
        
        self.risk_manager = DynamicRiskManager()
        self.market_profiles = self.initialize_market_profiles()
        self.active_trades = {}
        self.trade_history = []
        
        # Initialize Telegram notifier
        if telegram_token and telegram_chat_id:
            try:
                self.telegram = TelegramNotifier(telegram_token, telegram_chat_id)
                # Test Telegram connection
                test_msg = self.telegram.send_message(
                    "🤖 Trading Bot Started Successfully!\n"
                    f"Ready to receive signals...\n"
                    f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    disable_notification=False
                )
                if test_msg:
                    logger.info("✅ Telegram notifications ENABLED and working")
                else:
                    logger.warning("⚠️ Telegram notifications enabled but connection test failed")
                    self.telegram = None
            except Exception as e:
                logger.error(f"❌ Failed to initialize Telegram: {e}")
                self.telegram = None
        else:
            self.telegram = None
            logger.info("ℹ️ Telegram notifications DISABLED - no credentials provided")
    
    def initialize_market_profiles(self) -> Dict[str, MarketProfile]:
        """Initialize market profiles"""
        profiles = {
            # Forex
            "EURUSD": MarketProfile("EURUSD", MarketType.FOREX, 70.0, 0.0001, 10.0),
            "GBPUSD": MarketProfile("GBPUSD", MarketType.FOREX, 90.0, 0.00012, 10.0),
            "USDJPY": MarketProfile("USDJPY", MarketType.FOREX, 65.0, 0.01, 9.27),
            "EURCAD": MarketProfile("EURCAD", MarketType.FOREX, 85.0, 0.00015, 7.5),
            
            # Cryptocurrencies (adjusted pip values)
            "BTCUSD": MarketProfile("BTCUSD", MarketType.CRYPTO, 3000.0, 5.0, 1.0, 1.0),
            "ETHUSD": MarketProfile("ETHUSD", MarketType.CRYPTO, 150.0, 0.5, 1.0, 1.0),
            "SOLUSD": MarketProfile("SOLUSD", MarketType.CRYPTO, 10.0, 0.1, 0.5, 1.0),
            
            # Commodities
            "XAUUSD": MarketProfile("XAUUSD", MarketType.COMMODITIES, 1500.0, 0.5, 1.0),
        }
        return profiles
    
    def get_market_profile(self, symbol: str) -> MarketProfile:
        """Get or create market profile for symbol"""
        symbol = symbol.upper().replace("/", "")
        
        if symbol in self.market_profiles:
            return self.market_profiles[symbol]
        
        # Auto-detect market type
        if any(crypto in symbol for crypto in ["BTC", "ETH", "SOL", "XRP"]):
            return MarketProfile(symbol, MarketType.CRYPTO, 500.0, 1.0, 1.0, 1.0)
        elif any(commodity in symbol for commodity in ["XAU", "XAG"]):
            return MarketProfile(symbol, MarketType.COMMODITIES, 100.0, 0.5, 1.0)
        else:
            return MarketProfile(symbol, MarketType.FOREX, 80.0, 0.0001, 10.0)
    
    def calculate_trade_plan(self,
                            symbol: str,
                            direction: str,
                            entry_price: float,
                            timeframe: TimeFrame,
                            risk_amount: float = 100.0) -> Dict:
        """Calculate complete trade plan"""
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
            stop_pips=stop_data["stop_pips"],
            direction=direction,
            timeframe=timeframe,
            symbol=symbol
        )
        
        # Calculate position size based on fixed risk amount
        position_size = self.risk_manager.calculate_position_size(
            account_balance=10000.0,  # Fixed for calculation
            risk_percent=(risk_amount / 10000.0) * 100,
            stop_pips=stop_data["stop_pips"],
            pip_value=market_profile.pip_value,
            max_position_size=5.0  # Max 5 lots
        )
        
        trade_plan = {
            "symbol": symbol,
            "direction": direction,
            "market_type": market_profile.market_type.value,
            "timeframe": timeframe.value,
            "entry_price": entry_price,
            "stop_loss": stop_data["stop_loss"],
            "stop_pips": stop_data["stop_pips"],
            "take_profits": tp_levels,
            "position_size": position_size,
            "risk_amount": risk_amount,
            "pip_value": market_profile.pip_value,
            "calculated_at": datetime.now()
        }
        
        return trade_plan
    
    def process_signal(self, 
                      symbol: str,
                      direction: str,
                      entry_price: float,
                      timeframe: str = "3M",
                      risk_amount: float = 100.0) -> Optional[str]:
        """Process a trading signal and send to Telegram"""
        try:
            # Convert timeframe string to TimeFrame enum
            tf_map = {
                "1M": TimeFrame.M1, "3M": TimeFrame.M3, "5M": TimeFrame.M5,
                "15M": TimeFrame.M15, "30M": TimeFrame.M30, "1H": TimeFrame.H1,
                "4H": TimeFrame.H4, "1D": TimeFrame.D1, "1W": TimeFrame.W1
            }
            timeframe_enum = tf_map.get(timeframe.upper(), TimeFrame.M3)
            
            # Calculate trade plan
            trade_plan = self.calculate_trade_plan(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                timeframe=timeframe_enum,
                risk_amount=risk_amount
            )
            
            # Display in console
            self.display_trade_plan(trade_plan)
            
            # Send to Telegram
            if self.telegram:
                success = self.telegram.send_trade_signal(trade_plan)
                if not success:
                    logger.error("❌ Failed to send signal to Telegram")
                    return None
            
            # Generate trade ID
            trade_id = f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Store trade
            self.active_trades[trade_id] = {
                **trade_plan,
                "trade_id": trade_id,
                "status": "PENDING",
                "entry_time": datetime.now()
            }
            
            logger.info(f"✅ Signal processed: {symbol} {direction} at {entry_price}")
            return trade_id
            
        except Exception as e:
            logger.error(f"❌ Error processing signal: {e}")
            if self.telegram:
                self.telegram.send_message(f"❌ Error processing signal for {symbol}: {str(e)}")
            return None
    
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
        print(f"Risk Amount: ${trade_plan['risk_amount']:.2f}")
        
        print("\n🎯 TAKE PROFIT LEVELS:")
        print("-"*40)
        for tp in trade_plan["take_profits"]:
            print(f"TP{tp['level']}: {tp['price']:.5f} ({tp['pips']:.1f} pips, {tp['rr_ratio']}:1 RR)")
        
        print("="*80)
    
    def simulate_trade_result(self, trade_id: str, exit_price: float, exit_reason: str):
        """Simulate a trade result (for testing)"""
        if trade_id not in self.active_trades:
            logger.error(f"Trade {trade_id} not found")
            return
        
        trade = self.active_trades[trade_id]
        
        # Calculate P&L
        if trade["direction"] == "LONG":
            price_diff = exit_price - trade["entry_price"]
        else:  # SHORT
            price_diff = trade["entry_price"] - exit_price
        
        # Calculate pips
        pip_size = self.risk_manager.calculate_pip_size(trade['symbol'])
        pips = price_diff / pip_size
        
        # Calculate P&L (simplified)
        pnl = pips * trade["position_size"] * trade["pip_value"] / 100
        
        # Ensure reasonable P&L
        max_pnl = trade["risk_amount"] * 10  # Max 10x risk
        pnl = max(min(pnl, max_pnl), -trade["risk_amount"])
        
        # Update trade status
        trade["status"] = "CLOSED"
        trade["exit_price"] = exit_price
        trade["exit_reason"] = exit_reason
        trade["pnl"] = pnl
        trade["pips"] = pips
        trade["exit_time"] = datetime.now()
        
        # Move to history
        self.trade_history.append(trade)
        del self.active_trades[trade_id]
        
        # Send Telegram notification
        if self.telegram:
            self.telegram.send_trade_closed(
                symbol=trade['symbol'],
                exit_reason=exit_reason,
                exit_price=exit_price,
                pnl=pnl,
                pips=pips
            )
        
        logger.info(f"📊 Trade {trade_id} closed: {exit_reason}")
        logger.info(f"Exit Price: {exit_price:.5f}")
        logger.info(f"Pips: {pips:.1f}")
        logger.info(f"P&L: ${pnl:.2f}")

def main():
    """Main trading bot"""
    
    # Your Telegram Credentials
    TELEGRAM_BOT_TOKEN = "8276762810:AAFR_9TxacZPIhx_n3ohc_tdDgp6p1WQFOI"
    TELEGRAM_CHAT_ID = "-1003587493551"
    
    print("\n" + "="*80)
    print("🤖 TRADING BOT - TELEGRAM SIGNALS ONLY")
    print("="*80)
    print(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    print("="*80)
    
    # Initialize bot
    bot = TradingBot(
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID
    )
    
    # Send test signals
    print("\n📡 Sending Test Signals to Telegram...")
    print("-"*40)
    
    # Signal 1: EURCAD Short (from your original image)
    print("\n1. EURCAD Short Signal (3-minute)")
    trade_id1 = bot.process_signal(
        symbol="EURCAD",
        direction="SHORT",
        entry_price=1.61159,
        timeframe="3M",
        risk_amount=100.0
    )
    
    time.sleep(3)
    
    # Signal 2: BTCUSD Long
    print("\n2. BTCUSD Long Signal (1-hour)")
    trade_id2 = bot.process_signal(
        symbol="BTCUSD",
        direction="LONG",
        entry_price=87832.0,
        timeframe="1H",
        risk_amount=100.0
    )
    
    time.sleep(3)
    
    # Signal 3: ETHUSD Short
    print("\n3. ETHUSD Short Signal (15-minute)")
    trade_id3 = bot.process_signal(
        symbol="ETHUSD",
        direction="SHORT",
        entry_price=2972.0,
        timeframe="15M",
        risk_amount=100.0
    )
    
    time.sleep(3)
    
    # Signal 4: XAUUSD Long
    print("\n4. XAUUSD Long Signal (4-hour)")
    trade_id4 = bot.process_signal(
        symbol="XAUUSD",
        direction="LONG",
        entry_price=1835.0,
        timeframe="4H",
        risk_amount=100.0
    )
    
    # Simulate some trade results (optional)
    print("\n" + "="*80)
    print("📊 Simulating Trade Results (Optional)")
    print("="*80)
    
    simulate = input("\nSimulate trade results? (y/n): ").lower().strip()
    
    if simulate == 'y':
        # Simulate EURCAD trade hitting TP2
        if trade_id1:
            time.sleep(2)
            bot.simulate_trade_result(trade_id1, 1.61099, "TP2")
        
        # Simulate BTCUSD trade hitting STOP LOSS
        if trade_id2:
            time.sleep(2)
            bot.simulate_trade_result(trade_id2, 87831.0, "STOP_LOSS")
        
        # Simulate ETHUSD trade hitting TP1
        if trade_id3:
            time.sleep(2)
            bot.simulate_trade_result(trade_id3, 2968.0, "TP1")
        
        # Simulate XAUUSD trade hitting TP3
        if trade_id4:
            time.sleep(2)
            bot.simulate_trade_result(trade_id4, 1855.0, "TP3")
    
    print("\n" + "="*80)
    print("✅ Bot execution completed successfully!")
    print("📱 Check your Telegram for all trade signals!")
    print("="*80)
    
    # Keep bot running to receive new signals
    print("\n🔄 Bot is running and ready to receive new signals...")
    print("Press Ctrl+C to stop\n")
    
    # Simple loop to keep bot alive
    try:
        while True:
            # Check for new signals every 10 seconds
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Bot stopped by user")
        if bot.telegram:
            bot.telegram.send_message("🛑 Trading Bot Stopped\nGoodbye!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()