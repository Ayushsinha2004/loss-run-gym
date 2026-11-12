"""Command line: lrg generate | lrg score | lrg baseline | lrg bench"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import baseline
from .generate import generate
from .render import Messiness, render
from .score import score

LEVELS = {
    "clean": Messiness.clean(),
    "default": Messiness(),
    "hard": Messiness.hard(),
}


def cmd_generate(a) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for seed in range(a.seed, a.seed + a.count):
        run = generate(seed, n_claims=a.claims)
        stem = out / f"loss_run_{a.level}_{seed:03d}"
        manifest = render(run, f"{stem}.pdf", LEVELS[a.level], seed=seed)
        Path(f"{stem}.truth.json").write_text(json.dumps(run.to_json(), indent=2))
        Path(f"{stem}.manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"{stem}.pdf  claims={len(run.claims)} pages={manifest['pages']}")


def cmd_score(a) -> None:
    pred = json.loads(Path(a.pred).read_text())
    truth = json.loads(Path(a.truth).read_text())["claims"]
    print(json.dumps(score(pred if isinstance(pred, list) else pred["claims"], truth), indent=2))


def cmd_baseline(a) -> None:
    claims = baseline.extract(a.pdf)
    Path(a.out).write_text(json.dumps(claims, indent=2))
    print(f"wrote {len(claims)} rows to {a.out}")


def cmd_bench(a) -> None:
    import tempfile

    print(f"{'level':8} {'files':>5} {'row acc':>8} {'fields':>7} {'missing':>8} {'extra':>6} {'dupes':>6} {'pass':>5}")
    with tempfile.TemporaryDirectory() as tmp:
        for level, mess in LEVELS.items():
            rows = []
            for seed in range(a.seeds):
                run = generate(seed, n_claims=a.claims)
                pdf = f"{tmp}/{level}_{seed}.pdf"
                render(run, pdf, mess, seed=seed)
                rows.append(score(baseline.extract(pdf), run.to_json()["claims"]))
            n = len(rows)
            print(
                f"{level:8} {n:5d} {sum(r['row_count_accuracy'] for r in rows) / n:8.3f}"
                f" {sum(r['mean_field_accuracy'] for r in rows) / n:7.3f}"
                f" {sum(r['missing'] for r in rows):8d} {sum(r['extra'] for r in rows):6d}"
                f" {sum(r['duplicates'] for r in rows):6d} {sum(r['pass'] for r in rows):5d}"
            )


def main() -> None:
    p = argparse.ArgumentParser(prog="lrg", description="Synthetic loss runs with realistic traps, plus a scorer.")
    sub = p.add_subparsers(required=True)

    g = sub.add_parser("generate", help="write PDFs + ground truth")
    g.add_argument("--level", choices=list(LEVELS), default="default")
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("--count", type=int, default=1)
    g.add_argument("--claims", type=int, default=35)
    g.add_argument("--out", default="data")
    g.set_defaults(fn=cmd_generate)

    s = sub.add_parser("score", help="score an extractor's JSON against truth")
    s.add_argument("pred")
    s.add_argument("truth")
    s.set_defaults(fn=cmd_score)

    b = sub.add_parser("baseline", help="run the naive single-pass extractor")
    b.add_argument("pdf")
    b.add_argument("-o", "--out", default="pred.json")
    b.set_defaults(fn=cmd_baseline)

    m = sub.add_parser("bench", help="baseline across all messiness levels")
    m.add_argument("--seeds", type=int, default=10)
    m.add_argument("--claims", type=int, default=35)
    m.set_defaults(fn=cmd_bench)

    a = p.parse_args()
    a.fn(a)
