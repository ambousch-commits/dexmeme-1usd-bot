from __future__ import annotations
import sqlite3, time
from pathlib import Path
from .models import Pair, Position

class Database:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS positions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          token_address TEXT NOT NULL, pair_address TEXT NOT NULL, symbol TEXT NOT NULL,
          entry_price REAL NOT NULL, entry_time REAL NOT NULL, size_sol REAL NOT NULL, target_pct REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'open', exit_price REAL, exit_time REAL, exit_reason TEXT, pnl_pct REAL
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, event TEXT NOT NULL,
          token_address TEXT, pair_address TEXT, payload TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_open_token ON positions(token_address) WHERE status='open';
        ''')
        self.conn.commit()

    def log(self, event: str, token_address: str | None = None, pair_address: str | None = None, payload: str = ''):
        self.conn.execute('INSERT INTO events(ts,event,token_address,pair_address,payload) VALUES(?,?,?,?,?)', (time.time(), event, token_address, pair_address, payload))
        self.conn.commit()

    def open_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM positions WHERE status='open'").fetchone()[0])

    def has_open_token(self, token_address: str) -> bool:
        return self.conn.execute("SELECT 1 FROM positions WHERE token_address=? AND status='open'", (token_address,)).fetchone() is not None

    def open_position(self, pair: Pair, size_sol: float, target: float) -> Position:
        now = time.time()
        cur = self.conn.execute('INSERT INTO positions(token_address,pair_address,symbol,entry_price,entry_time,size_sol,target_pct) VALUES(?,?,?,?,?,?,?)', (pair.token_address,pair.pair_address,pair.symbol,pair.price_usd,now,size_sol,target))
        self.conn.commit()
        self.log('paper_buy', pair.token_address, pair.pair_address, f'price={pair.price_usd};size_sol={size_sol};target={target};liquidity={pair.liquidity_usd};buys24h={pair.buys_24h};sells24h={pair.sells_24h}')
        return Position(cur.lastrowid,pair.token_address,pair.pair_address,pair.symbol,pair.price_usd,now,size_sol,target)

    def open_positions(self) -> list[Position]:
        rows = self.conn.execute("SELECT * FROM positions WHERE status='open' ORDER BY id").fetchall()
        return [Position(r['id'],r['token_address'],r['pair_address'],r['symbol'],r['entry_price'],r['entry_time'],r['size_sol'],r['target_pct']) for r in rows]

    def close_position(self, position_id: int, exit_price: float, reason: str, pnl: float):
        self.conn.execute("UPDATE positions SET status='closed',exit_price=?,exit_time=?,exit_reason=?,pnl_pct=? WHERE id=?", (exit_price,time.time(),reason,pnl,position_id))
        self.conn.commit()
        self.log('paper_sell', payload=f'position_id={position_id};price={exit_price};reason={reason};pnl_pct={pnl}')

    def close(self): self.conn.close()
