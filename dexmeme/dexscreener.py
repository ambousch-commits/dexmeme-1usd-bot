from __future__ import annotations
import asyncio
from typing import Any
import httpx
from .config import Settings
from .models import Pair

SOLANA='solana'
WSOL_MINT='So11111111111111111111111111111111111111112'
ALLOWED_QUOTES={'SOL','USDC','USDT','WSOL'}
STABLE_QUOTES={'USDC','USDT'}

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
    async def _get_url(self,url:str)->Any:
        last=None
        for i in range(3):
            try:
                r=await self.client.get(url); r.raise_for_status(); return r.json()
            except (httpx.HTTPError,ValueError) as e:
                last=e; await asyncio.sleep(.5*(i+1))
        raise RuntimeError(f'Price request failed: {last}')
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
        # Resolve SOL from canonical WSOL pairs only. The previous implementation
        # could accidentally select a non-SOL base token from a WSOL-quoted pair.
        data=await self._get(f'/token-pairs/v1/{SOLANA}/{WSOL_MINT}')
        candidates=[]
        for raw in data or []:
            if raw.get('chainId')!=SOLANA: continue
            base=raw.get('baseToken') or {}; quote=raw.get('quoteToken') or {}
            base_addr=str(base.get('address') or '')
            quote_symbol=str(quote.get('symbol') or '').upper()
            price=_num(raw.get('priceUsd'))
            liq=_num((raw.get('liquidity') or {}).get('usd'))
            if base_addr==WSOL_MINT and quote_symbol in STABLE_QUOTES and 10.0 <= price <= 1000.0 and liq>0:
                candidates.append((liq,price))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]

        # Fallback to Jupiter's canonical mint price if DexScreener has no
        # suitable USD-quoted WSOL pair at the moment.
        try:
            data=await self._get_url(f'https://lite-api.jup.ag/price/v3?ids={WSOL_MINT}')
            raw=(data.get(WSOL_MINT) or {}) if isinstance(data,dict) else {}
            price=_num(raw.get('usdPrice') or raw.get('price'))
            if 10.0 <= price <= 1000.0:
                return price
        except Exception:
            pass
        raise RuntimeError('Unable to resolve canonical SOL/USD price')

def _num(v:Any)->float:
    try:return float(v or 0)
    except (TypeError,ValueError):return 0.0
