from dexmeme.config import Settings
from dexmeme.models import Pair
from dexmeme.strategy import entry_allowed, exit_reason, pnl_pct, gross_target_pct

def test_stop_loss():
    s=Settings()
    assert exit_reason(100,97.5,2,s)=='stop_loss'

def test_target_can_cover_cost_and_net_dollar_goal():
    s=Settings()
    p=Pair('solana','dex','pair','token','T','T',1.0,10000,0,200,100,20,10,5000,5.0,'')
    assert gross_target_pct(p,s,200.0)>=1.5

def test_entry_filter():
    s=Settings()
    p=Pair('solana','dex','pair','token','T','T',1.0,10000,0,200,100,20,10,5000,5.0,'')
    assert entry_allowed(p,s)

def test_pnl():
    assert pnl_pct(100,95)==-5.0
