import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    mode: str = os.getenv('MODE', 'paper')
    port: int = int(os.getenv('PORT', '8080'))
    poll_seconds: float = float(os.getenv('POLL_SECONDS', '2'))
    position_size_usd: float = float(os.getenv('POSITION_SIZE_USD', '10.0'))
    target_net_usd: float = float(os.getenv('TARGET_NET_USD', '1.0'))
    round_trip_cost_pct: float = float(os.getenv('ROUND_TRIP_COST_PCT', '1.0'))
    daily_trade_goal: int = int(os.getenv('DAILY_TRADE_GOAL', '100'))
    min_buys: int = int(os.getenv('MIN_BUYS', '100'))
    min_liquidity_usd: float = float(os.getenv('MIN_LIQUIDITY_USD', '10000'))
    max_open_positions: int = int(os.getenv('MAX_OPEN_POSITIONS', '20'))
    stop_loss_pct: float = float(os.getenv('STOP_LOSS_PCT', '-2.5'))
    take_profit_min_pct: float = float(os.getenv('TAKE_PROFIT_MIN_PCT', '1.25'))
    take_profit_max_pct: float = float(os.getenv('TAKE_PROFIT_MAX_PCT', '5.0'))
    min_pair_age_seconds: int = int(os.getenv('MIN_PAIR_AGE_SECONDS', '60'))
    max_pair_age_hours: float = float(os.getenv('MAX_PAIR_AGE_HOURS', '24'))
    profile_refresh_seconds: int = int(os.getenv('PROFILE_REFRESH_SECONDS', '30'))
    request_timeout_seconds: float = float(os.getenv('REQUEST_TIMEOUT_SECONDS', '10'))
    dex_base_url: str = os.getenv('DEXSCREENER_BASE_URL', 'https://api.dexscreener.com')
    solana_rpc_url: str = os.getenv('SOLANA_RPC_URL', 'https://api.mainnet-beta.solana.com')
    require_authorities_revoked: bool = os.getenv('REQUIRE_AUTHORITIES_REVOKED', 'true').lower() == 'true'
    db_path: str = os.getenv('DB_PATH', '/data/dexmeme-1usd.sqlite3')

    def validate(self) -> None:
        if self.mode != 'paper':
            raise ValueError('Only paper mode is supported')
        if self.position_size_usd <= 0:
            raise ValueError('POSITION_SIZE_USD must be > 0')
        if self.target_net_usd <= 0:
            raise ValueError('TARGET_NET_USD must be > 0')
        if self.round_trip_cost_pct < 0:
            raise ValueError('ROUND_TRIP_COST_PCT must be >= 0')
        if self.daily_trade_goal < 1 or self.max_open_positions < 1:
            raise ValueError('daily trade goal and max positions must be >= 1')
        if self.stop_loss_pct >= 0:
            raise ValueError('STOP_LOSS_PCT must be negative')
        if self.take_profit_min_pct <= 0 or self.take_profit_max_pct < self.take_profit_min_pct:
            raise ValueError('invalid take-profit range')
        if self.poll_seconds <= 0 or self.profile_refresh_seconds <= 0:
            raise ValueError('poll intervals must be positive')
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.validate()
