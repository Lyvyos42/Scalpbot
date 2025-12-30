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
        self.last_message_time = {}
        
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
            risk = trade_plan['risk_amount']
            position_size = trade_plan['position_size']
            
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

<b>⚖️ Position Size:</b> {position_size:.2f} lots
<b>📉 Risk Amount:</b> ${risk:.2f}
<b>📈 Risk/Reward:</b> 1:{trade_plan['take_profits'][2]['rr_ratio']}

<b>⏱️ Signal Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

━━━━━━━━━━━━━━━━━━━━
<b>#TradeSignal #{symbol.replace('/', '')} #{direction}</b>
"""
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Error creating trade signal message: {e}")
            return False
    
    def send_trade_update(self, trade_id: str, symbol: str, status: str, pnl: float = 0, current_price: float = None):
        """Send trade update to Telegram"""
        try:
            if pnl > 0:
                emoji = "💰 PROFIT 💰"
            elif pnl < 0:
                emoji = "💸 LOSS 💸"
            else:
                emoji = "⚪ BREAKEVEN ⚪"
            
            message = f"""
<b>{emoji}</b>
━━━━━━━━━━━━━━━━━━━━

<b>📊 Trade Update:</b> <code>{trade_id}</code>
<b>📍 Symbol:</b> <code>{symbol}</code>
<b>📈 Status:</b> <b>{status}</b>

"""
            if current_price:
                message += f"<b>💰 Current Price:</b> <code>{current_price:.5f}</code>\n"
            
            if pnl != 0:
                message += f"<b>📊 P&L:</b> <code>${abs(pnl):.2f}</code> {'Profit' if pnl > 0 else 'Loss'}\n"
            
            message += f"""
<b>⏱️ Time:</b> {datetime.now().strftime('%H:%M:%S UTC')}

━━━━━━━━━━━━━━━━━━━━
"""
            return self.send_message(message, disable_notification=(abs(pnl) < 10))
        except Exception as e:
            logger.error(f"Error creating trade update message: {e}")
            return False
    
    def send_trade_closed(self, trade_id: str, symbol: str, exit_reason: str, exit_price: float, pnl: float, pips: float):
        """Send trade closed notification"""
        try:
            if pnl > 0:
                title = "✅ TRADE WON ✅"
                emoji = "💰"
            elif pnl < 0:
                title = "❌ TRADE LOST ❌"
                emoji = "💸"
            else:
                title = "➖ TRADE CLOSED ➖"
                emoji = "⚪"
            
            message = f"""
<b>{title}</b>
{emoji}━━━━━━━━━━━━━━━━━━━━{emoji}

<b>📊 Trade ID:</b> <code>{trade_id}</code>
<b>📍 Symbol:</b> <code>{symbol}</code>
<b>📈 Exit Reason:</b> <b>{exit_reason}</b>
<b>💰 Exit Price:</b> <code>{exit_price:.5f}</code>
<b>📊 P&L:</b> <code>${abs(pnl):.2f}</code> {'Profit' if pnl > 0 else 'Loss'}
<b>📈 Pips:</b> {abs(pips):.1f} {'+' if pnl > 0 else '-'}

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
        self.timeframe_stops = {
            TimeFrame.M1: 2,   TimeFrame.M3: 3,   TimeFrame.M5: 5,
            TimeFrame.M15: 8,  TimeFrame.M30: 12, TimeFrame.H1: 15,
            TimeFrame.H4: 25,  TimeFrame.D1: 40,  TimeFrame.W1: 60
        }
        
        self.timeframe_rr_ratios = {
            TimeFrame.M1: [1.0, 1.5, 2.0],   TimeFrame.M3: [1.0, 2.0, 3.0],
            TimeFrame.M5: [1.5, 2.5, 3.5],   TimeFrame.M15: [2.0, 3.0, 4.0],
            TimeFrame.M30: [2.0, 3.0, 4.0],  TimeFrame.H1: [2.5, 3.5, 5.0],
            TimeFrame.H4: [3.0, 4.0, 6.0],   TimeFrame.D1: [3.0, 5.0, 8.0],
            TimeFrame.W1: [4.0, 6.0, 10.0]
        }
        
        self.market_multipliers = {
            MarketType.FOREX: 1.0,
            MarketType.CRYPTO: 2.5,
            MarketType.STOCKS: 0.8,
            MarketType.COMMODITIES: 1.5
        }
    
    def calculate_pip_size(self, symbol: str) -> float:
        """Calculate pip size based on symbol"""
        symbol = symbol.upper()
        if "JPY" in symbol:
            return 0.01
        elif any(x in symbol for x in ["XAU", "XAG", "OIL"]):  # Gold, Silver, Oil
            return 0.01
        elif any(x in symbol for x in ["BTC", "ETH", "SOL"]):  # Cryptos
            return 1.0
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
                               pip_value: float) -> float:
        """Calculate position size based on risk"""
        risk_amount = account_balance * (risk_percent / 100.0)
        
        if stop_pips > 0:
            position_size = risk_amount / (stop_pips * pip_value)
        else:
            position_size = 0
        
        position_size = round(position_size, 2)
        
        if position_size < 0.01:
            position_size = 0.01
        
        return position_size

