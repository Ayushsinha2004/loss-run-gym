"""A deliberately naive single-pass extractor.

It reads the PDF text line by line and treats any line with four money amounts as a claim. It
exists to show which traps a one-pass approach falls into, so it is meant to fail on messy files.
Plug your own extractor in by writing its output as JSON and running `lrg score`.
"""

from __future__ import annotations

import re

import pdfplumber

MONEY = r"-?[\d,]+\.\d{2}"
ROW = re.compile(rf"^(?P<left>.+?)\s+(?P<paid>{MONEY})\s+(?P<reserve>{MONEY})\s+(?P<recovered>{MONEY})\s+(?P<incurred>{MONEY})$")
DATE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
STATUS = re.compile(r"\b(Open|Closed)$")
COV = {"Workers Compensation": "WC", "Commercial Auto": "AUTO", "General Liability": "GL"}
POLICY_COL = re.compile(r"^[A-Z]{2}-(WC|AUTO|GL)-\d{6}$")


def extract(pdf_path: str) -> list[dict]:
    claims: list[dict] = []
    coverage = None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                line = line.strip()
                for name, code in COV.items():
                    if line.startswith(f"Line of Business: {name}"):
                        coverage = code
                m = ROW.match(line)
                if not m:
                    continue
                tokens = m.group("left").split()
                policy = None
                if tokens and POLICY_COL.match(tokens[0]):
                    policy = tokens.pop(0)
                left = " ".join(tokens)
                d = DATE.search(left)
                status = STATUS.search(left)
                rest = left
                if status:
                    rest = rest[: status.start()].strip()
                after_date = rest[d.end():].strip().split() if d else []
                claims.append(
                    {
                        "claim_number": tokens[0] if tokens else "",
                        "policy_number": policy,
                        "coverage": coverage,
                        "loss_date": d.group(1) if d else None,
                        "claimant": " ".join(after_date[:2]),
                        "description": " ".join(after_date[2:]),
                        "status": status.group(1) if status else None,
                        "paid": m.group("paid"),
                        "reserve": m.group("reserve"),
                        "recovered": m.group("recovered"),
                    }
                )
    return claims
