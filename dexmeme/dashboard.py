from __future__ import annotations
import csv
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from .config import settings
from .db import Database

HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dexmeme · 1USD Bot</title></head><body><main><h1>dexmeme · 1USD Bot</h1><p>Paper trading · $1 net target · $10 position size</p><p><a href="/api/trades.csv" download>Export all trades CSV</a> · <a href="/api/events.csv" download>Export all events CSV</a></p><div id="app">Loading…</div><script>async function r(){try{const x=await fetch('/api/stats',{cache:'no-store'});document.getElementById('app').textContent=JSON.stringify(await x.json(),null,2)}catch(e){document.getElementById('app').textContent='OFFLINE'}}r();setInterval(r,3000)</script></main></body></html>'''

def db_candidates():
    paths=[]
    configured=os.path.abspath(settings.db_path)
    paths.append(configured)
    roots=['/data','/app/data','/app',os.getcwd()]
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for name in sorted(os.listdir(root)):
                if name.endswith(('.sqlite3','.db','.sqlite')):
                    p=os.path.abspath(os.path.join(root,name))
                    if p not in paths: paths.append(p)
        except Exception:
            pass
    return paths

def active_db():
    best=None
    for path in db_candidates():
        if not os.path.isfile(path):
            continue
        db=None
        try:
            db=Database(path)
            positions=int(db.conn.execute('SELECT COUNT(*) FROM positions').fetchone()[0])
            events=int(db.conn.execute('SELECT COUNT(*) FROM events').fetchone()[0])
            score=positions*1000000+events
            if best is None or score>best[0]:
                if best is not None: best[2].close()
                best=(score,path,db,positions,events)
            else:
                db.close()
        except Exception:
            try:
                if db: db.close()
            except Exception: pass
    return best

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/health':
            best=active_db()
            body={'ok':True,'mode':'paper','configured_db':settings.db_path,'db_candidates':db_candidates()}
            if best: body.update({'active_db':best[1],'positions_count':best[3],'events_count':best[4]})
            self._json(body); return
        if path=='/api/stats':
            best=active_db()
            if best is None:
                self._json({'mode':'paper','trades_total':0,'error':'No SQLite database found'}); return
            _,db_path,db,_,_=best
            try:
                total=int(db.conn.execute('SELECT COUNT(*) FROM positions').fetchone()[0]); closed=int(db.conn.execute("SELECT COUNT(*) FROM positions WHERE status='closed'").fetchone()[0]); opens=int(db.conn.execute("SELECT COUNT(*) FROM positions WHERE status='open'").fetchone()[0]); wins=int(db.conn.execute("SELECT COUNT(*) FROM positions WHERE status='closed' AND pnl_pct>0").fetchone()[0]); losses=closed-wins
                row=db.conn.execute("SELECT COALESCE(SUM(pnl_usd),0),COALESCE(AVG(pnl_pct),0) FROM positions WHERE status='closed'").fetchone(); today=db.conn.execute("SELECT COUNT(*),COALESCE(SUM(pnl_usd),0) FROM positions WHERE status='closed' AND date(exit_time)=date('now')").fetchone(); rows=db.conn.execute("SELECT symbol,entry_price,entry_time,exit_price,exit_time,pnl_pct,pnl_usd,exit_reason FROM positions WHERE status='closed' ORDER BY exit_time DESC LIMIT 15").fetchall()
                events=int(db.conn.execute('SELECT COUNT(*) FROM events').fetchone()[0])
                body={'mode':'paper','trades_total':total,'closed_trades':closed,'open_positions':opens,'wins':wins,'losses':losses,'win_rate_pct':round(wins/closed*100,2) if closed else 0,'realized_pnl_usd':round(float(row[0]),6),'average_closed_pnl_pct':round(float(row[1]),4),'target_net_usd':settings.target_net_usd,'position_size_usd':settings.position_size_usd,'daily_trade_goal':settings.daily_trade_goal,'trades_today':int(today[0]),'pnl_today_usd':round(float(today[1]),6),'positions':[p.__dict__ for p in db.open_positions()],'recent_trades':[dict(r) for r in rows],'active_db':db_path,'events_total':events}
                self._json(body)
            finally: db.close()
            return
        if path=='/api/trades.csv':
            best=active_db()
            if best is None:
                self.send_response(404); self.end_headers(); return
            _,_,db,_,_=best
            try:
                rows=db.conn.execute("SELECT id,token_address,pair_address,symbol,entry_price,entry_time,size_sol,target_pct,status,exit_price,exit_time,exit_reason,pnl_pct,size_usd,entry_sol_usd,exit_sol_usd,pnl_usd FROM positions ORDER BY entry_time ASC").fetchall()
                out=io.StringIO(); writer=csv.writer(out); writer.writerow(['id','token_address','pair_address','symbol','entry_price','entry_time','size_sol','target_pct','status','exit_price','exit_time','exit_reason','pnl_pct','size_usd','entry_sol_usd','exit_sol_usd','pnl_usd']); writer.writerows([tuple(r) for r in rows]); body=out.getvalue().encode('utf-8')
            finally: db.close()
            self._csv(body,'dexmeme-1usd-trades.csv'); return
        if path=='/api/events.csv':
            best=active_db()
            if best is None:
                self.send_response(404); self.end_headers(); return
            _,_,db,_,_=best
            try:
                rows=db.conn.execute("SELECT id,ts,event,token_address,pair_address,payload FROM events ORDER BY ts ASC").fetchall()
                out=io.StringIO(); writer=csv.writer(out); writer.writerow(['id','timestamp','event','token_address','pair_address','payload']); writer.writerows([tuple(r) for r in rows]); body=out.getvalue().encode('utf-8')
            finally: db.close()
            self._csv(body,'dexmeme-1usd-events.csv'); return
        if path=='/': self._html(HTML); return
        self.send_response(404); self.end_headers()
    def _json(self,obj):
        b=json.dumps(obj).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b)
    def _html(self,text):
        b=text.encode(); self.send_response(200); self.send_response if False else None; self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b)
    def _csv(self,body:bytes,name:str):
        self.send_response(200); self.send_header('Content-Type','text/csv; charset=utf-8'); self.send_header('Content-Disposition',f'attachment; filename="{name}"'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)

def serve(host='0.0.0.0',port=None): ThreadingHTTPServer((host,port or settings.port),Handler).serve_forever()