class AdaptiveTradingBot:
    """Trading bot with adaptive parameters and Telegram notifications"""
    
    def __init__(self, 
                 account_balance: float = 10000.0,
                 telegram_token: str = None,
                 telegram_chat_id: str = None,
                 risk_percent: float = 1.0):
        
        self.account_balance = account_balance
        self.risk_percent = risk_percent
        self.risk_manager = DynamicRiskManager()
        self.market_profiles = self.initialize_market_profiles()
        self.active_trades = {}
        self.signal_queue = []
        self.last_signal_time = {}
        
        # Initialize Telegram notifier
        if telegram_token and telegram_chat_id:
            try:
                self.telegram = TelegramNotifier(telegram_token, telegram_chat_id)
                # Test Telegram connection
                test_msg = self.telegram.send_message(
                    "🤖 Trading Bot Started Successfully!\n"
                    f"Account Balance: ${account_balance:,.2f}\n"
                    f"Risk Per Trade: {risk_percent}%\n"
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
            "AUDUSD": MarketProfile("AUDUSD", MarketType.FOREX, 75.0, 0.0001, 10.0),
            "NZDUSD": MarketProfile("NZDUSD", MarketType.FOREX, 80.0, 0.00012, 10.0),
            "USDCAD": MarketProfile("USDCAD", MarketType.FOREX, 70.0, 0.0001, 10.0),
            
            # Cryptocurrencies
            "BTCUSD": MarketProfile("BTCUSD", MarketType.CRYPTO, 3000.0, 5.0, 1.0, 1.0),
            "ETHUSD": MarketProfile("ETHUSD", MarketType.CRYPTO, 150.0, 0.5, 1.0, 1.0),
            "SOLUSD": MarketProfile("SOLUSD", MarketType.CRYPTO, 10.0, 0.1, 1.0, 1.0),
            "XRPUSD": MarketProfile("XRPUSD", MarketType.CRYPTO, 0.05, 0.0001, 1.0, 1.0),
            
            # Commodities
            "XAUUSD": MarketProfile("XAUUSD", MarketType.COMMODITIES, 1500.0, 0.5, 1.0),
            "XAGUSD": MarketProfile("XAGUSD", MarketType.COMMODITIES, 1.5, 0.01, 1.0),
            
            # Indices
            "US30": MarketProfile("US30", MarketType.STOCKS, 300.0, 2.0, 1.0),
            "SPX500": MarketProfile("SPX500", MarketType.STOCKS, 50.0, 0.5, 1.0),
            "NAS100": MarketProfile("NAS100", MarketType.STOCKS, 150.0, 1.0, 1.0),
        }
        return profiles
    
    def get_market_profile(self, symbol: str) -> MarketProfile:
        """Get or create market profile for symbol"""
        symbol = symbol.upper().replace("/", "")
        
        if symbol in self.market_profiles:
            return self.market_profiles[symbol]
        
        # Auto-detect market type
        if any(crypto in symbol for crypto in ["BTC", "ETH", "SOL", "XRP", "ADA", "DOT"]):
            return MarketProfile(symbol, MarketType.CRYPTO, 500.0, 1.0, 1.0, 1.0)
        elif any(forex in symbol for forex in ["EUR", "GBP", "USD", "JPY", "CAD", "AUD", "NZD", "CHF"]):
            return MarketProfile(symbol, MarketType.FOREX, 80.0, 0.0001, 10.0)
        elif any(commodity in symbol for commodity in ["XAU", "XAG", "OIL"]):
            return MarketProfile(symbol, MarketType.COMMODITIES, 100.0, 0.5, 1.0)
        else:
            return MarketProfile(symbol, MarketType.STOCKS, 50.0, 0.1, 1.0, 100)
    
    def calculate_trade_plan(self,
                            symbol: str,
                            direction: str,
                            entry_price: float,
                            timeframe: TimeFrame,
                            risk_percent: float = None) -> Dict:
        """Calculate complete trade plan"""
        if risk_percent is None:
            risk_percent = self.risk_percent
        
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
        
        position_size = self.risk_manager.calculate_position_size(
            account_balance=self.account_balance,
            risk_percent=risk_percent,
            stop_pips=stop_data["stop_pips"],
            pip_value=market_profile.pip_value
        )
        
        risk_amount = self.account_balance * (risk_percent / 100.0)
        
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
            "risk_percent": risk_percent,
            "pip_value": market_profile.pip_value,
            "calculated_at": datetime.now()
        }
        
        return trade_plan
    
    def add_signal(self, 
                  symbol: str,
                  direction: str,
                  entry_price: float,
                  timeframe: str = "3M",
                  signal_strength: float = 50.0,
                  indicators: Dict = None):
        """Add a trading signal (main entry point for signals)"""
        try:
            # Convert timeframe string to TimeFrame enum
            tf_map = {
                "1M": TimeFrame.M1, "3M": TimeFrame.M3, "5M": TimeFrame.M5,
                "15M": TimeFrame.M15, "30M": TimeFrame.M30, "1H": TimeFrame.H1,
                "4H": TimeFrame.H4, "1D": TimeFrame.D1, "1W": TimeFrame.W1
            }
            timeframe_enum = tf_map.get(timeframe.upper(), TimeFrame.M3)
            
            # Create signal
            signal = TradeSignal(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                signal_strength=signal_strength,
                indicators=indicators or {}
            )
            
            # Check if similar signal was sent recently (avoid duplicates)
            signal_key = f"{symbol}_{direction}_{timeframe}"
            current_time = time.time()
            
            if signal_key in self.last_signal_time:
                time_since_last = current_time - self.last_signal_time[signal_key]
                if time_since_last < 300:  # 5 minutes cooldown
                    logger.info(f"⚠️ Skipping duplicate signal for {symbol} (last signal {int(time_since_last)}s ago)")
                    return False
            
            self.last_signal_time[signal_key] = current_time
            
            # Process signal immediately
            trade_plan = self.calculate_trade_plan(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                timeframe=timeframe_enum,
                risk_percent=self.risk_percent
            )
            
            # Display in console
            self.display_trade_plan(trade_plan)
            
            # Send to Telegram
            if self.telegram:
                success = self.telegram.send_trade_signal(trade_plan)
                if not success:
                    logger.error("❌ Failed to send signal to Telegram")
            
            # Execute trade
            trade_id = self.execute_trade(trade_plan)
            
            logger.info(f"✅ Signal processed: {symbol} {direction} at {entry_price}")
            return trade_id
            
        except Exception as e:
            logger.error(f"❌ Error processing signal: {e}")
            if self.telegram:
                self.telegram.send_message(f"❌ Error processing signal for {symbol}: {str(e)}")
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
        print(f"Risk Amount: ${trade_plan['risk_amount']:.2f} ({trade_plan['risk_percent']}%)")
        
        print("\n🎯 TAKE PROFIT LEVELS:")
        print("-"*40)
        for tp in trade_plan["take_profits"]:
            print(f"TP{tp['level']}: {tp['price']:.5f} ({tp['pips']:.1f} pips, {tp['rr_ratio']}:1 RR)")
        
        print("="*80)
    
    def execute_trade(self, trade_plan: Dict):
        """Execute a trade based on trade plan"""
        trade_id = f"{trade_plan['symbol']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"⚡ Executing trade: {trade_id}")
        logger.info(f"Direction: {trade_plan['direction']} at {trade_plan['entry_price']:.5f}")
        
        # Store trade
        self.active_trades[trade_id] = {
            **trade_plan,
            "trade_id": trade_id,
            "status": "ACTIVE",
            "entry_time": datetime.now(),
            "current_pnl": 0.0,
            "current_price": trade_plan['entry_price'],
            "max_profit": 0.0,
            "max_loss": 0.0
        }
        
        # Send Telegram notification
        if self.telegram:
            exec_msg = f"⚡ Trade EXECUTED\nSymbol: {trade_plan['symbol']}\nEntry: {trade_plan['entry_price']:.5f}"
            self.telegram.send_message(exec_msg, disable_notification=True)
        
        return trade_id
    
    def update_market_prices(self, market_data: Dict[str, float]):
        """Update all active trades with current market prices"""
        updated_trades = []
        
        for trade_id, trade in list(self.active_trades.items()):
            symbol = trade['symbol']
            
            if symbol in market_data:
                current_price = market_data[symbol]
                update_result = self.update_trade(trade_id, current_price)
                if update_result:
                    updated_trades.append(update_result)
        
        return updated_trades
    
    def update_trade(self, trade_id: str, current_price: float):
        """Update trade with current price"""
        if trade_id not in self.active_trades:
            return None
        
        trade = self.active_trades[trade_id]
        trade['current_price'] = current_price
        
        # Calculate current PnL
        if trade["direction"] == "LONG":
            pips = (current_price - trade["entry_price"]) / self.risk_manager.calculate_pip_size(trade['symbol']) * 10000
            pnl = pips * trade["position_size"] * trade["pip_value"]
        else:  # SHORT
            pips = (trade["entry_price"] - current_price) / self.risk_manager.calculate_pip_size(trade['symbol']) * 10000
            pnl = pips * trade["position_size"] * trade["pip_value"]
        
        trade["current_pips"] = pips
        trade["current_pnl"] = pnl
        
        # Track max profit/loss
        if pnl > trade["max_profit"]:
            trade["max_profit"] = pnl
        if pnl < trade["max_loss"]:
            trade["max_loss"] = pnl
        
        # Check exit conditions
        exit_reason = None
        
        # Check stop loss
        if trade["direction"] == "LONG" and current_price <= trade["stop_loss"]:
            exit_reason = "STOP_LOSS"
        elif trade["direction"] == "SHORT" and current_price >= trade["stop_loss"]:
            exit_reason = "STOP_LOSS"
        
        # Check take profits
        if not exit_reason:
            for tp in trade["take_profits"]:
                if trade["direction"] == "LONG" and current_price >= tp["price"]:
                    exit_reason = f"TP{tp['level']}"
                    break
                elif trade["direction"] == "SHORT" and current_price <= tp["price"]:
                    exit_reason = f"TP{tp['level']}"
                    break
        
        if exit_reason:
            self.close_trade(trade_id, current_price, exit_reason)
            return None
        
        # Send periodic update to Telegram (every significant move)
        if self.telegram and abs(pnl) > trade["risk_amount"] * 0.25:  # 25% of risk amount
            # Only send if we haven't sent an update recently for this trade
            update_key = f"{trade_id}_update"
            current_time = time.time()
            
            if update_key not in trade.get('_last_update', {}):
                trade['_last_update'] = {}
            
            last_update_time = trade['_last_update'].get(update_key, 0)
            
            if current_time - last_update_time > 300:  # 5 minutes cooldown
                if self.telegram.send_trade_update(trade_id, trade['symbol'], "UPDATE", pnl, current_price):
                    trade['_last_update'][update_key] = current_time
        
        return {
            "trade_id": trade_id,
            "symbol": trade['symbol'],
            "current_price": current_price,
            "current_pips": pips,
            "current_pnl": pnl,
            "exit_reason": exit_reason
        }
    
    def close_trade(self, trade_id: str, exit_price: float, exit_reason: str):
        """Close a trade"""
        if trade_id not in self.active_trades:
            return
        
        trade = self.active_trades[trade_id]
        
        # Calculate final PnL
        if trade["direction"] == "LONG":
            pips = (exit_price - trade["entry_price"]) / self.risk_manager.calculate_pip_size(trade['symbol']) * 10000
            pnl = pips * trade["position_size"] * trade["pip_value"]
        else:  # SHORT
            pips = (trade["entry_price"] - exit_price) / self.risk_manager.calculate_pip_size(trade['symbol']) * 10000
            pnl = pips * trade["position_size"] * trade["pip_value"]
        
        # Update account balance
        self.account_balance += pnl
        
        # Log
        logger.info(f"📊 Trade {trade_id} closed: {exit_reason}")
        logger.info(f"Exit Price: {exit_price:.5f}")
        logger.info(f"Pips: {pips:.1f}")
        logger.info(f"PnL: ${pnl:.2f}")
        logger.info(f"New Balance: ${self.account_balance:.2f}")
        
        # Send Telegram notification
        if self.telegram:
            self.telegram.send_trade_closed(trade_id, trade['symbol'], exit_reason, exit_price, pnl, pips)
        
        # Remove from active trades
        del self.active_trades[trade_id]
        
        # Send account update
        if self.telegram and len(self.active_trades) == 0:
            time.sleep(1)  # Small delay
            self.telegram.send_message(
                f"📈 Account Update\nCurrent Balance: ${self.account_balance:.2f}\n"
                f"Active Trades: {len(self.active_trades)}",
                disable_notification=True
            )
    
    def get_active_trades_summary(self):
        """Get summary of all active trades"""
        summary = []
        total_pnl = 0
        
        for trade_id, trade in self.active_trades.items():
            summary.append({
                "trade_id": trade_id,
                "symbol": trade['symbol'],
                "direction": trade['direction'],
                "entry_price": trade['entry_price'],
                "current_price": trade.get('current_price', trade['entry_price']),
                "pnl": trade.get('current_pnl', 0),
                "status": trade.get('status', 'ACTIVE')
            })
            total_pnl += trade.get('current_pnl', 0)
        
        return {
            "total_trades": len(self.active_trades),
            "total_pnl": total_pnl,
            "trades": summary
        }

