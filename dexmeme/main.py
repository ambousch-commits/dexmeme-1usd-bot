from __future__ import annotations
import asyncio, logging, threading, os
from .config import settings
from .db import Database
from .dexscreener import DexScreenerClient
from .safety import SolanaSafetyClient
from .strategy import entry_allowed, exit_reason, pnl_pct, gross_target_pct
from .dashboard import serve

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log=logging.getLogger('dexmeme-1usd')

def start_dashboard():
    t=threading.Thread(target=serve, kwargs={'host':'0.0.0.0','port':settings.port}, daemon=True); t.start(); log.info('dashboard on %s',settings.port)

async def run():
    start_dashboard(); db=Database(settings.db_path); dex=DexScreenerClient(settings); safety=SolanaSafetyClient(settings.solana_rpc_url,settings.request_timeout_seconds)
    try:
        while True:
            try:
                await manage_open_positions(db,dex)
                if db.open_count()<settings.max_open_positions:
                    candidates=await dex.discover_candidates(); sol=await dex.sol_price_usd()
                    for pair in candidates:
                        if db.open_count()>=settings.max_open_positions: break
                        if not entry_allowed(pair,settings) or db.has_open_token(pair.token_address): continue
                        if settings.require_authorities_revoked:
                            safe=await safety.token_safety(pair.token_address)
                            if not safe.safe:
                                db.log('safety_reject',pair.token_address,pair.pair_address,f'mint={safe.mint_authority};freeze={safe.freeze_authority}'); continue
                        target=gross_target_pct(pair,settings,sol)
                        db.open_position(pair,settings.position_size_sol,target)
                        log.info('PAPER BUY %s target=%.3f%% liquidity=$%.0f buys=%d',pair.symbol,target,pair.liquidity_usd,pair.buys_24h)
                await asyncio.sleep(settings.poll_seconds)
            except asyncio.CancelledError: raise
            except Exception:
                log.exception('loop error'); await asyncio.sleep(min(30,max(2,settings.poll_seconds*2)))
    finally:
        await safety.close(); await dex.close(); db.close()

async def manage_open_positions(db,dex):
    positions=db.open_positions()
    if not positions:return
    await asyncio.gather(*(check_position(p,db,dex) for p in positions), return_exceptions=True)

async def check_position(pos,db,dex):
    pairs=await dex.token_pairs(pos.token_address); pair=next((p for p in pairs if p.pair_address==pos.pair_address),None)
    if pair is None or pair.price_usd<=0:return
    reason=exit_reason(pos.entry_price,pair.price_usd,pos.target_pct,settings)
    if reason:
        pnl=pnl_pct(pos.entry_price,pair.price_usd); db.close_position(pos.id,pair.price_usd,reason,pnl); log.info('PAPER SELL %s %s %.2f%%',pos.symbol,reason,pnl)

if __name__=='__main__': asyncio.run(run())
