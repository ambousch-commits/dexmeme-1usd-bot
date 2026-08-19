from .config import Settings
from .models import Pair

def entry_allowed(pair: Pair, settings: Settings) -> bool:
    if pair.price_usd <= 0 or pair.liquidity_usd < settings.min_liquidity_usd: return False
    if not (pair.age_seconds >= settings.min_pair_age_seconds and pair.age_seconds <= settings.max_pair_age_hours*3600): return False
    if pair.buys_24h < settings.min_buys or pair.buys_1h < settings.min_buys_1h: return False
    if pair.buys_1h < pair.sells_1h * settings.buy_sell_ratio: return False
    if pair.price_change_1h_pct < settings.min_price_change_1h_pct: return False
    return True

def gross_target_pct(pair: Pair, settings: Settings, sol_usd: float) -> float:
    # Phase 2 requires enough upside to justify the fixed -5% stop.
    capital_usd=settings.position_size_usd
    required=((settings.target_net_usd/capital_usd)*100.0)+settings.round_trip_cost_pct
    pressure=pair.buys_1h/(pair.buys_1h+pair.sells_1h) if pair.buys_1h+pair.sells_1h else 0
    momentum=max(0.0,min(1.0,pair.price_change_1h_pct/15.0))
    adjusted=required*(1.0+0.10*(1.0-pressure))+0.10*momentum
    return max(settings.take_profit_min_pct,min(settings.take_profit_max_pct,adjusted))

def pnl_pct(entry_price:float,current_price:float)->float:
    return 0.0 if entry_price<=0 else round((current_price/entry_price-1.0)*100.0,10)

def exit_reason(entry_price:float,current_price:float,target:float,settings:Settings):
    change=pnl_pct(entry_price,current_price)
    if change<=settings.stop_loss_pct:return 'stop_loss'
    if change>=target:return 'take_profit'
    return None
