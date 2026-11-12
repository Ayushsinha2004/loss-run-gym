"""Render a LossRun to a PDF with controllable, realistic messiness.

Each knob reproduces a failure pattern that real loss runs cause for extractors:

- header_policy: the policy number appears once in a section header, never on the claim rows.
- subtotal_rows: per-policy total rows formatted like claim rows.
- ditto_blanks: a blank Status cell means "same as the row above".
- split_tables: claim details and financials sit in two tables pages apart, joined only by claim number.
- page_break_repeat: when a table runs onto a new page, the last row is printed again at the top.
- prefix_typos: one claim number is printed with a typo in the carrier prefix.

The ground truth always holds the correct, de-duplicated claims.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

from .model import COVERAGES, Claim, LossRun

COVERAGE_NAMES = {"WC": "Workers Compensation", "AUTO": "Commercial Auto", "GL": "General Liability"}


@dataclass(frozen=True)
class Messiness:
    header_policy: bool = True
    subtotal_rows: bool = True
    ditto_blanks: bool = True
    split_tables: bool = False
    page_break_repeat: bool = True
    prefix_typos: bool = True

    @classmethod
    def clean(cls) -> "Messiness":
        return cls(False, False, False, False, False, False)

    @classmethod
    def hard(cls) -> "Messiness":
        return cls(True, True, True, True, True, True)

    def to_json(self) -> dict:
        return asdict(self)


def money(v: int) -> str:
    return f"{v:,.2f}"


PAGE_W, PAGE_H = landscape(letter)
MARGIN = 36
ROW_H = 15
TOP = PAGE_H - MARGIN - 40
BOTTOM = MARGIN + 20


class _Doc:
    """Minimal paginating writer over a reportlab canvas."""

    def __init__(self, path: str, run: LossRun):
        self.c = canvas.Canvas(path, pagesize=landscape(letter))
        self.c.setTitle(f"Loss Run - {run.insured}")
        self.run = run
        self.page = 1
        self.y = TOP
        self._page_header()
        self.table: tuple[list[str], list[float]] | None = None
        self.last_row: list[str] | None = None
        self.repeat_on_break = False

    def _page_header(self) -> None:
        c = self.c
        c.setFont("Helvetica-Bold", 12)
        c.drawString(MARGIN, PAGE_H - MARGIN, f"{self.run.carrier}  -  Loss Run Report")
        c.setFont("Helvetica", 9)
        c.drawString(MARGIN, PAGE_H - MARGIN - 14, f"Insured: {self.run.insured}")
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN, f"Valued as of {self.run.valuation_date:%m/%d/%Y}")
        c.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN - 14, f"Page {self.page}")

    def new_page(self) -> None:
        self.c.showPage()
        self.page += 1
        self.y = TOP
        self._page_header()
        if self.table:
            self._draw_row(self.table[0], self.table[1], bold=True)
            if self.repeat_on_break and self.last_row is not None:
                self._draw_row(self.last_row, self.table[1])

    def need(self, rows: int) -> None:
        if self.y - rows * ROW_H < BOTTOM:
            self.new_page()

    def heading(self, text: str, size: int = 10) -> None:
        self.table = None
        self.need(3)
        self.y -= 6
        self.c.setFont("Helvetica-Bold", size)
        self.c.drawString(MARGIN, self.y, text)
        self.y -= ROW_H

    def text(self, text: str) -> None:
        self.need(1)
        self.c.setFont("Helvetica", 9)
        self.c.drawString(MARGIN, self.y, text)
        self.y -= ROW_H

    def start_table(self, header: list[str], widths: list[float], repeat_on_break: bool) -> None:
        self.table = (header, widths)
        self.last_row = None
        self.repeat_on_break = repeat_on_break
        self.need(3)
        self._draw_row(header, widths, bold=True)

    def row(self, cells: list[str], bold: bool = False) -> None:
        assert self.table is not None
        self.need(1)
        self._draw_row(cells, self.table[1], bold=bold)
        self.last_row = cells

    def end_table(self) -> None:
        self.table = None
        self.last_row = None
        self.y -= 6

    def _draw_row(self, cells: list[str], widths: list[float], bold: bool = False) -> None:
        c = self.c
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 8)
        x = MARGIN
        for cell, w in zip(cells, widths):
            if cell and cell[0].isdigit() and ("," in cell or "." in cell):
                c.drawRightString(x + w - 4, self.y, cell)
            else:
                c.drawString(x + 2, self.y, cell)
            x += w
        c.setLineWidth(0.3)
        c.line(MARGIN, self.y - 4, x, self.y - 4)
        self.y -= ROW_H

    def save(self) -> None:
        self.c.save()


def _typo(claim_number: str, rng: random.Random) -> str:
    prefix, rest = claim_number[:2], claim_number[2:]
    letters = [ch for ch in "ABCDEFGHJKLMNPQRSTUVWXYZ" if ch != prefix[1]]
    return prefix[0] + rng.choice(letters) + rest


def render(run: LossRun, path: str, mess: Messiness, seed: int = 0) -> dict:
    """Write the PDF and return a manifest describing which traps were placed."""
    rng = random.Random(seed + 7919)
    doc = _Doc(path, run)
    traps: dict[str, list] = {"typo_claims": [], "subtotal_rows": 0, "repeated_rows": 0}

    typo_target = rng.choice(run.claims).claim_number if (mess.prefix_typos and run.claims) else None

    def shown_number(c: Claim) -> str:
        if c.claim_number == typo_target:
            t = _typo(c.claim_number, rng)
            traps["typo_claims"].append({"printed": t, "correct": c.claim_number})
            return t
        return c.claim_number

    printed_numbers: dict[str, str] = {}

    detail_cols = ["Claim #", "Loss Date", "Claimant", "Description", "Status"]
    detail_w = [120, 70, 90, 210, 60]
    money_cols = ["Paid", "Reserve", "Recovered", "Incurred"]
    money_w = [80, 80, 80, 80]
    if not mess.header_policy:
        detail_cols = ["Policy #"] + detail_cols
        detail_w = [110] + detail_w

    def detail_cells(c: Claim, prev_status: str | None) -> list[str]:
        num = printed_numbers.setdefault(c.claim_number, shown_number(c))
        status = "" if (mess.ditto_blanks and prev_status == c.status) else c.status
        cells = [num, f"{c.loss_date:%m/%d/%Y}", c.claimant, c.description, status]
        return ([c.policy_number] + cells) if not mess.header_policy else cells

    def money_cells(c: Claim) -> list[str]:
        return [money(c.paid), money(c.reserve), money(c.recovered), money(c.paid + c.reserve - c.recovered)]

    by_policy: dict[str, list[Claim]] = {}
    for c in run.claims:
        by_policy.setdefault(c.policy_number, []).append(c)

    doc.text(f"Report includes all claims reported through {run.valuation_date:%m/%d/%Y}. Amounts in USD.")

    for cov in COVERAGES:
        pols = [p for p in run.policies if p.coverage == cov and p.policy_number in by_policy]
        if not pols:
            continue
        doc.heading(f"Line of Business: {COVERAGE_NAMES[cov]}", size=11)
        for p in pols:
            claims = sorted(by_policy[p.policy_number], key=lambda c: (c.status, c.loss_date))
            if mess.header_policy:
                doc.heading(f"Policy {p.policy_number}   Term {p.period_start:%m/%d/%Y} - {p.period_end:%m/%d/%Y}", size=9)
            else:
                doc.heading(f"Term {p.period_start:%m/%d/%Y} - {p.period_end:%m/%d/%Y}", size=9)
            cols, widths = (detail_cols, detail_w) if mess.split_tables else (detail_cols + money_cols, detail_w + money_w)
            doc.start_table(cols, widths, repeat_on_break=mess.page_break_repeat)
            prev = None
            for c in claims:
                pages_before = doc.page
                cells = detail_cells(c, prev) + ([] if mess.split_tables else money_cells(c))
                doc.row(cells)
                if doc.page != pages_before and mess.page_break_repeat:
                    traps["repeated_rows"] += 1
                prev = c.status
            if mess.subtotal_rows and not mess.split_tables:
                pad = [""] * (len(detail_cols) - 2)
                totals = [
                    sum(c.paid for c in claims),
                    sum(c.reserve for c in claims),
                    sum(c.recovered for c in claims),
                ]
                doc.row(
                    [f"{len(claims)} claims", ""] + pad[:-1] + ["Policy Total"]
                    + [money(totals[0]), money(totals[1]), money(totals[2]), money(totals[0] + totals[1] - totals[2])],
                    bold=False,
                )
                traps["subtotal_rows"] += 1
            doc.end_table()

    if mess.split_tables:
        doc.new_page()
        doc.heading("Financial Detail by Claim", size=11)
        doc.start_table(["Claim #"] + money_cols, [120] + money_w, repeat_on_break=mess.page_break_repeat)
        fin_order = sorted(run.claims, key=lambda c: c.claim_number)
        for c in fin_order:
            pages_before = doc.page
            doc.row([printed_numbers[c.claim_number]] + money_cells(c))
            if doc.page != pages_before and mess.page_break_repeat:
                traps["repeated_rows"] += 1
        doc.end_table()

    t = run.totals()
    doc.heading("Account Summary", size=11)
    doc.text(f"Total claims: {t['claim_count']}")
    doc.text(f"Total paid: {money(t['paid'])}    Total reserve: {money(t['reserve'])}    Total recovered: {money(t['recovered'])}")
    doc.text(f"Total incurred: {money(t['paid'] + t['reserve'] - t['recovered'])}")
    doc.save()
    return {"pages": doc.page, "messiness": mess.to_json(), "traps": traps}
