"""薬機法広告チェッカー

使い方:
    from checker import Checker
    c = Checker()
    result = c.check("シミが消える美容液", category="化粧品")
    print(result.verdict, result.rationale)
"""

from .judge import Checker, CheckResult
from .retrieve import ReferenceIndex, Retrieval

__all__ = ["Checker", "CheckResult", "ReferenceIndex", "Retrieval"]
