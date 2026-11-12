"""Score an extractor's claims against ground truth.

Row count and totals are read together: a run can match the financial totals of the rows it found
while still missing claims, so totals alone are never treated as success.

Claims are paired by normalised claim number first. Whatever is left is paired by an optimal
assignment over coverage, loss date, claimant, description and claim-number similarity, so a
typo in the claim number does not turn one claim into a "missing" plus an "extra".
"""

from __future__ import annotations

import re
from datetime import date, datetime
from difflib import SequenceMatcher

import numpy as np
from scipy.optimize import linear_sum_assignment

from .model import CLAIM_FIELDS

MONEY_FIELDS = ("paid", "reserve", "recovered")
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%b %d, %Y")
PAIR_THRESHOLD = 0.55


def norm_money(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = str(v).strip().replace("$", "").replace(",", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        x = float(s)
    except ValueError:
        return None
    return round(-x if neg else x, 2)


def norm_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def norm_text(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().casefold()


def norm_claim_number(v) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(v or "").upper())


def field_equal(name: str, a, b) -> bool:
    if name in MONEY_FIELDS:
        return norm_money(a) == norm_money(b)
    if name == "loss_date":
        return norm_date(a) is not None and norm_date(a) == norm_date(b)
    if name in ("claim_number", "policy_number"):
        return norm_claim_number(a) == norm_claim_number(b)
    return norm_text(a) == norm_text(b)


def _sim(p: dict, t: dict) -> float:
    s = 0.0
    s += 0.25 * SequenceMatcher(None, norm_claim_number(p.get("claim_number")), norm_claim_number(t["claim_number"])).ratio()
    s += 0.20 * field_equal("coverage", p.get("coverage"), t["coverage"])
    s += 0.25 * field_equal("loss_date", p.get("loss_date"), t["loss_date"])
    s += 0.15 * SequenceMatcher(None, norm_text(p.get("claimant")), norm_text(t["claimant"])).ratio()
    s += 0.15 * SequenceMatcher(None, norm_text(p.get("description")), norm_text(t["description"])).ratio()
    return s


def score(pred: list[dict], truth: list[dict]) -> dict:
    t_by_num = {norm_claim_number(t["claim_number"]): i for i, t in enumerate(truth)}
    pairs: list[tuple[int, int]] = []
    used_t: set[int] = set()
    rest_p: list[int] = []
    duplicates = 0
    for i, p in enumerate(pred):
        j = t_by_num.get(norm_claim_number(p.get("claim_number")))
        if j is not None and j not in used_t:
            pairs.append((i, j))
            used_t.add(j)
        elif j is not None:
            duplicates += 1  # same claim number extracted twice
        else:
            rest_p.append(i)

    rest_t = [j for j in range(len(truth)) if j not in used_t]
    if rest_p and rest_t:
        cost = np.array([[1 - _sim(pred[i], truth[j]) for j in rest_t] for i in rest_p])
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols):
            if 1 - cost[r, c] >= PAIR_THRESHOLD:
                pairs.append((rest_p[r], rest_t[c]))
                used_t.add(rest_t[c])
    paired_p = {i for i, _ in pairs}

    field_acc = {}
    for f in CLAIM_FIELDS:
        if pairs:
            field_acc[f] = round(sum(field_equal(f, pred[i].get(f), truth[j][f]) for i, j in pairs) / len(pairs), 4)
        else:
            field_acc[f] = 0.0

    n_t, n_p = len(truth), len(pred)
    pred_tot = {f: round(sum(norm_money(p.get(f)) or 0 for p in pred), 2) for f in MONEY_FIELDS}
    true_tot = {f: round(float(sum(t[f] for t in truth)), 2) for f in MONEY_FIELDS}

    return {
        "truth_claims": n_t,
        "predicted_claims": n_p,
        "row_count_accuracy": round(max(0.0, 1 - abs(n_p - n_t) / n_t), 4) if n_t else 0.0,
        "matched": len(pairs),
        "missing": n_t - len(used_t),
        "extra": n_p - len(paired_p),
        "duplicates": duplicates,
        "field_accuracy": field_acc,
        "mean_field_accuracy": round(sum(field_acc.values()) / len(field_acc), 4),
        "totals": {"predicted": pred_tot, "truth": true_tot, "match": pred_tot == true_tot},
        "pass": n_p == n_t and len(pairs) == n_t and pred_tot == true_tot,
    }
