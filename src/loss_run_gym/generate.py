"""Deterministic generator for synthetic loss-run ground truth.

All names, carriers and numbers are invented. The same seed always gives the same loss run.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from .model import COVERAGES, Claim, LossRun, Policy

CARRIERS = [
    ("Harbourline Mutual", "HM"),
    ("Redcliff Casualty", "RC"),
    ("Northgate Specialty", "NG"),
    ("Silverreach Insurance", "SR"),
]
INSUREDS = [
    "Kestrel Logistics LLC",
    "Bluewater Bakeries Inc",
    "Ironbark Construction Co",
    "Maple Row Senior Living",
]
FIRST = ["J.", "M.", "A.", "R.", "S.", "T.", "L.", "D."]
LAST = ["Alvarez", "Brennan", "Chu", "Doyle", "Okafor", "Patel", "Novak", "Reyes", "Svensson"]
DESCRIPTIONS = {
    "WC": ["Lower back strain lifting pallet", "Laceration to hand", "Slip on wet floor", "Shoulder sprain", "Repetitive wrist strain"],
    "AUTO": ["Rear-ended at signal", "Backing into bollard", "Side-swipe on highway", "Windshield damage", "Hit parked vehicle"],
    "GL": ["Customer trip and fall", "Property damage at client site", "Product damage claim", "Water damage to tenant unit"],
}


def generate(seed: int, n_claims: int = 35, years: int = 3) -> LossRun:
    rng = random.Random(seed)
    carrier, prefix = rng.choice(CARRIERS)
    insured = rng.choice(INSUREDS)
    valuation = date(2026, 10, 31)

    policies: list[Policy] = []
    for cov in COVERAGES:
        for y in range(years):
            start = date(2023 + y, 7, 1)
            policies.append(
                Policy(
                    policy_number=f"{prefix}-{cov}-{rng.randint(100000, 999999)}",
                    coverage=cov,
                    period_start=start,
                    period_end=date(start.year + 1, 7, 1),
                )
            )

    claims: list[Claim] = []
    used: set[str] = set()
    for _ in range(n_claims):
        pol = rng.choice(policies)
        loss = pol.period_start + timedelta(days=rng.randint(0, 364))
        loss = min(loss, valuation - timedelta(days=1))
        while True:
            num = f"{prefix}-{pol.coverage}-{str(loss.year)[2:]}-{rng.randint(0, 99999):05d}"
            if num not in used:
                used.add(num)
                break
        status = "Closed" if (valuation - loss).days > 400 and rng.random() < 0.8 else rng.choice(["Open", "Closed"])
        roll = rng.random()
        if roll < 0.12:  # closed without payment: a zero-value claim that is still a real claim
            paid = reserve = recovered = 0
            status = "Closed"
        else:
            paid = rng.randint(1, 60) * 250
            reserve = 0 if status == "Closed" else rng.randint(1, 80) * 500
            recovered = rng.choice([0, 0, 0, rng.randint(1, 8) * 100])
            recovered = min(recovered, paid)
        claims.append(
            Claim(
                claim_number=num,
                policy_number=pol.policy_number,
                coverage=pol.coverage,
                loss_date=loss,
                claimant=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                description=rng.choice(DESCRIPTIONS[pol.coverage]),
                status=status,
                paid=paid,
                reserve=reserve,
                recovered=recovered,
            )
        )

    claims.sort(key=lambda c: (COVERAGES.index(c.coverage), c.policy_number, c.loss_date, c.claim_number))
    return LossRun(carrier, prefix, insured, valuation, policies, claims)
