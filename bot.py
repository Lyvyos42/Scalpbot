import time
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import talib
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MarketType(Enum):
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    STOCKS = "STOCKS"
    COMMODITIES = "COMMODITIES"
    INDICES = "INDICES"

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
    MN1 = "1MN"

@dataclass
class MarketProfile:
    """Market-specific volatility and characteristics"""
    symbol: str
    market_type: MarketType
    avg_daily_range: float  # Average Daily Range in pips/points
    avg_true_range: float   # Current ATR
    volatility_rank: float  # 0-100 volatility ranking
    spread: float          # Typical spread
    pip_value: float       # Value of 1 pip in account currency
    lot_size: float = 100000  # Standard lot size
    
    def get_timeframe_multiplier(self, tf: TimeFrame) -> float:
        """Get volatility multiplier for specific timeframe"""
        multipliers = {
            TimeFrame.M1: 0.2,
            TimeFrame.M3: 0.3,
            TimeFrame.M5: 0.4,
            TimeFrame.M15: 0.6,
            TimeFrame.M30: 0.8,
            TimeFrame.H1: 1.0,
            TimeFrame.H4: 1.5,
            TimeFrame.D1: 2.0,
            TimeFrame.W1: 3.0,
            TimeFrame.MN1: 4.0
        }
        return multipliers.get(tf, 1.0)

@dataclass
class TradeSignal:
    """Trading signal with dynamic parameters"""
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    signal_strength: float  # 0-100
    confidence: float       # 0-1
    timestamp: datetime
    indicators: Dict = field(default_factory=dict)
    
class DynamicRiskManager:
    """Dynamic risk management across timeframes and markets"""
    
    def __init__(self):
        self.timeframe_config = {
            TimeFrame.M1: {"base_stop_pips": 3, "rr_ratios": [1.0, 2.0, 3.0]},
            TimeFrame.M3: {"base_stop_pips": 5, "rr_ratios": [1.5, 2.5, 3.5]},
            TimeFrame.M5: {"base_stop_pips": 8, "rr_ratios": [1.5, 2.5, 3.5]},
            TimeFrame.M15: {"base_stop_pips": 10, "rr_ratios": [2.0, 3.0, 4.0]},
            TimeFrame.M30: {"base_stop_pips": 15, "rr_ratios": [2.0, 3.0, 4.0]},
            TimeFrame.H1: {"base_stop_pips": 20, "rr_ratios": [2.5, 3.5, 5.0]},
            TimeFrame.H4: {"base_stop_pips": 30, "rr_ratios": [3.0, 4.0, 6.0]},
            TimeFrame.D1: {"base_stop_pips": 50, "rr_ratios": [3.0, 5.0, 8.0]},
            TimeFrame.W1: {"base_stop_pips": 100, "rr_ratios": [4.0, 6.0, 10.0]},
            TimeFrame.MN1: {"base_stop_pips": 200, "rr_ratios": [5.0, 8.0, 13.0]}
        }
        
        self.market_volatility_adjustments = {
            MarketType.FOREX: 1.0,
            MarketType.CRYPTO: 2.0,
            MarketType.STOCKS: 0.8,
            MarketType.COMMODITIES: 1.2,
            MarketType.INDICES: 1.5
        }
    
    def calculate_dynamic_stop_loss(self, 
                                   market_profile: MarketProfile,
                                   timeframe: TimeFrame,
                                   entry_price: float,
                                   direction: str) -> Dict:
        """
        Calculate dynamic stop loss based on market conditions and timeframe
        """
        # Base configuration for timeframe
        config = self.timeframe_config[timeframe]
        base_stop = config["base_stop_pips"]
        
        # Adjust for market volatility
        volatility_factor = self.market_volatility_adjustments.get(
            market_profile.market_type, 1.0
        )
        
        # Adjust for current ATR
        atr_factor = market_profile.avg_true_range / market_profile.avg_daily_range * 20
        
        # Calculate final stop loss in pips
        stop_pips = base_stop * volatility_factor * atr_factor
        
        # Apply market-specific adjustments
        if market_profile.market_type == MarketType.CRYPTO:
            stop_pips *= 1.5  # Higher volatility
        elif market_profile.market_type == MarketType.FOREX:
            stop_pips *= 1.0  # Standard
            
        # Ensure minimum stop loss
        min_stop = market_profile.spread * 3
        stop_pips = max(stop_pips, min_stop)
        
        # Calculate stop loss price
        pip_size = 0.0001 if "JPY" not in market_profile.symbol else 0.01
        stop_distance = stop_pips * pip_size
        
        if direction == "SHORT":
            stop_price = entry_price + stop_distance
        else:  # LONG
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
                              rr_ratios: List[float]) -> List[Dict]:
        """
        Calculate multiple take-profit levels
        """
        tp_levels = []
        pip_size = 0.0001  # Adjust based on symbol
        
        for i, ratio in enumerate(rr_ratios):
            tp_pips = stop_pips * ratio
            tp_distance = tp_pips * pip_size
            
            if direction == "SHORT":
                tp_price = entry_price - tp_distance
            else:  # LONG
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
                               market_profile: MarketProfile) -> float:
        """
        Calculate position size based on risk parameters
        """
        risk_amount = account_balance * (risk_percent / 100)
        
        # Risk per pip in account currency
        risk_per_pip = (risk_amount / stop_pips) if stop_pips > 0 else 0
        
        # Convert to lot size
        position_size = risk_per_pip / (market_profile.pip_value * 10)
        
        # Standardize to lot sizes
        if position_size < 0.01:
            position_size = 0.01  # Minimum micro lot
            
        return round(position_size, 2)

