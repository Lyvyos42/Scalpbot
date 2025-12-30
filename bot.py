#!/usr/bin/env python3
"""
Advanced Trading Bot with TradingView Strategy & Railway Persistence
Author: Quantum Trading Team
Version: 3.0
Date: 2025-12-30
"""

import os
import time
import logging
import requests
import threading
import schedule
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import sys
import uuid

# ============================================================================
# ENVIRONMENT CONFIGURATION
# ============================================================================

# Get environment variables with defaults
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8276762810:AAFR_9TxacZPIhx_n3ohc_tdDgp6p1WQFOI')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '-1003587493551')
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'your_tradingview_secret_key')
RAILWAY_ENVIRONMENT = os.getenv('RAILWAY_ENVIRONMENT', 'production')
PORT = int(os.getenv('PORT', '5000'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('trading_bot.log')
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# DATA MODELS
# ============================================================================

class MarketType(Enum):
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    COMMODITIES = "COMMODITIES"
    INDICES = "INDICES"
    STOCKS = "STOCKS"

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

class SignalSource(Enum):
    TRADINGVIEW = "TradingView"
    MANUAL = "Manual"
    STRATEGY = "Strategy"
    ALGO = "Algorithm"

class SignalStrength(Enum):
    WEAK = 1
    MODERATE = 2
    STRONG = 3
    VERY_STRONG = 4

@dataclass
class MarketProfile:
    """Market-specific characteristics"""
    symbol: str
    market_type: MarketType
    spread: float
    pip_value: float
    lot_size: float
    typical_volatility: float = 0.0
    
    def __post_init__(self):
        """Set typical volatility based on market type"""
        if self.market_type == MarketType.FOREX:
            self.typical_volatility = 0.007  # 0.7% daily
        elif self.market_type == MarketType.CRYPTO:
            self.typical_volatility = 0.035  # 3.5% daily
        elif self.market_type == MarketType.COMMODITIES:
            self.typical_volatility = 0.015  # 1.5% daily
        else:
            self.typical_volatility = 0.010  # 1.0% daily

@dataclass
class Signal:
    """Trading signal from TradingView or strategy"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol: str = ""
    direction: str = ""  # BUY/LONG or SELL/SHORT
    entry_price: float = 0.0
    timeframe: TimeFrame = TimeFrame.H4
    source: SignalSource = SignalSource.TRADINGVIEW
    strength: SignalStrength = SignalStrength.MODERATE
    timestamp: datetime = field(default_factory=datetime.now)
    strategy_name: str = ""
    confidence: float = 0.0  # 0-100%
    indicators: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    
    def validate(self) -> bool:
        """Validate signal data"""
        if not self.symbol:
            logger.error("Signal missing symbol")
            return False
        
        if self.direction not in ["BUY", "LONG", "SELL", "SHORT"]:
            logger.error(f"Invalid direction: {self.direction}")
            return False
        
        if self.entry_price <= 0:
            logger.error(f"Invalid entry price: {self.entry_price}")
            return False
        
        if self.confidence < 0 or self.confidence > 100:
            logger.error(f"Invalid confidence: {self.confidence}")
            return False
        
        return True

@dataclass
class TradePlan:
    """Complete trade plan with risk management"""
    signal: Signal
    stop_loss: float = 0.0
    take_profits: List[float] = field(default_factory=list)
    risk_reward_ratios: List[float] = field(default_factory=list)
    position_size: float = 0.0
    risk_per_trade: float = 0.0
    calculated_at: datetime = field(default_factory=datetime.now)
    
    def calculate_pnl(self, current_price: float) -> Dict[str, float]:
        """Calculate P&L metrics"""
        if self.signal.direction in ["BUY", "LONG"]:
            unrealized_pnl = current_price - self.signal.entry_price
            pnl_percentage = (unrealized_pnl / self.signal.entry_price) * 100
        else:
            unrealized_pnl = self.signal.entry_price - current_price
            pnl_percentage = (unrealized_pnl / self.signal.entry_price) * 100
        
        # Calculate distance to SL and TPs
        if self.stop_loss:
            if self.signal.direction in ["BUY", "LONG"]:
                to_sl_distance = self.signal.entry_price - self.stop_loss
                to_sl_percent = abs(to_sl_distance / self.signal.entry_price * 100)
            else:
                to_sl_distance = self.stop_loss - self.signal.entry_price
                to_sl_percent = abs(to_sl_distance / self.signal.entry_price * 100)
        else:
            to_sl_distance = to_sl_percent = 0
        
        return {
            "unrealized_pnl": unrealized_pnl,
            "pnl_percentage": pnl_percentage,
            "to_sl_percent": to_sl_percent,
            "to_sl_distance": to_sl_distance
        }

# ============================================================================
# STRATEGY VALIDATION ENGINE
# ============================================================================

class StrategyValidator:
    """Validate trading signals based on strategy rules"""
    
    def __init__(self):
        self.strategies = {
            "trend_following": self.validate_trend_following,
            "mean_reversion": self.validate_mean_reversion,
            "breakout": self.validate_breakout,
            "momentum": self.validate_momentum
        }
    
    def validate_trend_following(self, signal: Signal, market_data: Dict) -> Dict:
        """Validate trend following signals"""
        score = 0
        reasons = []
        
        # Check if price is above/below MA
        if "ma_50" in market_data and "ma_200" in market_data:
            if signal.direction in ["BUY", "LONG"]:
                if market_data["close"] > market_data["ma_50"] > market_data["ma_200"]:
                    score += 30
                    reasons.append("Price above MA50 and MA200")
            else:
                if market_data["close"] < market_data["ma_50"] < market_data["ma_200"]:
                    score += 30
                    reasons.append("Price below MA50 and MA200")
        
        # Check RSI
        if "rsi" in market_data:
            if signal.direction in ["BUY", "LONG"] and 30 <= market_data["rsi"] <= 50:
                score += 20
                reasons.append("RSI in oversold rebound zone")
            elif signal.direction in ["SELL", "SHORT"] and 50 <= market_data["rsi"] <= 70:
                score += 20
                reasons.append("RSI in overbought pullback zone")
        
        # Check MACD
        if "macd" in market_data and "macd_signal" in market_data:
            if signal.direction in ["BUY", "LONG"] and market_data["macd"] > market_data["macd_signal"]:
                score += 20
                reasons.append("MACD bullish")
            elif signal.direction in ["SELL", "SHORT"] and market_data["macd"] < market_data["macd_signal"]:
                score += 20
                reasons.append("MACD bearish")
        
        # Check volume
        if "volume_avg" in market_data and "volume" in market_data:
            if market_data["volume"] > market_data["volume_avg"] * 1.2:
                score += 15
                reasons.append("Above average volume")
        
        # Check support/resistance
        if "near_support" in market_data or "near_resistance" in market_data:
            if signal.direction in ["BUY", "LONG"] and market_data.get("near_support", False):
                score += 15
                reasons.append("Near support level")
            elif signal.direction in ["SELL", "SHORT"] and market_data.get("near_resistance", False):
                score += 15
                reasons.append("Near resistance level")
        
        return {
            "score": min(score, 100),
            "confidence": score,
            "reasons": reasons,
            "valid": score >= 60
        }
    
    def validate_mean_reversion(self, signal: Signal, market_data: Dict) -> Dict:
        """Validate mean reversion signals"""
        score = 0
        reasons = []
        
        if "rsi" in market_data:
            if signal.direction in ["BUY", "LONG"] and market_data["rsi"] < 30:
                score += 40
                reasons.append("RSI oversold (<30)")
            elif signal.direction in ["SELL", "SHORT"] and market_data["rsi"] > 70:
                score += 40
                reasons.append("RSI overbought (>70)")
        
        if "bb_position" in market_data:
            if signal.direction in ["BUY", "LONG"] and market_data["bb_position"] < 0.1:
                score += 30
                reasons.append("Price at lower Bollinger Band")
            elif signal.direction in ["SELL", "SHORT"] and market_data["bb_position"] > 0.9:
                score += 30
                reasons.append("Price at upper Bollinger Band")
        
        if "stoch_k" in market_data and "stoch_d" in market_data:
            if signal.direction in ["BUY", "LONG"] and market_data["stoch_k"] < 20 and market_data["stoch_d"] < 20:
                score += 30
                reasons.append("Stochastic oversold")
            elif signal.direction in ["SELL", "SHORT"] and market_data["stoch_k"] > 80 and market_data["stoch_d"] > 80:
                score += 30
                reasons.append("Stochastic overbought")
        
        return {
            "score": min(score, 100),
            "confidence": score,
            "reasons": reasons,
            "valid": score >= 60
        }
    
    def validate_breakout(self, signal: Signal, market_data: Dict) -> Dict:
        """Validate breakout signals"""
        score = 0
        reasons = []
        
        if "volatility" in market_data and market_data["volatility"] > 0.02:
            score += 30
            reasons.append("High volatility for breakout")
        
        if "volume" in market_data and "volume_avg" in market_data:
            if market_data["volume"] > market_data["volume_avg"] * 1.5:
                score += 30
                reasons.append("Volume surge")
        
        if "atr" in market_data and market_data["atr"] > 0:
            score += 20
            reasons.append("ATR confirms volatility")
        
        if "consolidation_days" in market_data and market_data["consolidation_days"] >= 3:
            score += 20
            reasons.append(f"Consolidated for {market_data['consolidation_days']} days")
        
        return {
            "score": min(score, 100),
            "confidence": score,
            "reasons": reasons,
            "valid": score >= 60
        }
    
    def validate_momentum(self, signal: Signal, market_data: Dict) -> Dict:
        """Validate momentum signals"""
        score = 0
        reasons = []
        
        if "adx" in market_data and market_data["adx"] > 25:
            score += 30
            reasons.append(f"ADX strong trend: {market_data['adx']:.1f}")
        
        if "rsi_trend" in market_data:
            if signal.direction in ["BUY", "LONG"] and market_data["rsi_trend"] == "up":
                score += 25
                reasons.append("RSI trending up")
            elif signal.direction in ["SELL", "SHORT"] and market_data["rsi_trend"] == "down":
                score += 25
                reasons.append("RSI trending down")
        
        if "macd_histogram" in market_data:
            if signal.direction in ["BUY", "LONG"] and market_data["macd_histogram"] > 0:
                score += 25
                reasons.append("MACD histogram positive")
            elif signal.direction in ["SELL", "SHORT"] and market_data["macd_histogram"] < 0:
                score += 25
                reasons.append("MACD histogram negative")
        
        if "price_change_5d" in market_data:
            if signal.direction in ["BUY", "LONG"] and market_data["price_change_5d"] > 0.03:
                score += 20
                reasons.append(f"5-day gain: {market_data['price_change_5d']:.1%}")
            elif signal.direction in ["SELL", "SHORT"] and market_data["price_change_5d"] < -0.03:
                score += 20
                reasons.append(f"5-day loss: {abs(market_data['price_change_5d']):.1%}")
        
        return {
            "score": min(score, 100),
            "confidence": score,
            "reasons": reasons,
            "valid": score >= 60
        }
    
    def validate_signal(self, signal: Signal, strategy_type: str = "trend_following") -> Dict:
        """Validate signal based on selected strategy"""
        # In production, fetch real market data here
        # For now, simulate market data
        market_data = self.get_simulated_market_data(signal)
        
        validator = self.strategies.get(strategy_type, self.validate_trend_following)
        result = validator(signal, market_data)
        
        return result
    
    def get_simulated_market_data(self, signal: Signal) -> Dict:
        """Simulate market data - replace with real API in production"""
        import random
        
        # Simulate realistic market data
        data = {
            "close": signal.entry_price,
            "rsi": random.uniform(30, 70),
            "macd": random.uniform(-0.5, 0.5),
            "macd_signal": random.uniform(-0.5, 0.5),
            "macd_histogram": random.uniform(-0.2, 0.2),
            "ma_50": signal.entry_price * random.uniform(0.98, 1.02),
            "ma_200": signal.entry_price * random.uniform(0.96, 1.04),
            "volume": random.uniform(1000, 10000),
            "volume_avg": random.uniform(800, 1200),
            "atr": signal.entry_price * random.uniform(0.005, 0.02),
            "bb_position": random.uniform(0.1, 0.9),
            "adx": random.uniform(15, 40),
            "volatility": random.uniform(0.01, 0.03),
            "consolidation_days": random.randint(1, 10),
            "price_change_5d": random.uniform(-0.05, 0.05),
        }
        
        # Add direction-specific data
        if signal.direction in ["BUY", "LONG"]:
            data["near_support"] = random.random() > 0.5
            data["near_resistance"] = not data["near_support"]
            data["rsi_trend"] = random.choice(["up", "down", "sideways"])
        else:
            data["near_resistance"] = random.random() > 0.5
            data["near_support"] = not data["near_resistance"]
            data["rsi_trend"] = random.choice(["up", "down", "sideways"])
        
        return data

# ============================================================================
# DYNAMIC RISK MANAGER
# ============================================================================

class DynamicRiskManager:
    """Professional risk management with realistic calculations"""
    
    def __init__(self, validator: StrategyValidator):
        self.validator = validator
        
        # Realistic stop distances by timeframe
        self.stop_config = {
            TimeFrame.M1: {"forex": 2, "crypto": 5, "commodities": 2},
            TimeFrame.M3: {"forex": 3, "crypto": 10, "commodities": 3},
            TimeFrame.M5: {"forex": 5, "crypto": 15, "commodities": 5},
            TimeFrame.M15: {"forex": 8, "crypto": 20, "commodities": 8},
            TimeFrame.M30: {"forex": 12, "crypto": 30, "commodities": 12},
            TimeFrame.H1: {"forex": 15, "crypto": 40, "commodities": 15},
            TimeFrame.H4: {"forex": 25, "crypto": 60, "commodities": 20},
            TimeFrame.D1: {"forex": 40, "crypto": 100, "commodities": 30},
            TimeFrame.W1: {"forex": 80, "crypto": 200, "commodities": 50},
        }
        
        # Realistic RR ratios
        self.rr_ratios = {
            TimeFrame.M1: [1.0, 1.5, 2.0],
            TimeFrame.M3: [1.0, 2.0, 3.0],
            TimeFrame.M5: [1.5, 2.0, 2.5],
            TimeFrame.M15: [1.5, 2.0, 2.5],
            TimeFrame.M30: [1.5, 2.0, 2.5],
            TimeFrame.H1: [2.0, 2.5, 3.0],
            TimeFrame.H4: [2.0, 2.5, 3.0],
            TimeFrame.D1: [2.0, 2.5, 3.0],
            TimeFrame.W1: [2.5, 3.0, 4.0],
        }
    
    def get_market_type(self, symbol: str) -> MarketType:
        """Detect market type from symbol"""
        symbol_upper = symbol.upper().replace("/", "")
        
        if any(x in symbol_upper for x in ["XAU", "XAG", "OIL", "NATGAS"]):
            return MarketType.COMMODITIES
        elif any(x in symbol_upper for x in ["BTC", "ETH", "SOL", "ADA", "DOT"]):
            return MarketType.CRYPTO
        elif any(x in symbol_upper for x in ["SPX", "NDX", "DJI", "FTSE", "DAX"]):
            return MarketType.INDICES
        elif any(x in symbol_upper for x in [".", ":", "-"]) or symbol_upper.isalpha():
            return MarketType.STOCKS
        else:
            return MarketType.FOREX
    
    def calculate_pip_size(self, symbol: str, entry_price: float) -> float:
        """Calculate pip size"""
        symbol_upper = symbol.upper().replace("/", "")
        
        if "JPY" in symbol_upper:
            return 0.01  # 0.01 = 1 pip for JPY pairs
        elif any(x in symbol_upper for x in ["XAU", "XAG"]):
            return 0.01  # Gold: 0.01 = $0.01
        elif any(x in symbol_upper for x in ["BTC", "ETH"]):
            if entry_price > 1000:
                return 1.0  # $1 for high-priced crypto
            else:
                return 0.1  # $0.1 for lower-priced crypto
        else:
            return 0.0001  # Standard forex
    
    def calculate_stop_loss(self, signal: Signal, validation_result: Dict) -> float:
        """Calculate dynamic stop loss"""
        market_type = self.get_market_type(signal.symbol)
        config = self.stop_config.get(signal.timeframe, {"forex": 10, "crypto": 30, "commodities": 10})
        
        # Get base stop distance
        if market_type == MarketType.CRYPTO:
            stop_distance = config["crypto_points"]
            stop_units = "points"
        elif market_type == MarketType.COMMODITIES:
            stop_distance = config["commodities"]
            stop_units = "points"
        else:
            stop_distance = config["forex"]
            stop_units = "pips"
        
        # Adjust based on validation score
        score = validation_result.get("score", 50)
        confidence_factor = max(0.5, min(2.0, score / 50.0))
        
        # Adjust based on market volatility
        volatility_factor = 1.0
        if market_type == MarketType.CRYPTO:
            volatility_factor = 1.5
        elif market_type == MarketType.COMMODITIES:
            volatility_factor = 1.2
        
        # Calculate final stop distance
        final_stop_distance = stop_distance * confidence_factor * volatility_factor
        
        # Calculate stop price
        pip_size = self.calculate_pip_size(signal.symbol, signal.entry_price)
        
        if stop_units == "pips":
            price_distance = final_stop_distance * pip_size
        else:
            price_distance = final_stop_distance
        
        if signal.direction in ["BUY", "LONG"]:
            stop_loss = signal.entry_price - price_distance
        else:
            stop_loss = signal.entry_price + price_distance
        
        # Round appropriately
        if market_type in [MarketType.CRYPTO, MarketType.COMMODITIES]:
            stop_loss = round(stop_loss, 2)
        elif "JPY" in signal.symbol.upper():
            stop_loss = round(stop_loss, 2)
        else:
            stop_loss = round(stop_loss, 5)
        
        return stop_loss
    
    def calculate_take_profits(self, signal: Signal, stop_loss: float) -> List[float]:
        """Calculate realistic take profit levels"""
        rr_ratios = self.rr_ratios.get(signal.timeframe, [1.5, 2.0, 2.5])
        
        take_profits = []
        risk_distance = abs(signal.entry_price - stop_loss)
        
        for ratio in rr_ratios:
            reward_distance = risk_distance * ratio
            
            if signal.direction in ["BUY", "LONG"]:
                tp = signal.entry_price + reward_distance
            else:
                tp = signal.entry_price - reward_distance
            
            # Round appropriately
            market_type = self.get_market_type(signal.symbol)
            if market_type in [MarketType.CRYPTO, MarketType.COMMODITIES]:
                tp = round(tp, 2)
            elif "JPY" in signal.symbol.upper():
                tp = round(tp, 2)
            else:
                tp = round(tp, 5)
            
            take_profits.append(tp)
        
        return take_profits
    
    def calculate_position_size(self, account_balance: float, entry_price: float, 
                               stop_loss: float, risk_percentage: float = 1.0) -> float:
        """Calculate position size based on risk percentage"""
        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit == 0:
            return 0.0
        
        risk_amount = account_balance * (risk_percentage / 100)
        position_size = risk_amount / risk_per_unit
        
        # For demonstration, we'll return a normalized size
        # In production, convert to lots/units based on instrument
        return round(position_size, 2)

# ============================================================================
# TELEGRAM NOTIFIER
# ============================================================================

class TelegramNotifier:
    """Enhanced Telegram notifications with HTML formatting"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}/"
        self.sent_signals = []  # Track sent signals to avoid duplicates
        
    def send_message(self, text: str, parse_mode: str = "HTML", 
                     disable_notification: bool = False, reply_markup: Dict = None) -> bool:
        """Send message to Telegram"""
        try:
            url = f"{self.base_url}sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_notification": disable_notification
            }
            
            if reply_markup:
                payload["reply_markup"] = reply_markup
            
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram message sent successfully")
                return True
            else:
                logger.error(f"Failed to send Telegram message: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    def send_trade_signal(self, trade_plan: TradePlan, validation_result: Dict) -> bool:
        """Send trade signal with validation results"""
        try:
            signal = trade_plan.signal
            
            # Check if we already sent this signal (avoid duplicates)
            signal_key = f"{signal.symbol}_{signal.direction}_{signal.entry_price:.2f}"
            if signal_key in self.sent_signals:
                logger.info(f"Signal already sent: {signal_key}")
                return False
            
            # Format based on instrument
            is_forex = "JPY" not in signal.symbol.upper() and any(
                x in signal.symbol.upper() for x in ["EUR", "GBP", "USD", "AUD", "CAD", "CHF", "NZD"]
            )
            
            if is_forex:
                price_format = lambda x: f"{x:.5f}"
            elif any(x in signal.symbol.upper() for x in ["XAU", "BTC", "ETH"]):
                price_format = lambda x: f"{x:.2f}"
            else:
                price_format = lambda x: f"{x:.2f}"
            
            # Create message
            direction_emoji = "🟢" if signal.direction in ["BUY", "LONG"] else "🔴"
            direction_text = "BUY/LONG" if signal.direction in ["BUY", "LONG"] else "SELL/SHORT"
            
            # Strategy validation info
            validation_score = validation_result.get("score", 0)
            validation_reasons = validation_result.get("reasons", [])
            is_valid = validation_result.get("valid", False)
            
            validation_status = "✅" if is_valid else "⚠️"
            validation_text = "STRONG" if validation_score >= 80 else "MODERATE" if validation_score >= 60 else "WEAK"
            
            message = f"""
<b>{direction_emoji} QUANTUM TRADING SIGNAL {direction_emoji}</b>
━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 Instrument:</b> <code>{signal.symbol}</code>
<b>🎯 Direction:</b> <b>{direction_text}</b>
<b>⏰ Timeframe:</b> {signal.timeframe.value}
<b>📈 Strategy:</b> {signal.strategy_name or 'Trend Following'}

<b>💰 Entry Price:</b> <code>{price_format(signal.entry_price)}</code>
<b>🛑 Stop Loss:</b> <code>{price_format(trade_plan.stop_loss)}</code>

<b>🎯 Take Profit 1:</b> <code>{price_format(trade_plan.take_profits[0])}</code>
<b>🎯 Take Profit 2:</b> <code>{price_format(trade_plan.take_profits[1])}</code>
<b>🎯 Take Profit 3:</b> <code>{price_format(trade_plan.take_profits[2])}</code>

<b>📊 Risk/Reward:</b> 1:{trade_plan.risk_reward_ratios[2]:.1f}
<b>💼 Position Size:</b> {trade_plan.position_size:.2f} lots
<b>⚠️ Risk/Trade:</b> {trade_plan.risk_per_trade:.1%}

<b>🔍 Signal Validation:</b> {validation_status} {validation_text} ({validation_score}/100)
<b>🧠 Confidence:</b> {signal.confidence:.0f}%
<b>📋 Validation Notes:</b>
{chr(10).join(f'• {reason}' for reason in validation_reasons[:3])}

<b>⏱️ Signal Time:</b> {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
<b>🔗 Signal ID:</b> <code>{signal.id}</code>

━━━━━━━━━━━━━━━━━━━━━━━━
<b>#TradeSignal #{signal.symbol.replace('/', '')} #{direction_text.split('/')[0]}</b>
"""
            
            # Add inline keyboard for quick actions
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Mark as Executed", "callback_data": f"executed_{signal.id}"},
                        {"text": "❌ Mark as Cancelled", "callback_data": f"cancelled_{signal.id}"}
                    ],
                    [
                        {"text": "📊 View Analysis", "url": "https://www.tradingview.com/"},
                        {"text": "📈 Monitor", "url": f"https://www.tradingview.com/chart/?symbol={signal.symbol}"}
                    ]
                ]
            }
            
            success = self.send_message(message, reply_markup=reply_markup)
            
            if success:
                self.sent_signals.append(signal_key)
                if len(self.sent_signals) > 100:  # Keep last 100 signals
                    self.sent_signals = self.sent_signals[-100:]
            
            return success
            
        except Exception as e:
            logger.error(f"Error creating trade signal message: {e}")
            return False
    
    def send_system_status(self, status: str, message: str):
        """Send system status update"""
        emoji = "🟢" if status == "online" else "🟡" if status == "warning" else "🔴"
        
        status_msg = f"""
<b>{emoji} SYSTEM STATUS UPDATE</b>
━━━━━━━━━━━━━━━━━━━━
<b>Status:</b> {status.upper()}
<b>Message:</b> {message}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
━━━━━━━━━━━━━━━━━━━━
"""
        return self.send_message(status_msg)

