from __future__ import annotations
import sqlite3, time
from pathlib import Path
from .models import Pair, Position


def _db_counts(path: Path) -> tuple[int, int]:
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=1)
        try:
            tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            positions=int(conn.execute('SELECT COUNT(*) FROM positions').fetchone()[0]) if 'positions' in tables else 0
            events=int(conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]) if 'events' in tables else 0
            return positions,events
        finally: conn.close()
    except Exception:return -1,-1

def _find_db_files(root: Path,max_depth:int=5)->list[Path]:
    if not root.exists() or not root.is_dir():return []
    found=[]; base_depth=len(root.parts)
    try:
        for p in root.rglob('*'):
            try:
                if p.is_file() and not p.name.endswith(('-wal','-shm')) and len(p.parts)-base_depth<=max_depth and p.suffix.lower() in ('.sqlite3','.sqlite','.db'):found.append(p)
            except OSError:continue
    except OSError:pass
    return found

def _resolve_db_path(path:str)->str:
    requested=Path(path); candidates=[requested]
    for root in (Path('/data'),Path('/app/data'),Path('/app'),Path.cwd()):candidates.extend(_find_db_files(root))
    unique=[];seen=set()
    for c in candidates:
        try:r=str(c.resolve())
        except Exception:r=str(c)
        if r not in seen and c.exists() and c.is_file():seen.add(r);unique.append(c)
    cp,ce=_db_counts(requested) if requested.exists() else (-1,-1)
    best=requested;best_score=max(0,cp)*1000000+max(0,ce);bp=max(0,cp);be=max(0,ce)
    for c in unique:
        p,e=_db_counts(c)
        if p<0:continue
        score=p*1000000+max(0,e)
        if score>best_score or (score==best_score and c.stat().st_size>(best.stat().st_size if best.exists() else 0)):best,best_score,bp,be=c,score,p,e
    if best!=requested and (bp>0 or be>0):print(f'[DB] recovered existing paper DB: {best} (positions={bp}, events={be})')
    else:print(f'[DB] no historical SQLite DB found; using configured path: {requested}')
    return str(best)

