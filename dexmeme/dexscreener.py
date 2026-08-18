from __future__ import annotations
import asyncio
from typing import Any
import httpx
from .config import Settings
from .models import Pair

SOLANA='solana'
ALLOWED_QUOTES={'SOL','USDC','USDT','WSOL'}

class DexScreenerClient:
    def __init__(self, settings: Settings):
        self.settings=settings
        self.client=httpx.AsyncClient(timeout=settings.request_timeout_seconds, headers={'User-Agent':'dexmeme-1usd-bot/1.0'})
    async def close(self): await self.client.aclose()
    async def _get(self,path:str)->Any:
        last=None
        for i in range(3):
            try:
                r=await self.client.get(self.settings.dex_base_url+path); r.raise_for_status(); return r.json()
            except (httpx.HTTPError,ValueError) as e:
                last=e; await asyncio.sleep(.5*(i+1))
        raise RuntimeError(f'DEX request failed: {last}')
    async def latest_solana_profiles(self):
        data=await self._get('/token-profiles/latest/v1')
        return [x for x in data if x.get('chainId')==SOLANA and x.get('tokenAddress')]
    async def token_pairs(self, token_address:str)->list[Pair]:
        data=await self._get(f'/token-pairs/v1/{SOLANA}/{token_address}')
        out=[]
        for raw in data or []:
            if raw.get('chainId')!=SOLANA or not raw.get('pairAddress'): continue
            base=raw.get('baseToken') or {}; quote=raw.get('quoteToken') or {}
            if quote.get('symbol','').upper() not in ALLOWED_QUOTES: continue
            tx=raw.get('txns') or {}; h24=tx.get('h24') or {}; h1=tx.get('h1') or {}
            vol=raw.get('volume') or {}; change=raw.get('priceChange') or {}; liq=raw.get('liquidity') or {}
            out.append(Pair(SOLANA,str(raw.get('dexId') or ''),str(raw['pairAddress']),str(base.get('address') or token_address),str(base.get('symbol') or '?'),str(base.get('name') or 'Unknown'),_num(raw.get('priceUsd')),_num(liq.get('usd')),int(raw.get('pairCreatedAt') or 0),int(h24.get('buys') or 0),int(h24.get('sells') or 0),int(h1.get('buys') or 0),int(h1.get('sells') or 0),_num(vol.get('h1')),_num(change.get('h1')),str(raw.get('url') or '')))
        return out
    async def discover_candidates(self)->list[Pair]:
        profiles=await self.latest_solana_profiles()
        batches=await asyncio.gather(*(self.token_pairs(p['tokenAddress']) for p in profiles), return_exceptions=True)
        pairs=[]
        for b in batches:
            if not isinstance(b,Exception): pairs.extend(b)
        newest={}
        for p in pairs:
            if p.token_address not in newest or p.pair_created_at_ms>newest[p.token_address].pair_created_at_ms: newest[p.token_address]=p
        return sorted(newest.values(), key=lambda p:p.pair_created_at_ms, reverse=True)
    async def sol_price_usd(self)->float:
        data=await self._get('/latest/dex/search?q=SOL')
        pairs=data.get('pairs') or []
        for p in pairs:
            if p.get('chainId')=='solana' and p.get('priceUsd'):
                try: return float(p['priceUsd'])
                except (TypeError,ValueError): pass
        return 0.0

def _num(v:Any)->float:
    try:return float(v or 0)
    except (TypeError,ValueError):return 0.0
