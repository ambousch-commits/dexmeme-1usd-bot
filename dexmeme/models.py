from dataclasses import dataclass

@dataclass(frozen=True)
class Pair:
    chain_id: str
    dex_id: str
    pair_address: str
    token_address: str
    symbol: str
    name: str
    price_usd: float
    liquidity_usd: float
    pair_created_at_ms: int
    buys_24h: int
    sells_24h: int
    buys_1h: int
    sells_1h: int
    volume_1h: float
    price_change_1h_pct: float
    url: str

    @property
    def age_seconds(self) -> float:
        import time
        return max(0.0, time.time() - self.pair_created_at_ms / 1000.0) if self.pair_created_at_ms else 0.0

@dataclass(frozen=True)
class Position:
    id: int
    token_address: str
    pair_address: str
    symbol: str
    entry_price: float
    entry_time: float
    size_sol: float
    target_pct: float
    size_usd: float = 10.0
    entry_sol_usd: float | None = None