class MultiTimeframeAnalyzer:
    """Analyze all timeframes for optimal entry/exit points"""
    
    def __init__(self):
        self.support_resistance_levels = {}
        
    def analyze_timeframes(self, 
                          symbol: str,
                          price_data: Dict[TimeFrame, pd.DataFrame]) -> Dict:
        """
        Analyze all timeframes for the given symbol
        """
        analysis = {}
        
        for timeframe, data in price_data.items():
            if len(data) < 50:  # Need enough data
                continue
                
            # Calculate technical indicators
            close_prices = data['close'].values
            
            # Simple moving averages
            sma_20 = talib.SMA(close_prices, timeperiod=20)
            sma_50 = talib.SMA(close_prices, timeperiod=50)
            
            # RSI
            rsi = talib.RSI(close_prices, timeperiod=14)
            
            # ATR for volatility
            atr = talib.ATR(data['high'].values, 
                           data['low'].values, 
                           close_prices, 
                           timeperiod=14)
            
            # MACD
            macd, macd_signal, macd_hist = talib.MACD(close_prices)
            
            # Find support and resistance
            supports, resistances = self.find_support_resistance(data)
            
            analysis[timeframe] = {
                "sma_20": sma_20[-1] if not np.isnan(sma_20[-1]) else None,
                "sma_50": sma_50[-1] if not np.isnan(sma_50[-1]) else None,
                "rsi": rsi[-1] if not np.isnan(rsi[-1]) else None,
                "atr": atr[-1] if not np.isnan(atr[-1]) else None,
                "macd": {
                    "macd": macd[-1] if not np.isnan(macd[-1]) else None,
                    "signal": macd_signal[-1] if not np.isnan(macd_signal[-1]) else None,
                    "histogram": macd_hist[-1] if not np.isnan(macd_hist[-1]) else None
                },
                "supports": supports[-5:],  # Last 5 supports
                "resistances": resistances[-5:],  # Last 5 resistances
                "current_price": close_prices[-1],
                "volatility": np.std(close_prices[-20:]) if len(close_prices) >= 20 else 0
            }
            
        return analysis
    
    def find_support_resistance(self, data: pd.DataFrame) -> Tuple[List, List]:
        """
        Find support and resistance levels using pivot points
        """
        supports = []
        resistances = []
        
        if len(data) < 20:
            return supports, resistances
            
        highs = data['high'].values
        lows = data['low'].values
        
        for i in range(1, len(highs) - 1):
            # Local maximum (resistance)
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                resistances.append(highs[i])
            
            # Local minimum (support)
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                supports.append(lows[i])
                
        return supports, resistances
    
    def get_optimal_timeframe(self, analysis: Dict) -> TimeFrame:
        """
        Determine the optimal timeframe for entry based on multiple factors
        """
        timeframe_scores = {}
        
        for timeframe, data in analysis.items():
            score = 0
            
            # Higher volatility timeframes get higher score for active trading
            if timeframe in [TimeFrame.M1, TimeFrame.M3, TimeFrame.M5]:
                score += 30
            elif timeframe in [TimeFrame.M15, TimeFrame.M30]:
                score += 20
            elif timeframe == TimeFrame.H1:
                score += 15
                
            # Score based on RSI
            if data['rsi'] is not None:
                if data['rsi'] < 30 or data['rsi'] > 70:  # Overbought/oversold
                    score += 20
                    
            # Score based on MACD
            if data['macd']['histogram'] is not None:
                if abs(data['macd']['histogram']) > 0.001:  # Strong momentum
                    score += 15
                    
            timeframe_scores[timeframe] = score
            
        # Return timeframe with highest score
        return max(timeframe_scores, key=timeframe_scores.get)

