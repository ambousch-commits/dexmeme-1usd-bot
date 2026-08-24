from __future__ import annotations
import csv
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from .config import settings
from .db import Database

HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dexmeme · 1USD Bot</title><style>:root{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color-scheme:dark;--bg:#090e1d;--panel:#111a2d;--line:#273451;--text:#eef3ff;--muted:#8f9bb5;--good:#55d187;--bad:#ff6477;--accent:#7c8cff;--accent2:#4e6cff}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#121a30 0,#090e1d 48%);color:var(--text)}main{max-width:1280px;margin:auto;padding:28px 22px 50px}.top{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:22px}.brand h1{margin:0;font-size:30px;letter-spacing:-.03em}.brand p{margin:6px 0;color:var(--muted)}.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.btn{display:inline-flex;align-items:center;gap:8px;text-decoration:none;color:var(--text);background:var(--panel);border:1px solid var(--line);padding:10px 14px;border-radius:10px;font-size:13px;font-weight:650}.btn:hover{border-color:#52648c;background:#17223a}.status{display:flex;align-items:center;gap:8px;background:var(--panel);border:1px solid var(--line);padding:10px 13px;border-radius:999px;color:var(--muted);font-size:13px}.dot{width:9px;height:9px;border-radius:50%;background:var(--good);box-shadow:0 0 10px rgba(85,209,135,.55)}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{background:linear-gradient(180deg,#121c31,#10182a);border:1px solid var(--line);border-radius:16px;padding:18px;min-height:122px}.label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.09em}.value{font-size:29px;font-weight:780;margin-top:8px;letter-spacing:-.02em}.sub{font-size:12px;color:var(--muted);margin-top:5px}section{margin-top:20px}.section-title{font-size:18px;font-weight:750;margin:0 0 10px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;overflow:hidden}.progress{padding:16px}.progress-head{display:flex;justify-content:space-between;gap:12px}.bar{height:12px;background:#1b2743;border-radius:999px;overflow:hidden;margin-top:11px}.fill{height:100%;background:linear-gradient(90deg,var(--accent2),var(--accent));width:0;transition:width .25s}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:13px 14px;text-align:left;border-bottom:1px solid var(--line);font-size:13px;vertical-align:middle}.table th{color:var(--muted);font-weight:650}.table tr:last-child td{border-bottom:0}.good{color:var(--good)}.bad{color:var(--bad)}.muted{color:var(--muted)}.token{font-weight:750}.address{display:block;color:var(--muted);font-size:11px;margin-top:3px;max-width:520px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.reason{display:inline-block;padding:5px 9px;border-radius:999px;background:#202d4b;color:#d8e0f5;font-size:11px}.empty{padding:30px;text-align:center;color:var(--muted)}.footer{color:var(--muted);text-align:center;margin-top:18px;font-size:12px}@media(max-width:950px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.top{flex-direction:column}.actions{justify-content:flex-start}}@media(max-width:600px){.grid{grid-template-columns:1fr}.table{min-width:850px}.panel{overflow-x:auto}.actions{width:100%}.btn{flex:1;justify-content:center}.status{width:max-content}}</style></head><body><main><div class="top"><div class="brand"><h1>dexmeme · 1USD Bot</h1><p>Paper trading · $1 net target · $10 position size · 100+ trades/day research goal</p></div><div class="actions"><a class="btn" href="/api/trades.csv" download>⇩ Export trades CSV</a><a class="btn" href="/api/events.csv" download>⇩ Export events CSV</a><div class="status"><span class="dot"></span><span id="status">LIVE · refreshing</span></div></div></div><section class="grid" id="cards"></section><section><h2 class="section-title">Daily progress</h2><div class="panel progress"><div class="progress-head"><span id="goalLabel">0 / 100 trades</span><span class="muted" id="todayPnl">$0 today</span></div><div class="bar"><div class="fill" id="goalFill"></div></div></div></section><section><h2 class="section-title">Open positions</h2><div class="panel" id="positions"></div></section><section><h2 class="section-title">Recent closed trades</h2><div class="panel" id="trades"></div></section><div class="footer">Paper mode only · live refresh every 3 seconds · history is preserved on the Railway volume</div></main><script>const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const num=v=>Number(v||0);function fmt(v,d=6){return num(v).toLocaleString(undefined,{maximumFractionDigits:d})}function render(s){const cards=[['Trades today',`${s.trades_today}/${s.daily_trade_goal}`,'daily goal'],['Target / trade','$'+fmt(s.target_net_usd,2),'net after modeled costs'],['Today P&L','$'+fmt(s.pnl_today_usd,4),'closed trades today'],['Total trades',s.trades_total,'paper trades'],['Win rate',s.win_rate_pct+'%',s.closed_trades+' closed'],['Total P&L','$'+fmt(s.realized_pnl_usd,4),'realized paper P&L'],['Wins',s.wins,'closed winners'],['Losses',s.losses,'closed losers']];document.getElementById('cards').innerHTML=cards.map(c=>`<div class="card"><div class="label">${c[0]}</div><div class="value">${esc(c[1])}</div><div class="sub">${esc(c[2])}</div></div>`).join('');const pct=Math.min(100,(num(s.trades_today)/Math.max(1,num(s.daily_trade_goal)))*100);document.getElementById('goalFill').style.width=pct+'%';document.getElementById('goalLabel').textContent=`${s.trades_today} / ${s.daily_trade_goal} trades`;document.getElementById('todayPnl').textContent=`$${fmt(s.pnl_today_usd,4)} today`;const pos=s.positions||[];document.getElementById('positions').innerHTML=pos.length?`<table class="table"><thead><tr><th>Token</th><th>Entry</th><th>Target</th><th>Size</th></tr></thead><tbody>${pos.map(p=>`<tr><td><span class="token">${esc(p.symbol)}</span><span class="address">${esc(p.token_address)}</span></td><td>$${fmt(p.entry_price,10)}</td><td class="good">+${fmt(p.target_pct,3)}%</td><td>$${fmt(p.size_usd,2)}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">No open paper positions right now.</div>';const trades=s.recent_trades||[];document.getElementById('trades').innerHTML=trades.length?`<table class="table"><thead><tr><th>Token</th><th>Entry time</th><th>Exit time</th><th>Entry → Exit</th><th>P&L %</th><th>P&L $</th><th>Reason</th></tr></thead><tbody>${trades.map(t=>`<tr><td><span class="token">${esc(t.symbol)}</span></td><td>${esc(t.entry_time||'—')}</td><td>${esc(t.exit_time||'—')}</td><td>$${fmt(t.entry_price,10)} → $${fmt(t.exit_price,10)}</td><td class="${num(t.pnl_pct)>=0?'good':'bad'}">${num(t.pnl_pct)>=0?'+':''}${fmt(t.pnl_pct,3)}%</td><td class="${num(t.pnl_usd)>=0?'good':'bad'}">${num(t.pnl_usd)>=0?'+':''}$${fmt(t.pnl_usd,4)}</td><td><span class="reason">${esc(t.exit_reason||'closed')}</span></td></tr>`).join('')}</tbody></table>`:'<div class="empty">No closed trades yet.</div>';document.getElementById('status').textContent='LIVE · updated now'}async function refresh(){try{const r=await fetch('/api/stats',{cache:'no-store'});if(!r.ok)throw Error();render(await r.json())}catch(e){document.getElementById('status').textContent='OFFLINE · retrying'}}refresh();setInterval(refresh,3000)</script></body></html>'''

def db_candidates():
    paths=[]
    configured=os.path.abspath(settings.db_path)
    paths.append(configured)
    roots=['/data','/app/data','/app',os.getcwd()]
    for root in roots:
        if not os.path.isdir(root): continue
        try:
            for name in sorted(os.listdir(root)):
                if name.endswith(('.sqlite3','.db','.sqlite')):
                    p=os.path.abspath(os.path.join(root,name))
                    if p not in paths: paths.append(p)
        except Exception: pass
    return paths

def active_db():
    best=None
    for path in db_candidates():
        if not os.path.isfile(path): continue
        db=None
        try:
            db=Database(path)
            positions=int(db.conn.execute('SELECT COUNT(*) FROM positions').fetchone()[0])
            events=int(db.conn.execute('SELECT COUNT(*) FROM events').fetchone()[0])
            score=positions*1000000+events
            if best is None or score>best[0]:
                if best is not None: best[2].close()
                best=(score,path,db,positions,events)
            else: db.close()
        except Exception:
            try:
                if db: db.close()
            except Exception: pass
    return best

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/health':
            best=active_db(); body={'ok':True,'mode':'paper','configured_db':settings.db_path,'db_candidates':db_candidates()}
            if best: body.update({'active_db':best[1],'positions_count':best[3],'events_count':best[4]})
            self._json(body); return
        if path=='/api/stats':
            best=active_db()
            if best is None:
                self._json({'mode':'paper','trades_total':0,'error':'No SQLite database found'}); return
            _,db_path,db,_,_=best
            try:
                total=int(db.conn.execute('SELECT COUNT(*) FROM positions').fetchone()[0]); closed=int(db.conn.execute("SELECT COUNT(*) FROM positions WHERE status='closed'").fetchone()[0]); opens=int(db.conn.execute("SELECT COUNT(*) FROM positions WHERE status='open'").fetchone()[0]); wins=int(db.conn.execute("SELECT COUNT(*) FROM positions WHERE status='closed' AND pnl_pct>0").fetchone()[0]); losses=closed-wins
                row=db.conn.execute("SELECT COALESCE(SUM(pnl_usd),0),COALESCE(AVG(pnl_pct),0) FROM positions WHERE status='closed'").fetchone(); today=db.conn.execute("SELECT COUNT(*),COALESCE(SUM(pnl_usd),0) FROM positions WHERE status='closed' AND date(exit_time)=date('now')").fetchone(); rows=db.conn.execute("SELECT symbol,entry_price,entry_time,exit_price,exit_time,pnl_pct,pnl_usd,exit_reason FROM positions WHERE status='closed' ORDER BY exit_time DESC LIMIT 15").fetchall(); events=int(db.conn.execute('SELECT COUNT(*) FROM events').fetchone()[0])
                body={'mode':'paper','trades_total':total,'closed_trades':closed,'open_positions':opens,'wins':wins,'losses':losses,'win_rate_pct':round(wins/closed*100,2) if closed else 0,'realized_pnl_usd':round(float(row[0]),6),'average_closed_pnl_pct':round(float(row[1]),4),'target_net_usd':settings.target_net_usd,'position_size_usd':settings.position_size_usd,'daily_trade_goal':settings.daily_trade_goal,'trades_today':int(today[0]),'pnl_today_usd':round(float(today[1]),6),'positions':[p.__dict__ for p in db.open_positions()],'recent_trades':[dict(r) for r in rows],'active_db':db_path,'events_total':events}
                self._json(body)
            finally: db.close()
            return
        if path=='/api/trades.csv':
            best=active_db()
            if best is None: self.send_response(404); self.end_headers(); return
            _,_,db,_,_=best
            try:
                rows=db.conn.execute("SELECT id,token_address,pair_address,symbol,entry_price,entry_time,size_sol,target_pct,status,exit_price,exit_time,exit_reason,pnl_pct,size_usd,entry_sol_usd,exit_sol_usd,pnl_usd FROM positions ORDER BY entry_time ASC").fetchall()
                out=io.StringIO(); writer=csv.writer(out); writer.writerow(['id','token_address','pair_address','symbol','entry_price','entry_time','size_sol','target_pct','status','exit_price','exit_time','exit_reason','pnl_pct','size_usd','entry_sol_usd','exit_sol_usd','pnl_usd']); writer.writerows([tuple(r) for r in rows]); body=out.getvalue().encode('utf-8')
            finally: db.close()
            self._csv(body,'dexmeme-1usd-trades.csv'); return
        if path=='/api/events.csv':
            best=active_db()
            if best is None: self.send_response(404); self.end_headers(); return
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
        b=text.encode(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b)
    def _csv(self,body:bytes,name:str):
        self.send_response(200); self.send_header('Content-Type','text/csv; charset=utf-8'); self.send_header('Content-Disposition',f'attachment; filename="{name}"'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)

def serve(host='0.0.0.0',port=None): ThreadingHTTPServer((host,port or settings.port),Handler).serve_forever()
