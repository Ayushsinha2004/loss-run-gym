import json
import re

import pdfplumber
import pytest

from loss_run_gym import Messiness, generate, render, score
from loss_run_gym.baseline import extract
from loss_run_gym.cli import LEVELS


def truth_claims(run):
    return run.to_json()["claims"]


def pdf_text(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def test_generation_is_deterministic():
    assert generate(3).to_json() == generate(3).to_json()
    assert generate(3).to_json() != generate(4).to_json()


def test_claim_numbers_unique_and_amounts_sane():
    run = generate(11, n_claims=60)
    nums = [c.claim_number for c in run.claims]
    assert len(nums) == len(set(nums))
    for c in run.claims:
        assert c.recovered <= c.paid
        assert c.status == "Closed" or c.reserve >= 0
        assert c.loss_date < run.valuation_date


@pytest.mark.parametrize("level", list(LEVELS))
def test_pdf_summary_states_true_totals(tmp_path, level):
    run = generate(5)
    path = tmp_path / "x.pdf"
    render(run, str(path), LEVELS[level], seed=5)
    text = pdf_text(path)
    t = run.totals()
    assert f"Total claims: {t['claim_count']}" in text
    assert f"Total paid: {t['paid']:,.2f}" in text


def test_clean_file_is_extracted_perfectly_by_baseline(tmp_path):
    run = generate(2)
    path = tmp_path / "clean.pdf"
    render(run, str(path), Messiness.clean(), seed=2)
    result = score(extract(str(path)), truth_claims(run))
    assert result["pass"] is True
    assert result["mean_field_accuracy"] == 1.0


def test_header_policy_hides_policy_number_from_rows(tmp_path):
    run = generate(7)
    path = tmp_path / "hp.pdf"
    render(run, str(path), Messiness(header_policy=True, subtotal_rows=False, ditto_blanks=False,
                                     split_tables=False, page_break_repeat=False, prefix_typos=False), seed=7)
    result = score(extract(str(path)), truth_claims(run))
    assert result["matched"] == len(run.claims)
    assert result["field_accuracy"]["policy_number"] == 0.0


def test_subtotal_rows_inflate_naive_count(tmp_path):
    run = generate(8)
    path = tmp_path / "st.pdf"
    manifest = render(run, str(path), Messiness(header_policy=False, subtotal_rows=True, ditto_blanks=False,
                                                split_tables=False, page_break_repeat=False, prefix_typos=False), seed=8)
    result = score(extract(str(path)), truth_claims(run))
    assert result["predicted_claims"] == len(run.claims) + manifest["traps"]["subtotal_rows"]
    assert result["extra"] == manifest["traps"]["subtotal_rows"]


def test_page_break_repeat_shows_up_as_duplicates(tmp_path):
    run = generate(9, n_claims=80)
    path = tmp_path / "pb.pdf"
    manifest = render(run, str(path), Messiness(header_policy=False, subtotal_rows=False, ditto_blanks=False,
                                                split_tables=False, page_break_repeat=True, prefix_typos=False), seed=9)
    assert manifest["traps"]["repeated_rows"] > 0
    result = score(extract(str(path)), truth_claims(run))
    assert result["duplicates"] == manifest["traps"]["repeated_rows"]
    assert result["totals"]["match"] is False


def test_prefix_typo_is_printed_and_truth_stays_correct(tmp_path):
    run = generate(10)
    path = tmp_path / "ty.pdf"
    manifest = render(run, str(path), Messiness(header_policy=False, subtotal_rows=False, ditto_blanks=False,
                                                split_tables=False, page_break_repeat=False, prefix_typos=True), seed=10)
    (typo,) = manifest["traps"]["typo_claims"]
    text = pdf_text(path)
    assert typo["printed"] in text and typo["correct"] not in text
    assert typo["correct"] in {c.claim_number for c in run.claims}
    result = score(extract(str(path)), truth_claims(run))
    assert result["missing"] == 0 and result["extra"] == 0  # paired by similarity, not lost
    assert result["field_accuracy"]["claim_number"] < 1.0


def test_split_tables_put_money_on_a_later_page(tmp_path):
    run = generate(12)
    path = tmp_path / "sp.pdf"
    render(run, str(path), Messiness.hard(), seed=12)
    with pdfplumber.open(path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    fin_page = next(i for i, t in enumerate(pages) if "Financial Detail by Claim" in t)
    assert fin_page > 0
    assert "Incurred" not in "\n".join(pages[:fin_page])


def test_scorer_normalises_formats():
    truth = truth_claims(generate(1, n_claims=3))
    pred = []
    for t in truth:
        p = dict(t)
        y, m, d = p["loss_date"].split("-")
        p["loss_date"] = f"{m}/{d}/{y}"
        p["paid"] = f"${t['paid']:,.2f}"
        p["claimant"] = "  " + t["claimant"].upper()
        p["claim_number"] = t["claim_number"].lower()
        pred.append(p)
    r = score(pred, truth)
    assert r["pass"] is True and r["mean_field_accuracy"] == 1.0


def test_totals_can_match_while_claims_are_missing():
    truth = truth_claims(generate(3, n_claims=6))  # seed 3 includes a zero-value claim
    zero = [t for t in truth if t["paid"] == t["reserve"] == t["recovered"] == 0]
    assert zero
    pred = [t for t in truth if t not in zero]
    r = score(pred, truth)
    assert r["totals"]["match"] is True
    assert r["missing"] == len(zero) and r["pass"] is False


def test_cli_generate_and_score(tmp_path, monkeypatch, capsys):
    import sys

    from loss_run_gym import cli

    monkeypatch.setattr(sys, "argv", ["lrg", "generate", "--level", "clean", "--out", str(tmp_path)])
    cli.main()
    pdf = next(tmp_path.glob("*.pdf"))
    truth = pdf.with_name(pdf.name.replace(".pdf", ".truth.json"))
    pred = tmp_path / "pred.json"
    monkeypatch.setattr(sys, "argv", ["lrg", "baseline", str(pdf), "-o", str(pred)])
    cli.main()
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", ["lrg", "score", str(pred), str(truth)])
    cli.main()
    out = json.loads(capsys.readouterr().out)
    assert out["pass"] is True