class AdaptiveTradingBot:
    """Main trading bot with adaptive parameters for all timeframes and markets"""
    
    def __init__(self, account_balance: float = 10000.0):
        self.account_balance = account_balance
        self.risk_manager = DynamicRiskManager()
        self.analyzer = MultiTimeframeAnalyzer()
        self.active_trades = {}
        self.market_profiles = self.initialize_market_profiles()
        
        logger.info(f"Adaptive Trading Bot initialized with account balance: ${account_balance:,.2f}")
        
    def initialize_market_profiles(self) -> Dict[str, MarketProfile]:
        """Initialize market profiles for different symbols"""
        profiles = {
            # Forex pairs
            "EURUSD": MarketProfile(
                symbol="EURUSD",
                market_type=MarketType.FOREX,
                avg_daily_range=70.0,
                avg_true_range=8.5,
                volatility_rank=45.0,
                spread=0.0001,
                pip_value=10.0
            ),
            "GBPUSD": MarketProfile(
                symbol="GBPUSD",
                market_type=MarketType.FOREX,
                avg_daily_range=90.0,
                avg_true_range=10.2,
                volatility_rank=55.0,
                spread=0.00012,
                pip_value=10.0
            ),
            "USDJPY": MarketProfile(
                symbol="USDJPY",
                market_type=MarketType.FOREX,
                avg_daily_range=65.0,
                avg_true_range=7.8,
                volatility_rank=40.0,
                spread=0.01,
                pip_value=9.0
            ),
            "EURCAD": MarketProfile(
                symbol="EURCAD",
                market_type=MarketType.FOREX,
                avg_daily_range=85.0,
                avg_true_range=9.5,
                volatility_rank=50.0,
                spread=0.00015,
                pip_value=7.5
            ),
            # Cryptocurrencies
            "BTCUSD": MarketProfile(
                symbol="BTCUSD",
                market_type=MarketType.CRYPTO,
                avg_daily_range=3000.0,
                avg_true_range=350.0,
                volatility_rank=85.0,
                spread=5.0,
                pip_value=1.0,
                lot_size=1.0  # Crypto lot size
            ),
            "ETHUSD": MarketProfile(
                symbol="ETHUSD",
                market_type=MarketType.CRYPTO,
                avg_daily_range=150.0,
                avg_true_range=18.0,
                volatility_rank=75.0,
                spread=0.5,
                pip_value=1.0,
                lot_size=1.0
            ),
            # Stocks (example)
            "AAPL": MarketProfile(
                symbol="AAPL",
                market_type=MarketType.STOCKS,
                avg_daily_range=3.5,
                avg_true_range=0.42,
                volatility_rank=35.0,
                spread=0.01,
                pip_value=1.0,
                lot_size=100  # Stock lot size
            )
        }
        
        return profiles
    
    def process_signal(self, signal: TradeSignal, price_data: Dict) -> Optional[Dict]:
        """
        Process trading signal and generate trade parameters
        """
        if signal.symbol not in self.market_profiles:
            logger.error(f"No market profile for symbol: {signal.symbol}")
            return None
            
        # Get market profile
        market_profile = self.market_profiles[signal.symbol]
        
        # Analyze all timeframes
        timeframe_analysis = self.analyzer.analyze_timeframes(signal.symbol, price_data)
        
        if not timeframe_analysis:
            logger.error("No timeframe analysis available")
            return None
            
        # Get optimal timeframe for entry
        optimal_tf = self.analyzer.get_optimal_timeframe(timeframe_analysis)
        
        # Get analysis for optimal timeframe
        tf_analysis = timeframe_analysis[optimal_tf]
        
        # Adjust entry price based on timeframe analysis
        adjusted_entry = self.adjust_entry_price(
            signal.entry_price,
            signal.direction,
            tf_analysis
        )
        
        # Calculate dynamic stop loss
        stop_data = self.risk_manager.calculate_dynamic_stop_loss(
            market_profile=market_profile,
            timeframe=optimal_tf,
            entry_price=adjusted_entry,
            direction=signal.direction
        )
        
        # Get RR ratios for timeframe
        rr_ratios = self.risk_manager.timeframe_config[optimal_tf]["rr_ratios"]
        
        # Calculate take-profit levels
        tp_levels = self.risk_manager.calculate_take_profits(
            entry_price=adjusted_entry,
            stop_pips=stop_data["stop_pips"],
            direction=signal.direction,
            rr_ratios=rr_ratios
        )
        
        # Calculate position size
        position_size = self.risk_manager.calculate_position_size(
            account_balance=self.account_balance,
            risk_percent=1.0,  # 1% risk per trade
            stop_pips=stop_data["stop_pips"],
            market_profile=market_profile
        )
        
        # Create trade plan
        trade_plan = {
            "symbol": signal.symbol,
            "direction": signal.direction,
            "market_type": market_profile.market_type.value,
            "optimal_timeframe": optimal_tf.value,
            "entry_price": adjusted_entry,
            "original_signal_price": signal.entry_price,
            "stop_loss": stop_data["stop_loss"],
            "stop_pips": stop_data["stop_pips"],
            "take_profits": tp_levels,
            "position_size": position_size,
            "risk_amount": self.account_balance * 0.01,  # 1% risk
            "risk_reward_ratios": rr_ratios,
            "signal_strength": signal.signal_strength,
            "confidence": signal.confidence,
            "timestamp": datetime.now(),
            "timeframe_analysis": {
                tf.value: {
                    "current_price": analysis["current_price"],
                    "rsi": analysis["rsi"],
                    "atr": analysis["atr"],
                    "volatility": analysis["volatility"]
                } for tf, analysis in timeframe_analysis.items()
            }
        }
        
        # Log trade plan
        self.log_trade_plan(trade_plan)
        
        return trade_plan
    
    def adjust_entry_price(self, 
                          original_entry: float,
                          direction: str,
                          tf_analysis: Dict) -> float:
        """
        Adjust entry price based on support/resistance levels
        """
        adjusted_entry = original_entry
        
        # Use nearest support/resistance for better entry
        if direction == "LONG":
            supports = tf_analysis.get("supports", [])
            if supports:
                # Find closest support below current price
                valid_supports = [s for s in supports if s < original_entry]
                if valid_supports:
                    adjusted_entry = max(valid_supports)
                    
        elif direction == "SHORT":
            resistances = tf_analysis.get("resistances", [])
            if resistances:
                # Find closest resistance above current price
                valid_resistances = [r for r in resistances if r > original_entry]
                if valid_resistances:
                    adjusted_entry = min(valid_resistances)
                    
        return adjusted_entry
    
    def log_trade_plan(self, trade_plan: Dict):
        """Log detailed trade plan"""
        logger.info("=" * 80)
        logger.info("ADAPTIVE TRADE PLAN GENERATED")
        logger.info("=" * 80)
        logger.info(f"Symbol: {trade_plan['symbol']}")
        logger.info(f"Market Type: {trade_plan['market_type']}")
        logger.info(f"Direction: {trade_plan['direction']}")
        logger.info(f"Optimal Timeframe: {trade_plan['optimal_timeframe']}")
        logger.info(f"Entry Price: {trade_plan['entry_price']:.5f}")
        logger.info(f"Stop Loss: {trade_plan['stop_loss']:.5f} ({trade_plan['stop_pips']:.1f} pips)")
        logger.info(f"Position Size: {trade_plan['position_size']:.2f} lots")
        logger.info(f"Risk Amount: ${trade_plan['risk_amount']:.2f}")
        
        for tp in trade_plan["take_profits"]:
            logger.info(f"TP{tp['level']}: {tp['price']:.5f} ({tp['pips']:.1f} pips, {tp['rr_ratio']}:1 RR)")
            
        logger.info(f"Signal Strength: {trade_plan['signal_strength']}/100")
        logger.info(f"Confidence: {trade_plan['confidence']*100:.1f}%")
        logger.info("=" * 80)
        
        # Log timeframe analysis summary
        logger.info("TIMEFRAME ANALYSIS SUMMARY:")
        for tf, data in trade_plan["timeframe_analysis"].items():
            logger.info(f"  {tf}: Price={data['current_price']:.5f}, "
                       f"RSI={data['rsi']:.1f if data['rsi'] else 'N/A'}, "
                       f"ATR={data['atr']:.5f if data['atr'] else 'N/A'}")
    
    def execute_trade(self, trade_plan: Dict):
        """Execute the trade (simulated for this example)"""
        trade_id = f"{trade_plan['symbol']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Simulate trade execution
        logger.info(f"Executing trade {trade_id}")
        
        # Store trade information
        self.active_trades[trade_id] = {
            **trade_plan,
            "trade_id": trade_id,
            "status": "ACTIVE",
            "entry_time": datetime.now(),
            "current_pnl": 0.0
        }
        
        return trade_id
    
    def monitor_trades(self):
        """Monitor all active trades (simulated)"""
        while self.active_trades:
            for trade_id, trade in list(self.active_trades.items()):
                # Simulate price movement (in real implementation, get from market data)
                current_price = self.simulate_price_movement(trade)
                
                # Check exit conditions
                self.check_exit_conditions(trade_id, current_price)
                
                # Update PnL
                self.update_pnl(trade_id, current_price)
                
            time.sleep(1)  # Simulate monitoring interval
    
    def simulate_price_movement(self, trade: Dict) -> float:
        """Simulate price movement for demo purposes"""
        base_price = trade["entry_price"]
        direction = 1 if trade["direction"] == "LONG" else -1
        
        # Simulate random walk
        movement = np.random.randn() * trade["stop_pips"] * 0.0001 * 0.1
        
        return base_price + (direction * movement)
    
    def check_exit_conditions(self, trade_id: str, current_price: float):
        """Check if exit conditions are met"""
        trade = self.active_trades[trade_id]
        
        # Check stop loss
        if trade["direction"] == "LONG" and current_price <= trade["stop_loss"]:
            self.exit_trade(trade_id, current_price, "STOP_LOSS")
            return
            
        if trade["direction"] == "SHORT" and current_price >= trade["stop_loss"]:
            self.exit_trade(trade_id, current_price, "STOP_LOSS")
            return
            
        # Check take profits
        for tp in trade["take_profits"]:
            if trade["direction"] == "LONG" and current_price >= tp["price"]:
                self.exit_trade(trade_id, current_price, f"TP{tp['level']}")
                return
                
            if trade["direction"] == "SHORT" and current_price <= tp["price"]:
                self.exit_trade(trade_id, current_price, f"TP{tp['level']}")
                return
    
    def exit_trade(self, trade_id: str, exit_price: float, exit_reason: str):
        """Exit a trade"""
        trade = self.active_trades[trade_id]
        
        # Calculate PnL
        if trade["direction"] == "LONG":
            pips = (exit_price - trade["entry_price"]) * 10000
            pnl = pips * trade["position_size"] * trade.get("pip_value", 10.0)
        else:  # SHORT
            pips = (trade["entry_price"] - exit_price) * 10000
            pnl = pips * trade["position_size"] * trade.get("pip_value", 10.0)
        
        # Update account balance
        self.account_balance += pnl
        
        # Log exit
        logger.info(f"Trade {trade_id} exited: {exit_reason}")
        logger.info(f"Exit Price: {exit_price:.5f}")
        logger.info(f"Pips: {pips:.1f}")
        logger.info(f"PnL: ${pnl:.2f}")
        logger.info(f"New Account Balance: ${self.account_balance:.2f}")
        
        # Remove from active trades
        del self.active_trades[trade_id]
    
    def update_pnl(self, trade_id: str, current_price: float):
        """Update current PnL for active trade"""
        trade = self.active_trades[trade_id]
        
        if trade["direction"] == "LONG":
            pips = (current_price - trade["entry_price"]) * 10000
            pnl = pips * trade["position_size"] * trade.get("pip_value", 10.0)
        else:  # SHORT
            pips = (trade["entry_price"] - current_price) * 10000
            pnl = pips * trade["position_size"] * trade.get("pip_value", 10.0)
        
        trade["current_pnl"] = pnl
        
        # Log significant PnL changes
        if abs(pnl) > trade["risk_amount"] * 0.5:
            logger.info(f"Trade {trade_id}: PnL = ${pnl:.2f}")

