import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
@dataclass(frozen=True)
class Settings:
    mode: str=os.getenv('MODE','paper'); port:int=int(os.getenv('PORT','8080')); poll_seconds:float=float(os.getenv('POLL_SECONDS','2'))
    position_size_usd:float=min(float(os.getenv('POSITION_SIZE_USD','10')),10.0); target_net_usd:float=float(os.getenv('TARGET_NET_USD','1'))
    round_trip_cost_pct:float=float(os.getenv('ROUND_TRIP_COST_PCT','1')); daily_trade_goal:int=int(os.getenv('DAILY_TRADE_GOAL','100'))
    min_buys:int=int(os.getenv('MIN_BUYS','100')); min_liquidity_usd:float=float(os.getenv('MIN_LIQUIDITY_USD','30000')); max_open_positions:int=int(os.getenv('MAX_OPEN_POSITIONS','20'))
    stop_loss_pct:float=float(os.getenv('STOP_LOSS_PCT','-5')); take_profit_min_pct:float=float(os.getenv('TAKE_PROFIT_MIN_PCT','12')); take_profit_max_pct:float=float(os.getenv('TAKE_PROFIT_MAX_PCT','15'))
    min_pair_age_seconds:int=int(os.getenv('MIN_PAIR_AGE_SECONDS','300')); max_pair_age_hours:float=float(os.getenv('MAX_PAIR_AGE_HOURS','24'))
    min_buys_1h:int=int(os.getenv('MIN_BUYS_1H','10')); buy_sell_ratio:float=float(os.getenv('BUY_SELL_RATIO','1.25')); max_buy_pressure:float=float(os.getenv('MAX_BUY_PRESSURE','0.75'))
    min_price_change_1h_pct:float=float(os.getenv('MIN_PRICE_CHANGE_1H_PCT','1')); max_price_change_1h_pct:float=float(os.getenv('MAX_PRICE_CHANGE_1H_PCT','80'))
    max_volume_liquidity_ratio:float=float(os.getenv('MAX_VOLUME_LIQUIDITY_RATIO','15'))
    profile_refresh_seconds:int=int(os.getenv('PROFILE_REFRESH_SECONDS','30')); request_timeout_seconds:float=float(os.getenv('REQUEST_TIMEOUT_SECONDS','10'))
    dex_base_url:str=os.getenv('DEXSCREENER_BASE_URL','https://api.dexscreener.com'); solana_rpc_url:str=os.getenv('SOLANA_RPC_URL','https://api.mainnet-beta.solana.com')
    require_authorities_revoked:bool=os.getenv('REQUIRE_AUTHORITIES_REVOKED','true').lower()=='true'; db_path:str=os.getenv('DB_PATH','/data/dexmeme-1usd.sqlite3')
    def validate(self):
        if self.mode!='paper': raise ValueError('Only paper mode is supported')
        if not 0<self.position_size_usd<=10: raise ValueError('POSITION_SIZE_USD must be between 0 and $10')
        if self.stop_loss_pct>=0 or self.take_profit_min_pct<=0 or self.take_profit_max_pct<self.take_profit_min_pct: raise ValueError('invalid risk settings')
        Path(self.db_path).parent.mkdir(parents=True,exist_ok=True)
settings=Settings(); settings.validate()
