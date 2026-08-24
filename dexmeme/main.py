from __future__ import annotations
import asyncio,logging,threading,time
from .config import settings
from .db import Database
from .dexscreener import DexScreenerClient
from .safety import SolanaSafetyClient
from .strategy import entry_allowed,exit_reason,pnl_pct,gross_target_pct
from .dashboard import serve
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s');log=logging.getLogger('dexmeme-1usd')
def start_dashboard():
    t=threading.Thread(target=serve,kwargs={'host':'0.0.0.0','port':settings.port},daemon=True);t.start();log.info('dashboard listening on %s',settings.port)
def emergency_reason(pos,pair):
    entry_liq=pos.entry_liquidity_usd or 0
    if entry_liq>0 and pair.liquidity_usd<=entry_liq*(1-settings.emergency_liquidity_drop_pct/100):return 'emergency_liquidity_drop'
    if pair.buys_1h>0 and pair.sells_1h>=pair.buys_1h*settings.emergency_sell_buy_ratio and pnl_pct(pos.entry_price,pair.price_usd)<=-settings.emergency_price_drop_pct:return 'emergency_sell_pressure'
    return None
async def manage_open_positions(db,dex):
    positions=db.open_positions()
    if not positions:return
    sol_usd=await dex.sol_price_usd();await asyncio.gather(*(check_position(p,db,dex,sol_usd) for p in positions),return_exceptions=True)
async def check_position(pos,db,dex,sol_usd):
    pairs=await dex.token_pairs(pos.token_address);pair=next((p for p in pairs if p.pair_address==pos.pair_address),None)
    if pair is None or pair.price_usd<=0:return
    change=pnl_pct(pos.entry_price,pair.price_usd);reason=emergency_reason(pos,pair) or exit_reason(pos.entry_price,pair.price_usd,pos.target_pct,settings)
    if reason:
        db.close_position(pos.id,pair.price_usd,reason,change,sol_usd,pair.liquidity_usd,pair.buys_1h,pair.sells_1h,pair.volume_1h,pair.price_change_1h_pct)
        log.info('PAPER SELL %s reason=%s pnl=%.2f%% pnl_usd=$%.4f liquidity=$%.0f',pos.symbol,reason,change,pos.size_usd*change/100,pair.liquidity_usd)
def can_enter(db,pair):
    if db.has_open_token(pair.token_address):return False,'open_position'
    if db.has_recent_closed_token(pair.token_address,settings.reentry_cooldown_minutes*60):return False,'reentry_cooldown'
    return True,''
async def run():
    start_dashboard();db=Database(settings.db_path);dex=DexScreenerClient(settings);safety=SolanaSafetyClient(settings.solana_rpc_url,settings.request_timeout_seconds);last_backup=0.0
    try:
        log.info('Starting paper bot: target=$%.2f net, daily goal=%d, size=$%.2f, cooldown=%dm emergency_liq_drop=%.1f%% sell_buy=%.2f',settings.target_net_usd,settings.daily_trade_goal,settings.position_size_usd,settings.reentry_cooldown_minutes,settings.emergency_liquidity_drop_pct,settings.emergency_sell_buy_ratio);db.backup()
        while True:
            try:
                sol_usd=await dex.sol_price_usd();db.normalize_open_sizes(sol_usd,settings.position_size_usd);await manage_open_positions(db,dex)
                if db.open_count()<settings.max_open_positions:
                    for pair in await dex.discover_candidates():
                        if db.open_count()>=settings.max_open_positions:break
                        allowed,why=can_enter(db,pair)
                        if not allowed:
                            if why=='reentry_cooldown':db.log('reentry_reject',pair.token_address,pair.pair_address,'cooldown_minutes=%d'%settings.reentry_cooldown_minutes)
                            continue
                        if not entry_allowed(pair,settings):continue
                        if settings.require_authorities_revoked:
                            safe=await safety.token_safety(pair.token_address)
                            if not safe.safe:db.log('safety_reject',pair.token_address,pair.pair_address,f'mint={safe.mint_authority};freeze={safe.freeze_authority}');continue
                        target=gross_target_pct(pair,settings,sol_usd);pos=db.open_position(pair,settings.position_size_usd,sol_usd,target)
                        log.info('PAPER BUY %s target=%.3f%% size=$%.2f (%.6f SOL) liquidity=$%.0f buys=%d sells=%d',pos.symbol,target,pos.size_usd,pos.size_sol,pair.liquidity_usd,pair.buys_24h,pair.sells_24h)
                if time.time()-last_backup>=300:
                    backup=db.backup();last_backup=time.time()
                    if backup:log.info('TRADE HISTORY BACKUP %s',backup)
                await asyncio.sleep(settings.poll_seconds)
            except asyncio.CancelledError:raise
            except Exception:log.exception('loop error; continuing');await asyncio.sleep(min(30,max(2,settings.poll_seconds*2)))
    finally:await safety.close();await dex.close();db.close()
if __name__=='__main__':asyncio.run(run())