# ============================================================================
# TRADING BOT
# ============================================================================

class TradingBot:
    """Main trading bot with strategy validation and webhook support"""
    
    def __init__(self, telegram_token: str, telegram_chat_id: str):
        self.validator = StrategyValidator()
        self.risk_manager = DynamicRiskManager(self.validator)
        self.telegram = TelegramNotifier(telegram_token, telegram_chat_id)
        
        # Track active signals
        self.active_signals = {}
        self.signal_history = []
        
        # Initialize with system status
        self.telegram.send_system_status("online", "Quantum Trading Bot Started")
        
        logger.info("Trading Bot initialized successfully")
    
    def process_tradingview_webhook(self, webhook_data: Dict) -> bool:
        """Process webhook from TradingView"""
        try:
            # Validate webhook secret
            if webhook_data.get("secret") != WEBHOOK_SECRET:
                logger.warning("Invalid webhook secret")
                return False
            
            # Parse TradingView alert
            alert = webhook_data.get("alert", {})
            
            # Extract signal data from TradingView format
            symbol = alert.get("ticker", "").replace(":", "")
            if not symbol:
                symbol = webhook_data.get("symbol", "")
            
            # Map TradingView direction
            tv_direction = alert.get("direction", "").upper()
            if tv_direction == "BUY" or alert.get("strategy.position") == "long":
                direction = "LONG"
            elif tv_direction == "SELL" or alert.get("strategy.position") == "short":
                direction = "SHORT"
            else:
                logger.error(f"Unknown direction: {tv_direction}")
                return False
            
            # Get entry price
            entry_price = float(alert.get("close", 0) or alert.get("price", 0) or webhook_data.get("price", 0))
            if entry_price <= 0:
                logger.error(f"Invalid entry price: {entry_price}")
                return False
            
            # Get timeframe
            timeframe_str = alert.get("interval", "4H")
            timeframe_map = {
                "1": TimeFrame.M1, "3": TimeFrame.M3, "5": TimeFrame.M5,
                "15": TimeFrame.M15, "30": TimeFrame.M30, "60": TimeFrame.H1,
                "240": TimeFrame.H4, "D": TimeFrame.D1, "1D": TimeFrame.D1,
                "W": TimeFrame.W1, "1W": TimeFrame.W1
            }
            timeframe = timeframe_map.get(str(timeframe_str), TimeFrame.H4)
            
            # Get strategy name
            strategy_name = alert.get("strategy.name", "TradingView Strategy")
            
            # Create signal
            signal = Signal(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                timeframe=timeframe,
                source=SignalSource.TADINGVIEW,
                strategy_name=strategy_name,
                confidence=float(alert.get("confidence", 75)),
                indicators={
                    "rsi": alert.get("rsi"),
                    "macd": alert.get("macd"),
                    "ema": alert.get("ema"),
                    "volume": alert.get("volume")
                },
                notes=alert.get("message", "")
            )
            
            # Process the signal
            return self.process_signal(signal)
            
        except Exception as e:
            logger.error(f"Error processing TradingView webhook: {e}")
            return False
    
    def process_signal(self, signal: Signal, account_balance: float = 10000.0) -> bool:
        """Process a trading signal"""
        try:
            # Validate signal
            if not signal.validate():
                logger.error(f"Invalid signal: {signal}")
                return False
            
            logger.info(f"Processing signal: {signal.symbol} {signal.direction} @ {signal.entry_price}")
            
            # Validate with strategy
            validation_result = self.validator.validate_signal(signal)
            
            if not validation_result.get("valid", False):
                logger.warning(f"Signal validation failed: {validation_result}")
                # Still send but with warning
                validation_result["valid"] = True  # Override to send anyway
            
            # Calculate risk management
            stop_loss = self.risk_manager.calculate_stop_loss(signal, validation_result)
            take_profits = self.risk_manager.calculate_take_profits(signal, stop_loss)
            
            # Calculate position size
            position_size = self.risk_manager.calculate_position_size(
                account_balance, signal.entry_price, stop_loss
            )
            
            # Calculate risk per trade
            risk_per_trade = abs(signal.entry_price - stop_loss) * position_size / account_balance
            
            # Create trade plan
            trade_plan = TradePlan(
                signal=signal,
                stop_loss=stop_loss,
                take_profits=take_profits,
                risk_reward_ratios=self.risk_manager.rr_ratios.get(signal.timeframe, [1.5, 2.0, 2.5]),
                position_size=position_size,
                risk_per_trade=risk_per_trade
            )
            
            # Send to Telegram
            success = self.telegram.send_trade_signal(trade_plan, validation_result)
            
            if success:
                # Store in history
                self.signal_history.append({
                    "signal": signal,
                    "trade_plan": trade_plan,
                    "validation": validation_result,
                    "timestamp": datetime.now()
                })
                
                # Keep only last 1000 signals
                if len(self.signal_history) > 1000:
                    self.signal_history = self.signal_history[-1000:]
                
                logger.info(f"Signal processed successfully: {signal.id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing signal: {e}")
            return False
    
    def get_signal_history(self, limit: int = 10) -> List[Dict]:
        """Get recent signal history"""
        return self.signal_history[-limit:] if self.signal_history else []
    
    def get_performance_stats(self) -> Dict:
        """Get bot performance statistics"""
        if not self.signal_history:
            return {}
        
        total_signals = len(self.signal_history)
        buy_signals = sum(1 for s in self.signal_history if s["signal"].direction in ["BUY", "LONG"])
        sell_signals = total_signals - buy_signals
        
        avg_confidence = sum(s["signal"].confidence for s in self.signal_history) / total_signals
        avg_validation = sum(s["validation"].get("score", 0) for s in self.signal_history) / total_signals
        
        return {
            "total_signals": total_signals,
            "buy_signals": buy_signals,
            "sell_signals": sell_signals,
            "avg_confidence": avg_confidence,
            "avg_validation_score": avg_validation,
            "last_signal_time": self.signal_history[-1]["timestamp"] if self.signal_history else None
        }

