from __future__ import annotations
import sqlite3, time
from pathlib import Path
from .models import Pair, Position


def _trade_count(path: Path) -> int:
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=1)
        try:
            row = conn.execute("SELECT COUNT(*) FROM positions").fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except Exception:
        return -1


def _resolve_db_path(path: str) -> str:
    """Recover an existing paper database from common Railway volume paths.
    The recovery is read-only until the selected database is used normally."""
    requested = Path(path)
    candidates = [requested]
    roots = [Path('/data'), Path('/app/data'), Path('/app'), Path.cwd()]
    for root in roots:
        if root.exists():
            for pattern in ('*.sqlite3', '*.db', '*.sqlite'):
                try:
                    candidates.extend(root.glob(pattern))
                except Exception:
                    pass
    unique = []
    seen = set()
    for candidate in candidates:
        try:
            resolved = str(candidate.resolve())
        except Exception:
            resolved = str(candidate)
        if resolved in seen or not candidate.exists() or not candidate.is_file():
            continue
        seen.add(resolved)
        name = candidate.name.lower()
        if candidate == requested or any(k in name for k in ('dexmeme', '1usd', 'paper')):
            unique.append(candidate)
    current_count = _trade_count(requested) if requested.exists() else -1
    if current_count > 0:
        return str(requested)
    best = requested
    best_count = max(current_count, 0)
    for candidate in unique:
        count = _trade_count(candidate)
        if count > best_count:
            best, best_count = candidate, count
    if best != requested and best_count > 0:
        print(f'[DB] recovered existing paper DB: {best} ({best_count} trades)')
    return str(best)


class Database:
    def __init__(self, path: str):
        self.path = _resolve_db_path(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS positions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          token_address TEXT NOT NULL, pair_address TEXT NOT NULL, symbol TEXT NOT NULL,
          entry_price REAL NOT NULL, entry_time REAL NOT NULL, size_sol REAL NOT NULL, target_pct REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'open', exit_price REAL, exit_time REAL, exit_reason TEXT, pnl_pct REAL,
          size_usd REAL, entry_sol_usd REAL, exit_sol_usd REAL, pnl_usd REAL
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, event TEXT NOT NULL,
          token_address TEXT, pair_address TEXT, payload TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_open_token ON positions(token_address) WHERE status='open';
        ''')
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        cols = {r[1] for r in self.conn.execute('PRAGMA table_info(positions)').fetchall()}
        migrations = {
            'size_usd': 'ALTER TABLE positions ADD COLUMN size_usd REAL',
            'entry_sol_usd': 'ALTER TABLE positions ADD COLUMN entry_sol_usd REAL',
            'exit_sol_usd': 'ALTER TABLE positions ADD COLUMN exit_sol_usd REAL',
            'pnl_usd': 'ALTER TABLE positions ADD COLUMN pnl_usd REAL',
        }
        for name, sql in migrations.items():
            if name not in cols:
                self.conn.execute(sql)
        self.conn.execute("UPDATE positions SET size_usd=10.0 WHERE size_usd IS NULL OR size_usd<=0")
        self.conn.execute("UPDATE positions SET pnl_usd=size_usd*pnl_pct/100.0 WHERE status='closed' AND pnl_pct IS NOT NULL AND pnl_usd IS NULL")

    def normalize_open_sizes(self, sol_usd: float, size_usd: float = 10.0):
        if sol_usd <= 0: raise ValueError('SOL/USD must be positive')
        self.conn.execute("UPDATE positions SET size_usd=?, size_sol=? WHERE status='open'", (size_usd, size_usd / sol_usd))
        self.conn.commit()

    def log(self, event: str, token_address: str | None = None, pair_address: str | None = None, payload: str = ''):
        self.conn.execute('INSERT INTO events(ts,event,token_address,pair_address,payload) VALUES(?,?,?,?,?)', (time.time(), event, token_address, pair_address, payload))
        self.conn.commit()

    def open_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM positions WHERE status='open'").fetchone()[0])

    def has_open_token(self, token_address: str) -> bool:
        return self.conn.execute("SELECT 1 FROM positions WHERE token_address=? AND status='open'", (token_address,)).fetchone() is not None

    def open_position(self, pair: Pair, size_usd: float, sol_usd: float, target: float) -> Position:
        if size_usd <= 0 or sol_usd <= 0: raise ValueError('position USD size and SOL/USD price must be positive')
        now = time.time(); size_sol = size_usd / sol_usd
        cur = self.conn.execute('INSERT INTO positions(token_address,pair_address,symbol,entry_price,entry_time,size_sol,target_pct,size_usd,entry_sol_usd) VALUES(?,?,?,?,?,?,?,?,?)', (pair.token_address,pair.pair_address,pair.symbol,pair.price_usd,now,size_sol,target,size_usd,sol_usd))
        self.conn.commit()
        self.log('paper_buy', pair.token_address, pair.pair_address, f'price={pair.price_usd};size_usd={size_usd};size_sol={size_sol};entry_sol_usd={sol_usd};target={target};liquidity={pair.liquidity_usd};buys24h={pair.buys_24h};sells24h={pair.sells_24h}')
        return Position(cur.lastrowid,pair.token_address,pair.pair_address,pair.symbol,pair.price_usd,now,size_sol,target,size_usd,sol_usd)

    def open_positions(self) -> list[Position]:
        rows = self.conn.execute("SELECT * FROM positions WHERE status='open' ORDER BY id").fetchall()
        return [Position(r['id'],r['token_address'],r['pair_address'],r['symbol'],r['entry_price'],r['entry_time'],r['size_sol'],r['target_pct'],r['size_usd'] or 10.0,r['entry_sol_usd']) for r in rows]

    def close_position(self, position_id: int, exit_price: float, reason: str, pnl: float, exit_sol_usd: float):
        row = self.conn.execute('SELECT size_usd FROM positions WHERE id=?', (position_id,)).fetchone()
        size_usd = float(row['size_usd'] or 10.0) if row else 10.0
        pnl_usd = size_usd * pnl / 100.0
        self.conn.execute("UPDATE positions SET status='closed',exit_price=?,exit_time=?,exit_reason=?,pnl_pct=?,pnl_usd=?,exit_sol_usd=? WHERE id=?", (exit_price,time.time(),reason,pnl,pnl_usd,exit_sol_usd,position_id))
        self.conn.commit()
        self.log('paper_sell', payload=f'position_id={position_id};price={exit_price};reason={reason};pnl_pct={pnl};pnl_usd={pnl_usd};exit_sol_usd={exit_sol_usd}')

    def close(self): self.conn.close()
