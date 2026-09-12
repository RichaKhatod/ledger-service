from dataclasses import dataclass
from enum import Enum

class Decision(Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"
    
    
@dataclass
class PolicyResult:
    decision: Decision
    reason: str


def evaluate(amount, vendor, envelope):
    if amount<=0:
        return PolicyResult(Decision.REJECT, "amount can't be less than zero")
    
    if envelope.vendor_allowlist and vendor not in envelope.vendor_allowlist:
        return PolicyResult(Decision.REJECT, "vendor can't be none")
    
    if amount > envelope.per_txn_limit:
        return PolicyResult(Decision.REJECT, "your per transaction limit is exhausted")
    
    if envelope.spent_today + amount > envelope.daily_limit:
        return PolicyResult(Decision.REJECT, "your daily limit is exhausted")
    
    if envelope.spent_this_month + amount > envelope.monthly_limit:
        return PolicyResult(Decision.REJECT, "your monthly limit is exhausted")
    
    if amount > envelope.auto_approve_threshold:
        return PolicyResult(Decision.ESCALATE, "your auto approve request is escalated")
    
    return PolicyResult(Decision.APPROVE, "All policy checks passed")