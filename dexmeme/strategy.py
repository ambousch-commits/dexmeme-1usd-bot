from .config import Settings
from .models import Pair

def entry_filter_reason(pair: Pair, settings: Settings) -> str | None:
    if pair.price_usd <= 0:
        return 'invalid_price'
    if pair.liquidity_usd < settings.min_liquidity_usd:
        return 'low_liquidity'
    if pair.liquidity_usd > settings.max_liquidity_usd:
        return 'high_liquidity'
    if not (settings.min_pair_age_seconds <= pair.age_seconds <= settings.max_pair_age_hours * 3600):
        return 'age_outside_range'
    if pair.buys_24h < settings.min_buys or pair.buys_1h < settings.min_buys_1h:
        return 'insufficient_buy_activity'
    total = pair.buys_1h + pair.sells_1h
    pressure = pair.buys_1h / total if total else 0.0
    if pair.buys_1h < pair.sells_1h * settings.buy_sell_ratio:
        return 'weak_buy_pressure'
    if pressure > settings.max_buy_pressure:
        return 'extreme_buy_pressure'
    if pair.price_change_1h_pct < settings.min_price_change_1h_pct:
        return 'weak_momentum'
    if pair.price_change_1h_pct > settings.max_price_change_1h_pct:
        return 'extreme_momentum'
    turnover = pair.volume_1h / pair.liquidity_usd if pair.liquidity_usd > 0 else 0.0
    if turnover > settings.max_volume_liquidity_ratio:
        return 'excessive_volume_vs_liquidity'
    return None

def entry_allowed(pair: Pair, settings: Settings) -> bool:
    return entry_filter_reason(pair, settings) is None

def gross_target_pct(pair: Pair, settings: Settings, sol_usd: float) -> float:
    # For a $10 position and a $1 net target, require roughly 10% gross price gain
    # plus round-trip costs. Keep a 12-15% target band to preserve the requested net goal.
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