class Database:
    def __init__(self,path:str):
        self.path=_resolve_db_path(path);Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        self.conn=sqlite3.connect(self.path,check_same_thread=False);self.conn.row_factory=sqlite3.Row;self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.executescript('''CREATE TABLE IF NOT EXISTS positions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, token_address TEXT NOT NULL, pair_address TEXT NOT NULL, symbol TEXT NOT NULL,
          entry_price REAL NOT NULL, entry_time REAL NOT NULL, size_sol REAL NOT NULL, target_pct REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'open', exit_price REAL, exit_time REAL, exit_reason TEXT, pnl_pct REAL,
          size_usd REAL, entry_sol_usd REAL, exit_sol_usd REAL, pnl_usd REAL, entry_liquidity_usd REAL);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL NOT NULL,event TEXT NOT NULL,token_address TEXT,pair_address TEXT,payload TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS one_open_token ON positions(token_address) WHERE status='open';''')
        self._migrate();self.conn.commit()
    def _migrate(self):
        cols={r[1] for r in self.conn.execute('PRAGMA table_info(positions)').fetchall()}
        for name,sql in {'size_usd':'REAL','entry_sol_usd':'REAL','exit_sol_usd':'REAL','pnl_usd':'REAL','entry_liquidity_usd':'REAL'}.items():
            if name not in cols:self.conn.execute(f'ALTER TABLE positions ADD COLUMN {name} {sql}')
        self.conn.execute("UPDATE positions SET size_usd=10.0 WHERE size_usd IS NULL OR size_usd<=0")
        self.conn.execute("UPDATE positions SET pnl_usd=size_usd*pnl_pct/100.0 WHERE status='closed' AND pnl_pct IS NOT NULL AND pnl_usd IS NULL")
    def normalize_open_sizes(self,sol_usd:float,size_usd:float=10.0):
        if sol_usd<=0:raise ValueError('SOL/USD must be positive')
        self.conn.execute("UPDATE positions SET size_usd=?,size_sol=? WHERE status='open'",(size_usd,size_usd/sol_usd));self.conn.commit()
    def log(self,event:str,token_address:str|None=None,pair_address:str|None=None,payload:str=''):
        self.conn.execute('INSERT INTO events(ts,event,token_address,pair_address,payload) VALUES(?,?,?,?,?)',(time.time(),event,token_address,pair_address,payload));self.conn.commit()
    def open_count(self)->int:return int(self.conn.execute("SELECT COUNT(*) FROM positions WHERE status='open'").fetchone()[0])
    def has_open_token(self,token_address:str)->bool:return self.conn.execute("SELECT 1 FROM positions WHERE token_address=? AND status='open'",(token_address,)).fetchone() is not None
    def has_recent_closed_token(self,token_address:str,cooldown_seconds:int)->bool:
        cutoff=time.time()-cooldown_seconds
        return self.conn.execute("SELECT 1 FROM positions WHERE token_address=? AND status='closed' AND exit_time>=? LIMIT 1",(token_address,cutoff)).fetchone() is not None
    def open_position(self,pair:Pair,size_usd:float,sol_usd:float,target:float)->Position:
        if size_usd<=0 or sol_usd<=0:raise ValueError('position USD size and SOL/USD price must be positive')
        now=time.time();size_sol=size_usd/sol_usd
        cur=self.conn.execute('INSERT INTO positions(token_address,pair_address,symbol,entry_price,entry_time,size_sol,target_pct,size_usd,entry_sol_usd,entry_liquidity_usd) VALUES(?,?,?,?,?,?,?,?,?,?)',(pair.token_address,pair.pair_address,pair.symbol,pair.price_usd,now,size_sol,target,size_usd,sol_usd,pair.liquidity_usd));self.conn.commit()
        self.log('paper_buy',pair.token_address,pair.pair_address,f'price={pair.price_usd};size_usd={size_usd};size_sol={size_sol};entry_sol_usd={sol_usd};target={target};liquidity={pair.liquidity_usd};buys24h={pair.buys_24h};sells24h={pair.sells_24h};buys1h={pair.buys_1h};sells1h={pair.sells_1h};volume1h={pair.volume_1h};price_change_1h={pair.price_change_1h_pct};age={pair.age_seconds}')
        return Position(cur.lastrowid,pair.token_address,pair.pair_address,pair.symbol,pair.price_usd,now,size_sol,target,size_usd,sol_usd,pair.liquidity_usd)
    def open_positions(self)->list[Position]:
        rows=self.conn.execute("SELECT * FROM positions WHERE status='open' ORDER BY id").fetchall()
        return [Position(r['id'],r['token_address'],r['pair_address'],r['symbol'],r['entry_price'],r['entry_time'],r['size_sol'],r['target_pct'],r['size_usd'] or 10.0,r['entry_sol_usd'],r['entry_liquidity_usd']) for r in rows]
    def close_position(self,position_id:int,exit_price:float,reason:str,pnl:float,exit_sol_usd:float,exit_liquidity_usd:float=0.0,exit_buys_1h:int=0,exit_sells_1h:int=0,exit_volume_1h:float=0.0,exit_price_change_1h_pct:float=0.0):
        row=self.conn.execute('SELECT size_usd FROM positions WHERE id=?',(position_id,)).fetchone();size_usd=float(row['size_usd'] or 10.0) if row else 10.0;pnl_usd=size_usd*pnl/100.0
        self.conn.execute("UPDATE positions SET status='closed',exit_price=?,exit_time=?,exit_reason=?,pnl_pct=?,pnl_usd=?,exit_sol_usd=? WHERE id=?",(exit_price,time.time(),reason,pnl,pnl_usd,exit_sol_usd,position_id));self.conn.commit()
        self.log('paper_sell',payload=f'position_id={position_id};price={exit_price};reason={reason};pnl_pct={pnl};pnl_usd={pnl_usd};exit_sol_usd={exit_sol_usd};exit_liquidity={exit_liquidity_usd};exit_buys1h={exit_buys_1h};exit_sells1h={exit_sells_1h};exit_volume1h={exit_volume_1h};exit_price_change_1h={exit_price_change_1h_pct}')
    def backup(self,keep:int=12)->str|None:
        try:
            source=Path(self.path);d=source.parent/'backups';d.mkdir(parents=True,exist_ok=True);stamp=time.strftime('%Y%m%d-%H%M%S',time.gmtime());target=d/f'{source.stem}-{stamp}.sqlite3';dest=sqlite3.connect(str(target));self.conn.backup(dest);dest.close();files=sorted(d.glob(f'{source.stem}-*.sqlite3'),key=lambda p:p.stat().st_mtime,reverse=True)
            for old in files[keep:]:
                try:old.unlink()
                except OSError:pass
            return str(target)
        except Exception as exc:print(f'[DB] backup failed: {exc}');return None
    def close(self):self.conn.close()
