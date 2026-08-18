from __future__ import annotations
import asyncio
import logging
import threading
from .config import settings
from .db import Database
from .dexscreener import DexScreenerClient
from .safety import SolanaSafetyClient
from .strategy import entry_allowed, exit_reason, pnl_pct, gross_target_pct
from .dashboard import serve

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('dexmeme-1usd')

def start_dashboard():
    t = threading.Thread(target=serve, kwargs={'host': '0.0.0.0', 'port': settings.port}, daemon=True)
    t.start()
    log.info('dashboard listening on %s', settings.port)

async def manage_open_positions(db, dex):
    positions = db.open_positions()
    if not positions:
        return
    await asyncio.gather(*(check_position(p, db, dex) for p in positions), return_exceptions=True)

async def check_position(pos, db, dex):
    pairs = await dex.token_pairs(pos.token_address)
    pair = next((p for p in pairs if p.pair_address == pos.pair_address), None)
    if pair is None or pair.price_usd <= 0:
        return
    reason = exit_reason(pos.entry_price, pair.price_usd, pos.target_pct, settings)
    if reason:
        pnl = pnl_pct(pos.entry_price, pair.price_usd)
        db.close_position(pos.id, pair.price_usd, reason, pnl)
        log.info('PAPER SELL %s reason=%s pnl=%.2f%%', pos.symbol, reason, pnl)

async def run():
    start_dashboard()
    db = Database(settings.db_path)
    dex = DexScreenerClient(settings)
    safety = SolanaSafetyClient(settings.solana_rpc_url, settings.request_timeout_seconds)
    try:
        log.info('Starting paper bot: target=$%.2f net, daily goal=%d, size=$%.2f USD', settings.target_net_usd, settings.daily_trade_goal, settings.position_size_usd)
        while True:
            try:
                await manage_open_positions(db, dex)
                if db.open_count() < settings.max_open_positions:
                    candidates = await dex.discover_candidates()
                    sol_usd = await dex.sol_price_usd()
                    if sol_usd <= 0:
                        raise ValueError('SOL/USD price unavailable')
                    for pair in candidates:
                        if db.open_count() >= settings.max_open_positions:
                            break
                        if not entry_allowed(pair, settings) or db.has_open_token(pair.token_address):
                            continue
                        if settings.require_authorities_revoked:
                            safe = await safety.token_safety(pair.token_address)
                            if not safe.safe:
                                db.log('safety_reject', pair.token_address, pair.pair_address, f'mint={safe.mint_authority};freeze={safe.freeze_authority}')
                                continue
                        target = gross_target_pct(pair, settings, sol_usd)
                        size_sol = settings.position_size_usd / sol_usd
                        pos = db.open_position(pair, size_sol, target)
                        log.info('PAPER BUY %s target=%.3f%% size=$%.2f (%.6f SOL) liquidity=$%.0f buys=%d', pos.symbol, target, settings.position_size_usd, size_sol, pair.liquidity_usd, pair.buys_24h)
                await asyncio.sleep(settings.poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception('loop error; continuing')
                await asyncio.sleep(min(30, max(2, settings.poll_seconds * 2)))
    finally:
        await safety.close()
        await dex.close()
        db.close()

if __name__ == '__main__':
    asyncio.run(run())