# Example usage
def main():
    """Example of using the adaptive trading bot"""
    
    # Initialize bot
    bot = AdaptiveTradingBot(account_balance=10000.0)
    
    # Simulate price data for multiple timeframes
    def generate_sample_data(symbol: str, base_price: float) -> Dict[TimeFrame, pd.DataFrame]:
        """Generate sample price data for testing"""
        data = {}
        
        for timeframe in TimeFrame:
            # Generate OHLC data
            periods = 100
            dates = pd.date_range(end=datetime.now(), periods=periods, freq='T')
            
            # Generate random walk
            returns = np.random.randn(periods) * 0.001
            price = base_price * np.exp(np.cumsum(returns))
            
            # Create OHLC dataframe
            df = pd.DataFrame({
                'open': price * 0.999,
                'high': price * 1.001,
                'low': price * 0.997,
                'close': price,
                'volume': np.random.randint(1000, 10000, periods)
            }, index=dates)
            
            data[timeframe] = df
            
        return data
    
    # Create sample trading signal
    signal = TradeSignal(
        symbol="EURCAD",
        direction="SHORT",
        entry_price=1.61159,
        signal_strength=85.0,
        confidence=0.8,
        timestamp=datetime.now(),
        indicators={"rsi": 65.0, "macd": -0.0012}
    )
    
    # Generate sample price data
    price_data = generate_sample_data("EURCAD", 1.61159)
    
    # Process signal and generate trade plan
    trade_plan = bot.process_signal(signal, price_data)
    
    if trade_plan:
        # Execute trade
        trade_id = bot.execute_trade(trade_plan)
        
        # Start monitoring (in real implementation, this would be in a separate thread)
        logger.info("Starting trade monitoring...")
        
        # Monitor for 10 seconds in demo
        for i in range(10):
            for trade_id, trade in list(bot.active_trades.items()):
                current_price = bot.simulate_price_movement(trade)
                bot.check_exit_conditions(trade_id, current_price)
                bot.update_pnl(trade_id, current_price)
            time.sleep(1)
    
    logger.info("Trading bot execution completed")

if __name__ == "__main__":
    main()