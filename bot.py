import time
import logging
import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MarketType(Enum):
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
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

class DynamicRiskManager:
    """Dynamic risk management across timeframes and markets"""
    
    def __init__(self):
        # Base stop loss in pips for each timeframe
        self.timeframe_stops = {
            TimeFrame.M1: 2,   # 2 pips for 1-minute
            TimeFrame.M3: 3,   # 3 pips for 3-minute
            TimeFrame.M5: 5,   # 5 pips for 5-minute
            TimeFrame.M15: 8,  # 8 pips for 15-minute
            TimeFrame.M30: 12, # 12 pips for 30-minute
            TimeFrame.H1: 15,  # 15 pips for 1-hour
            TimeFrame.H4: 25,  # 25 pips for 4-hour
            TimeFrame.D1: 40   # 40 pips for daily
        }
        
        # Risk/Reward ratios for each timeframe
        self.timeframe_rr_ratios = {
            TimeFrame.M1: [1.0, 1.5, 2.0],
            TimeFrame.M3: [1.0, 2.0, 3.0],
            TimeFrame.M5: [1.5, 2.5, 3.5],
            TimeFrame.M15: [2.0, 3.0, 4.0],
            TimeFrame.M30: [2.0, 3.0, 4.0],
            TimeFrame.H1: [2.5, 3.5, 5.0],
            TimeFrame.H4: [3.0, 4.0, 6.0],
            TimeFrame.D1: [3.0, 5.0, 8.0]
        }
        
        # Market volatility multipliers
        self.market_multipliers = {
            MarketType.FOREX: 1.0,
            MarketType.CRYPTO: 2.5,
            MarketType.STOCKS: 0.8
        }
    
    def calculate_pip_size(self, symbol: str) -> float:
        """Calculate pip size based on symbol"""
        if "JPY" in symbol:
            return 0.01
        return 0.0001
    
    def calculate_stop_loss(self, 
                           symbol: str,
                           entry_price: float,
                           direction: str,
                           timeframe: TimeFrame,
                           market_type: MarketType) -> Dict:
        """
        Calculate dynamic stop loss
        """
        # Get base stop for timeframe
        base_stop = self.timeframe_stops.get(timeframe, 10)
        
        # Apply market multiplier
        multiplier = self.market_multipliers.get(market_type, 1.0)
        stop_pips = base_stop * multiplier
        
        # Adjust for symbol
        pip_size = self.calculate_pip_size(symbol)
        stop_distance = stop_pips * pip_size
        
        # Calculate stop price
        if direction.upper() == "SHORT":
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
                              timeframe: TimeFrame) -> List[Dict]:
        """
        Calculate three take-profit levels
        """
        rr_ratios = self.timeframe_rr_ratios.get(timeframe, [1.0, 2.0, 3.0])
        pip_size = 0.0001  # Standard for most pairs
        
        tp_levels = []
        for i, ratio in enumerate(rr_ratios):
            tp_pips = stop_pips * ratio
            tp_distance = tp_pips * pip_size
            
            if direction.upper() == "SHORT":
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
                               pip_value: float) -> float:
        """
        Calculate position size based on risk
        """
        risk_amount = account_balance * (risk_percent / 100.0)
        
        # Calculate position size
        if stop_pips > 0:
            position_size = risk_amount / (stop_pips * pip_value)
        else:
            position_size = 0
        
        # Convert to standard lot size
        position_size = round(position_size, 2)
        
        # Ensure minimum size
        if position_size < 0.01:
            position_size = 0.01
        
        return position_size

