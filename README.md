# kalshi-edge-lab

A small research log for one question: when a Kalshi combo-builder price on a correlated NHL
player-prop combo looks better than FanDuel's same-game-parlay price, is there a repeatable
edge once you use the price you could actually execute?

**This is research, not advice. Results are unproven.** Nothing here says any bet is a good
idea, and the early evidence is thin (17 $1 copies, 3 wins and 14 losses, +$6.68, which is
well within what luck produces). Do not read this repo as a recommendation to wager.

## Phase 0 only

This repo currently does paper logging and nothing else.

- It records priced combos in a local SQLite file.
- It settles them from the free public NHL stats API once games finish.
- It prints a calibration report.
- It has **no Kalshi client and no code that places orders**. `DRY_RUN` is `True` and
  `MAX_STAKE_USD` is `1` in `src/kalshi_edge_lab/safety.py`, and a test checks that nothing in
  `src/` imports or defines an order-placement function.

The edge is judged on the executable (RFQ) price plus the taker fee, compared with an estimated
true probability. It is not judged on a ratio to FanDuel, because the builder price shown on
screen and the price the API quotes can differ, and only the second one is what you would pay.

See `docs/PLAN.md` for the phases and `docs/SECURITY.md` for how keys are handled (short
version: none ever go in this repo).

## Setup

Python 3.11 or newer.

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml   # optional; defaults work
```

The database lives at `data/edge_lab.sqlite` by default. `data/` is gitignored, as are all
SQLite, CSV, key, and env files.

## Use

Log a priced combo. Prices are dollars per $1 contract; the builder payout is the total return
divided by stake at a $20 stake.

```
edge-lab log --date 2026-11-01 --game TOR@BOS --team TOR \
  --leg "Auston Matthews:2" --leg "Mitch Marner:2" --leg "John Tavares:2" \
  --builder-payout 32.5 --rfq-yes 0.034 --rfq-no-bid 0.95 \
  --fanduel-american +3500 \
  --other-book "dk:Auston Matthews:2:+250" \
  --notes "line 1, home back-to-back"
```

`Player Name:2` means 2 or more points. The taker fee per contract is computed as
`0.07 x price x (1 - price)` and stored with the row.

Other commands:

```
edge-lab list                       # everything logged, with status and result
edge-lab status 12 expired          # priced | bought | expired | ungateable
edge-lab record-buy --combo 12 --stake 1 --fill-price 0.04 --contracts 25
edge-lab settle                     # settle every due combo from NHL box scores
edge-lab settle --combo 12
edge-lab report                     # calibration report
```

`record-buy` only writes down a purchase you made yourself somewhere else. It refuses stakes
above `MAX_STAKE_USD`.

`settle` needs the network (the public NHL stats API). A combo is a win only if every leg's
player has at least the stated points. If any leg missed, it is a loss. If a player is not in
the box score and nothing else missed, the combo is left open for you to look at, because a
scratched player may mean a voided leg rather than a loss.

## The report

For settled combos that have an executable price, the report shows actual hits against the hits
expected at that price, ROI per contract at price plus fee, and how likely a result that far
from the price would be by luck alone (exact Poisson-binomial, with the plain Poisson
approximation beside it). That luck figure is not the chance an edge exists. The report also
states the sample size against a target of 200 or more settled combos; below that, treat every
number as noise.

## Development

```
ruff check .
ruff format --check .
pytest
python scripts/check_repo_hygiene.py
```

Tests are offline. NHL responses come from fixtures in `tests/fixtures/`.

A pre-commit config is included (`pre-commit install` if you use pre-commit). It runs the
hygiene check, which blocks key-shaped strings and anything under `data/` or `logs/`, plus ruff.
CI runs the same checks in one workflow.

## License

MIT. See `LICENSE`.
