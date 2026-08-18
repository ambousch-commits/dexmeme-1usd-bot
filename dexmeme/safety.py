from __future__ import annotations
import httpx

class SafetyResult:
    def __init__(self, safe: bool, owner: str = '', mint_authority: str = '', freeze_authority: str = ''):
        self.safe=safe; self.owner=owner; self.mint_authority=mint_authority; self.freeze_authority=freeze_authority

class SolanaSafetyClient:
    def __init__(self, rpc_url: str, timeout: float):
        self.rpc_url=rpc_url
        self.client=httpx.AsyncClient(timeout=timeout)
    async def close(self): await self.client.aclose()
    async def token_safety(self, token_address: str) -> SafetyResult:
        # Conservative default for paper trading: reject if RPC cannot confirm the mint state.
        try:
            r=await self.client.post(self.rpc_url,json={'jsonrpc':'2.0','id':1,'method':'getAccountInfo','params':[token_address,{'encoding':'jsonParsed'}]})
            r.raise_for_status(); data=r.json().get('result',{}).get('value')
            if not data: return SafetyResult(False)
            parsed=((data.get('data') or {}).get('parsed') or {}).get('info') or {}
            mint=parsed.get('mintAuthority'); freeze=parsed.get('freezeAuthority')
            return SafetyResult(mint is None and freeze is None, '', str(mint or ''), str(freeze or ''))
        except Exception:
            return SafetyResult(False)