class AdaptiveTradingBot:
    """Trading bot with adaptive parameters for all timeframes and markets"""
    
    def __init__(self, account_balance: float = 10000.0):
        self.account_balance = account_balance
        self.risk_manager = DynamicRiskManager()
        self.market_profiles = self.initialize_market_profiles()
        self.active_trades = {}
        
        logger.info(f"Adaptive Trading Bot initialized")
        logger.info(f"Account Balance: ${account_balance:,.2f}")
    
    def initialize_market_profiles(self) -> Dict[str, MarketProfile]:
        """Initialize market profiles"""
        profiles = {
            # Forex pairs
            "EURUSD": MarketProfile(
                symbol="EURUSD",
                market_type=MarketType.FOREX,
                avg_daily_range=70.0,
                spread=0.0001,
                pip_value=10.0
            ),
            "GBPUSD": MarketProfile(
                symbol="GBPUSD",
                market_type=MarketType.FOREX,
                avg_daily_range=90.0,
                spread=0.00012,
                pip_value=10.0
            ),
            "USDJPY": MarketProfile(
                symbol="USDJPY",
                market_type=MarketType.FOREX,
                avg_daily_range=65.0,
                spread=0.01,
                pip_value=9.27
            ),
            "EURCAD": MarketProfile(
                symbol="EURCAD",
                market_type=MarketType.FOREX,
                avg_daily_range=85.0,
                spread=0.00015,
                pip_value=7.5
            ),
            # Cryptocurrencies
            "BTCUSD": MarketProfile(
                symbol="BTCUSD",
                market_type=MarketType.CRYPTO,
                avg_daily_range=3000.0,
                spread=5.0,
                pip_value=1.0,
                lot_size=1.0
            ),
            "ETHUSD": MarketProfile(
                symbol="ETHUSD",
                market_type=MarketType.CRYPTO,
                avg_daily_range=150.0,
                spread=0.5,
                pip_value=1.0,
                lot_size=1.0
            )
        }
        return profiles
    
    def get_market_profile(self, symbol: str) -> MarketProfile:
        """Get or create market profile for symbol"""
        if symbol in self.market_profiles:
            return self.market_profiles[symbol]
        
        # Default profile for unknown symbols
        if "BTC" in symbol or "ETH" in symbol or "XRP" in symbol:
            return MarketProfile(
                symbol=symbol,
                market_type=MarketType.CRYPTO,
                avg_daily_range=500.0,
                spread=1.0,
                pip_value=1.0,
                lot_size=1.0
            )
        else:
            return MarketProfile(
                symbol=symbol,
                market_type=MarketType.FOREX,
                avg_daily_range=80.0,
                spread=0.0001,
                pip_value=10.0
            )
    
    def calculate_trade_plan(self,
                            symbol: str,
                            direction: str,
                            entry_price: float,
                            timeframe: TimeFrame,
                            risk_percent: float = 1.0) -> Dict:
        """
        Calculate complete trade plan for any symbol and timeframe
        """
        # Get market profile
        market_profile = self.get_market_profile(symbol)
        
        # Calculate stop loss
        stop_data = self.risk_manager.calculate_stop_loss(
            symbol=symbol,
            entry_price=entry_price,
            direction=direction,
            timeframe=timeframe,
            market_type=market_profile.market_type
        )
        
        # Calculate take profits
        tp_levels = self.risk_manager.calculate_take_profits(
            entry_price=entry_price,
            stop_pips=stop_data["stop_pips"],
            direction=direction,
            timeframe=timeframe
        )
        
        # Calculate position size
        position_size = self.risk_manager.calculate_position_size(
            account_balance=self.account_balance,
            risk_percent=risk_percent,
            stop_pips=stop_data["stop_pips"],
            pip_value=market_profile.pip_value
        )
        
        # Calculate risk amount
        risk_amount = self.account_balance * (risk_percent / 100.0)
        
        # Create trade plan
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
    
    def display_trade_plan(self, trade_plan: Dict):
        """Display formatted trade plan"""
        print("\n" + "="*80)
        print("ADAPTIVE TRADE PLAN")
        print("="*80)
        print(f"Symbol: {trade_plan['symbol']}")
        print(f"Market Type: {trade_plan['market_type']}")
        print(f"Direction: {trade_plan['direction']}")
        print(f"Timeframe: {trade_plan['timeframe']}")
        print(f"Entry Price: {trade_plan['entry_price']:.5f}")
        print(f"Stop Loss: {trade_plan['stop_loss']:.5f} ({trade_plan['stop_pips']:.1f} pips)")
        print(f"Position Size: {trade_plan['position_size']:.2f} lots")
        print(f"Risk Amount: ${trade_plan['risk_amount']:.2f} ({trade_plan['risk_percent']}%)")
        print(f"Pip Value: ${trade_plan['pip_value']:.2f}")
        
        print("\nTAKE PROFIT LEVELS:")
        print("-"*40)
        for tp in trade_plan["take_profits"]:
            print(f"TP{tp['level']}: {tp['price']:.5f} ({tp['pips']:.1f} pips, {tp['rr_ratio']}:1 RR)")
        
        print("="*80)
    
    def execute_trade(self, trade_plan: Dict):
        """Execute a trade based on trade plan"""
        trade_id = f"{trade_plan['symbol']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"Executing trade: {trade_id}")
        logger.info(f"Direction: {trade_plan['direction']} at {trade_plan['entry_price']}")
        
        # Store trade
        self.active_trades[trade_id] = {
            **trade_plan,
            "trade_id": trade_id,
            "status": "ACTIVE",
            "entry_time": datetime.now(),
            "current_pnl": 0.0
        }
        
        return trade_id
    
    def update_trade(self, trade_id: str, current_price: float):
        """Update trade with current price"""
        if trade_id not in self.active_trades:
            return None
        
        trade = self.active_trades[trade_id]
        
        # Calculate current PnL
        if trade["direction"] == "LONG":
            pips = (current_price - trade["entry_price"]) * 10000
            pnl = pips * trade["position_size"] * trade["pip_value"]
        else:  # SHORT
            pips = (trade["entry_price"] - current_price) * 10000
            pnl = pips * trade["position_size"] * trade["pip_value"]
        
        trade["current_price"] = current_price
        trade["current_pips"] = pips
        trade["current_pnl"] = pnl
        
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
        
        return {
            "trade_id": trade_id,
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
            pips = (exit_price - trade["entry_price"]) * 10000
            pnl = pips * trade["position_size"] * trade["pip_value"]
        else:  # SHORT
            pips = (trade["entry_price"] - exit_price) * 10000
            pnl = pips * trade["position_size"] * trade["pip_value"]
        
        # Update account balance
        self.account_balance += pnl
        
        # Log
        logger.info(f"Trade {trade_id} closed: {exit_reason}")
        logger.info(f"Exit Price: {exit_price:.5f}")
        logger.info(f"Pips: {pips:.1f}")
        logger.info(f"PnL: ${pnl:.2f}")
        logger.info(f"New Balance: ${self.account_balance:.2f}")
        
        # Remove from active trades
        del self.active_trades[trade_id]
    
    def get_all_timeframe_plans(self,
                               symbol: str,
                               direction: str,
                               entry_price: float,
                               risk_percent: float = 1.0) -> Dict[str, Dict]:
        """
        Generate trade plans for ALL timeframes
        """
        plans = {}
        
        for timeframe in TimeFrame:
            plan = self.calculate_trade_plan(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                timeframe=timeframe,
                risk_percent=risk_percent
            )
            plans[timeframe.value] = plan
        
        return plans
    
    def auto_adjust_for_volatility(self,
                                  symbol: str,
                                  current_volatility: float) -> float:
        """
        Auto-adjust risk based on current volatility
        """
        # Normal volatility is around 1.0
        # If volatility is high (>1.5), reduce risk
        # If volatility is low (<0.5), can increase risk slightly
        
        base_risk = 1.0  # 1% base risk
        
        if current_volatility > 2.0:
            adjusted_risk = base_risk * 0.5  # 0.5% risk
        elif current_volatility > 1.5:
            adjusted_risk = base_risk * 0.75  # 0.75% risk
        elif current_volatility < 0.5:
            adjusted_risk = base_risk * 1.25  # 1.25% risk
        elif current_volatility < 0.3:
            adjusted_risk = base_risk * 1.5  # 1.5% risk
        else:
            adjusted_risk = base_risk
        
        return adjusted_risk

def main():
    """Example usage"""
    bot = AdaptiveTradingBot(account_balance=10000.0)
    
    print("\n" + "="*80)
    print("ADAPTIVE TRADING BOT - ALL TIMEFRAMES & MARKETS")
    print("="*80)
    
    # Example 1: EURCAD Short on 3-minute timeframe (from your original example)
    print("\nExample 1: EURCAD Short on 3-Minute Timeframe")
    print("-"*40)
    
    eurcad_plan = bot.calculate_trade_plan(
        symbol="EURCAD",
        direction="SHORT",
        entry_price=1.61159,
        timeframe=TimeFrame.M3,
        risk_percent=1.0
    )
    bot.display_trade_plan(eurcad_plan)
    
    # Example 2: BTCUSD Long on 1-hour timeframe
    print("\n\nExample 2: BTCUSD Long on 1-Hour Timeframe")
    print("-"*40)
    
    btc_plan = bot.calculate_trade_plan(
        symbol="BTCUSD",
        direction="LONG",
        entry_price=87832.0,
        timeframe=TimeFrame.H1,
        risk_percent=1.0
    )
    bot.display_trade_plan(btc_plan)
    
    # Example 3: Get plans for ALL timeframes for EURUSD
    print("\n\nExample 3: ALL Timeframe Plans for EURUSD Short")
    print("-"*40)
    
    all_plans = bot.get_all_timeframe_plans(
        symbol="EURUSD",
        direction="SHORT",
        entry_price=1.0850,
        risk_percent=1.0
    )
    
    # Show summary for each timeframe
    for tf, plan in all_plans.items():
        print(f"\n{tf}: SL={plan['stop_pips']:.1f}pips, "
              f"TP1={plan['take_profits'][0]['rr_ratio']}:1, "
              f"TP2={plan['take_profits'][1]['rr_ratio']}:1, "
              f"TP3={plan['take_profits'][2]['rr_ratio']}:1")
    
    # Example 4: Simulate trade execution
    print("\n\nExample 4: Simulating Trade Execution")
    print("-"*40)
    
    # Create a trade
    trade_plan = bot.calculate_trade_plan(
        symbol="EURUSD",
        direction="SHORT",
        entry_price=1.0850,
        timeframe=TimeFrame.M5,
        risk_percent=1.0
    )
    
    trade_id = bot.execute_trade(trade_plan)
    
    # Simulate price updates
    print(f"\nSimulating price movement for trade {trade_id}...")
    
    current_price = 1.0850
    for i in range(10):
        # Simulate price movement
        price_change = random.uniform(-0.0005, 0.0005)
        current_price += price_change
        
        # Update trade
        update = bot.update_trade(trade_id, current_price)
        
        if update:
            print(f"Update {i+1}: Price={current_price:.5f}, "
                  f"Pips={update['current_pips']:.1f}, "
                  f"PnL=${update['current_pnl']:.2f}")
            
            if update['exit_reason']:
                print(f"Trade exited: {update['exit_reason']}")
                break
        
        time.sleep(0.5)
    
    print(f"\nFinal Account Balance: ${bot.account_balance:.2f}")
    print("\n" + "="*80)
    print("ADAPTIVE TRADING BOT READY")
    print("="*80)

if __name__ == "__main__":
    main()