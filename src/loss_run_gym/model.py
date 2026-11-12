"""Data model for a loss run: the ground truth an extractor should recover."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

COVERAGES = ("WC", "AUTO", "GL")

# Fields an extractor is scored on, one entry per claim.
CLAIM_FIELDS = (
    "claim_number",
    "policy_number",
    "coverage",
    "loss_date",
    "claimant",
    "description",
    "status",
    "paid",
    "reserve",
    "recovered",
)


@dataclass(frozen=True)
class Claim:
    claim_number: str
    policy_number: str
    coverage: str
    loss_date: date
    claimant: str
    description: str
    status: str  # "Open" | "Closed"
    paid: int  # whole dollars
    reserve: int
    recovered: int

    def to_json(self) -> dict:
        d = asdict(self)
        d["loss_date"] = self.loss_date.isoformat()
        return d


@dataclass(frozen=True)
class Policy:
    policy_number: str
    coverage: str
    period_start: date
    period_end: date


@dataclass
class LossRun:
    carrier: str
    carrier_prefix: str
    insured: str
    valuation_date: date
    policies: list[Policy]
    claims: list[Claim] = field(default_factory=list)

    def totals(self) -> dict:
        return {
            "claim_count": len(self.claims),
            "paid": sum(c.paid for c in self.claims),
            "reserve": sum(c.reserve for c in self.claims),
            "recovered": sum(c.recovered for c in self.claims),
        }

    def to_json(self) -> dict:
        return {
            "carrier": self.carrier,
            "insured": self.insured,
            "valuation_date": self.valuation_date.isoformat(),
            "policies": [
                {
                    "policy_number": p.policy_number,
                    "coverage": p.coverage,
                    "period_start": p.period_start.isoformat(),
                    "period_end": p.period_end.isoformat(),
                }
                for p in self.policies
            ],
            "claims": [c.to_json() for c in self.claims],
            "totals": self.totals(),
        }