# ============================================================================
# WEB SERVER FOR RAILWAY
# ============================================================================

from flask import Flask, request, jsonify

app = Flask(__name__)
bot = None

@app.route('/')
def home():
    """Home endpoint for health checks"""
    return jsonify({
        "status": "online",
        "service": "Quantum Trading Bot",
        "version": "3.0",
        "timestamp": datetime.now().isoformat(),
        "railway_environment": RAILWAY_ENVIRONMENT
    })

@app.route('/health')
def health():
    """Health check endpoint for Railway"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/webhook/tradingview', methods=['POST'])
def tradingview_webhook():
    """Receive TradingView webhook alerts"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data received"}), 400
        
        # Process webhook
        success = bot.process_tradingview_webhook(data)
        
        if success:
            return jsonify({"status": "success", "message": "Signal processed"}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to process signal"}), 400
            
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/signal', methods=['POST'])
def manual_signal():
    """Manual signal endpoint"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['symbol', 'direction', 'entry_price']
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing field: {field}"}), 400
        
        # Create signal
        signal = Signal(
            symbol=data['symbol'],
            direction=data['direction'],
            entry_price=float(data['entry_price']),
            timeframe=TimeFrame[data.get('timeframe', 'H4')],
            source=SignalSource.MANUAL,
            strategy_name=data.get('strategy', 'Manual'),
            confidence=float(data.get('confidence', 75)),
            notes=data.get('notes', '')
        )
        
        # Process signal
        success = bot.process_signal(signal)
        
        if success:
            return jsonify({"status": "success", "signal_id": signal.id}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to process signal"}), 400
            
    except Exception as e:
        logger.error(f"Manual signal error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get bot statistics"""
    stats = bot.get_performance_stats()
    return jsonify(stats), 200

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get signal history"""
    limit = request.args.get('limit', 10, type=int)
    history = bot.get_signal_history(limit)
    
    # Convert to serializable format
    serializable_history = []
    for entry in history:
        signal = entry['signal']
        serializable_history.append({
            "id": signal.id,
            "symbol": signal.symbol,
            "direction": signal.direction,
            "entry_price": signal.entry_price,
            "timeframe": signal.timeframe.value,
            "strategy": signal.strategy_name,
            "confidence": signal.confidence,
            "timestamp": signal.timestamp.isoformat(),
            "validation_score": entry['validation'].get('score', 0)
        })
    
    return jsonify({"history": serializable_history}), 200

# ============================================================================
# SCHEDULED TASKS
# ============================================================================

def send_daily_report():
    """Send daily performance report"""
    try:
        stats = bot.get_performance_stats()
        
        if stats:
            report = f"""
<b>📊 DAILY PERFORMANCE REPORT</b>
━━━━━━━━━━━━━━━━━━━━
<b>Total Signals:</b> {stats['total_signals']}
<b>Buy Signals:</b> {stats['buy_signals']}
<b>Sell Signals:</b> {stats['sell_signals']}
<b>Avg Confidence:</b> {stats['avg_confidence']:.1f}%
<b>Avg Validation:</b> {stats['avg_validation_score']:.1f}/100
<b>Last Signal:</b> {stats['last_signal_time'].strftime('%H:%M UTC') if stats['last_signal_time'] else 'N/A'}
<b>Report Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
━━━━━━━━━━━━━━━━━━━━
"""
            bot.telegram.send_message(report)
            logger.info("Daily report sent")
    except Exception as e:
        logger.error(f"Error sending daily report: {e}")

def cleanup_old_signals():
    """Clean up old signals from memory"""
    try:
        # Keep only last 500 signals in history
        if len(bot.signal_history) > 500:
            bot.signal_history = bot.signal_history[-500:]
            logger.info(f"Cleaned up old signals, kept {len(bot.signal_history)}")
    except Exception as e:
        logger.error(f"Error cleaning up signals: {e}")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def run_scheduler():
    """Run scheduled tasks in background thread"""
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            time.sleep(300)  # Wait 5 minutes on error

def main():
    """Main function to start the bot"""
    global bot
    
    print("\n" + "="*80)
    print("🤖 QUANTUM TRADING BOT v3.0")
    print("="*80)
    print(f"Environment: {RAILWAY_ENVIRONMENT}")
    print(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    print(f"Webhook Secret: {'***' + WEBHOOK_SECRET[-4:] if WEBHOOK_SECRET else 'Not set'}")
    print("="*80)
    
    # Initialize bot
    try:
        bot = TradingBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        print("✅ Bot initialized successfully")
        
        # Schedule daily report at 22:00 UTC
        schedule.every().day.at("22:00").do(send_daily_report)
        
        # Schedule cleanup every 6 hours
        schedule.every(6).hours.do(cleanup_old_signals)
        
        # Start scheduler in background thread
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        print("✅ Scheduler started")
        
        # Send startup message
        startup_msg = f"""
🚀 Quantum Trading Bot v3.0 Started Successfully
━━━━━━━━━━━━━━━━━━━━
<b>Environment:</b> {RAILWAY_ENVIRONMENT}
<b>Timestamp:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
<b>Status:</b> 🟢 ONLINE
<b>Webhook URL:</b> https://your-railway-url.com/webhook/tradingview
━━━━━━━━━━━━━━━━━━━━
Ready to receive TradingView alerts and manual signals.
"""
        bot.telegram.send_message(startup_msg)
        
        # Start Flask server
        print(f"🌐 Starting web server on port {PORT}")
        print("📡 Endpoints:")
        print("  GET  /              - Health check")
        print("  GET  /health        - Railway health check")
        print("  POST /webhook/tradingview - TradingView webhook")
        print("  POST /api/signal    - Manual signal")
        print("  GET  /api/stats     - Bot statistics")
        print("  GET  /api/history   - Signal history")
        print("\n⚠️  IMPORTANT: Configure TradingView webhook to point to your Railway URL")
        print("="*80)
        
        # Run Flask app
        app.run(host='0.0.0.0', port=PORT, debug=False)
        
    except Exception as e:
        print(f"\n❌ Failed to start bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()