def simulate_market_data():
    """Generate simulated market data for testing"""
    symbols = ["EURUSD", "BTCUSD", "ETHUSD", "EURCAD", "XAUUSD", "SOLUSD"]
    market_data = {}
    
    base_prices = {
        "EURUSD": 1.08500,
        "BTCUSD": 45000,
        "ETHUSD": 2500,
        "EURCAD": 1.61159,
        "XAUUSD": 1835.0,
        "SOLUSD": 100.0
    }
    
    for symbol in symbols:
        if symbol in base_prices:
            # Add random walk
            change = random.uniform(-0.002, 0.002)
            if "BTC" in symbol or "ETH" in symbol or "SOL" in symbol:
                change *= 100  # Larger moves for crypto
            market_data[symbol] = base_prices[symbol] * (1 + change)
    
    return market_data

def main():
    """Main trading bot with Telegram integration"""
    
    # Your Telegram Credentials
    TELEGRAM_BOT_TOKEN = "8276762810:AAFR_9TxacZPIhx_n3ohc_tdDgp6p1WQFOI"
    TELEGRAM_CHAT_ID = "-1003587493551"
    
    # Validate credentials
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.error("❌ Please set your Telegram Bot Token")
        return
    
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID_HERE":
        logger.error("❌ Please set your Telegram Chat ID")
        return
    
    print("\n" + "="*80)
    print("🤖 ADAPTIVE TRADING BOT WITH TELEGRAM")
    print("="*80)
    print(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    print(f"Bot Token: {TELEGRAM_BOT_TOKEN[:10]}...")
    print("="*80)
    
    # Initialize bot
    bot = AdaptiveTradingBot(
        account_balance=10000.0,
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        risk_percent=1.0  # 1% risk per trade
    )
    
    # Test signals from your original image
    print("\n📡 Processing Test Signals...")
    print("-"*40)
    
    # Signal 1: EURCAD Short on 3M (from your image)
    print("\n1. EURCAD Short Signal (3-minute)")
    bot.add_signal(
        symbol="EURCAD",
        direction="SHORT",
        entry_price=1.61159,
        timeframe="3M",
        signal_strength=85.0,
        indicators={"RSI": 65, "MACD": "bearish"}
    )
    
    time.sleep(2)  # Small delay between signals
    
    # Signal 2: BTCUSD Long on 1H
    print("\n2. BTCUSD Long Signal (1-hour)")
    bot.add_signal(
        symbol="BTCUSD",
        direction="LONG",
        entry_price=87832.0,
        timeframe="1H",
        signal_strength=75.0,
        indicators={"Volume": "high", "Trend": "bullish"}
    )
    
    time.sleep(2)
    
    # Signal 3: ETHUSD Short on 15M
    print("\n3. ETHUSD Short Signal (15-minute)")
    bot.add_signal(
        symbol="ETHUSD",
        direction="SHORT",
        entry_price=2972.0,
        timeframe="15M",
        signal_strength=70.0,
        indicators={"Stoch": "overbought"}
    )
    
    time.sleep(2)
    
    # Signal 4: XAUUSD Long on 4H
    print("\n4. XAUUSD Long Signal (4-hour)")
    bot.add_signal(
        symbol="XAUUSD",
        direction="LONG",
        entry_price=1835.0,
        timeframe="4H",
        signal_strength=80.0,
        indicators={"Support": "strong"}
    )
    
    # Simulate market updates
    print("\n" + "="*80)
    print("📈 Simulating Market Updates...")
    print("="*80)
    
    for i in range(20):  # Run for 20 updates
        # Generate simulated market data
        market_data = simulate_market_data()
        
        # Update trades with current prices
        updates = bot.update_market_prices(market_data)
        
        # Display active trades
        summary = bot.get_active_trades_summary()
        if summary['total_trades'] > 0:
            print(f"\nUpdate {i+1}: {summary['total_trades']} active trades")
            print(f"Total P&L: ${summary['total_pnl']:.2f}")
        
        # If no more active trades, break early
        if summary['total_trades'] == 0:
            print("\n✅ All trades closed")
            break
        
        time.sleep(2)  # Wait 2 seconds between updates
    
    # Final account status
    print("\n" + "="*80)
    print("📊 FINAL ACCOUNT STATUS")
    print("="*80)
    print(f"Account Balance: ${bot.account_balance:.2f}")
    print(f"Total P&L: ${bot.account_balance - 10000:.2f}")
    print(f"Return: {(bot.account_balance - 10000) / 10000 * 100:.2f}%")
    print("="*80)
    
    # Send final update to Telegram
    if bot.telegram:
        bot.telegram.send_message(
            f"📊 Trading Session Completed\n"
            f"Final Balance: ${bot.account_balance:.2f}\n"
            f"Total P&L: ${bot.account_balance - 10000:.2f}\n"
            f"Return: {(bot.account_balance - 10000) / 10000 * 100:.2f}%\n\n"
            f"Bot shutting down...",
            disable_notification=False
        )
    
    print("\n✅ Bot execution completed successfully!")
    print("📱 Check your Telegram for all trade signals and updates!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()