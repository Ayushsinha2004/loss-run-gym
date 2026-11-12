# loss-run-gym

Synthetic insurance loss runs with the traps that break extractors, plus a scorer.

Insurance has no public labelled set of loss runs. This tool makes one you can regenerate from a seed. Each PDF comes with exact ground truth, and each messiness knob reproduces a failure that real carrier reports cause:

| Knob | What the document does | What a naive extractor gets wrong |
|---|---|---|
| `header_policy` | Policy number printed once in a section header | Every claim loses its policy number |
| `subtotal_rows` | "Policy Total" rows laid out like claim rows | Totals counted as claims |
| `ditto_blanks` | Blank Status means "same as the row above" | Status read as missing |
| `split_tables` | Claim details and money in two tables pages apart | Rows with no money, or money with no claim |
| `page_break_repeat` | Last row repeated at the top of the next page | Duplicate claims, inflated totals |
| `prefix_typos` | One claim number printed with a wrong carrier prefix | Claim looks missing unless paired by context |

Zero-value claims (closed without payment) are always present. They are real claims, so a run can match every financial total while still missing them.

## Run it

```bash
uv sync
uv run lrg generate --level hard --seed 42 --out data     # PDF + truth.json + manifest.json
uv run lrg baseline data/loss_run_hard_042.pdf -o pred.json
uv run lrg score pred.json data/loss_run_hard_042.truth.json
uv run lrg bench --seeds 8                                # baseline across all levels
uv run pytest -q
```

To test your own extractor, write its output as a JSON list of claims with these keys and run `lrg score`:
`claim_number, policy_number, coverage, loss_date, claimant, description, status, paid, reserve, recovered`

## How scoring works

- Claims are paired by normalised claim number first. What is left is paired by optimal assignment (Hungarian) over coverage, loss date, claimant, description and claim-number similarity. A typo then counts as a wrong field, not a missing claim plus an extra one.
- Dates, money and case are normalised before comparison, so `07/04/2023` equals `2023-07-04` and `$1,250.00` equals `1250`.
- Row count, matched, missing, extra and duplicates are reported next to the totals. A file passes only if all of them are right. Totals alone are never treated as success.

## Baseline result

The included baseline is a deliberately naive single pass: any text line with four money amounts is a claim.

```
level    files  row acc  fields  missing  extra  dupes  pass
clean        8    1.000   1.000        0      0      0     8
default      8    0.732   0.834        0     75      3     0
hard         8    0.971   0.433        8     16      8     0
```

On clean files it is perfect, which checks the scorer end to end. On the hard level its row count looks fine (0.971) while most fields are wrong (0.433). That is why row count and field accuracy have to be read together.

## What is not here yet

- An agentic extractor with a validate-totals tool, scored against the same files.
- More layouts per carrier, scanned-image PDFs, and multi-insured reports.
- A difficulty dial for how much each trap fires, so the distribution of imperfection can be tuned against real files.

All carriers, insureds, people and numbers are invented.

MIT licence.
