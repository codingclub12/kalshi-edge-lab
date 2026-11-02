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
- Phase 0b adds a **read-only** Kalshi quote collector (`src/kalshi_edge_lab/kalshi_client.py`).
  It can read public market data, create a combo market, and create, read and delete an RFQ.
  It has **no code that accepts a quote, places an order, or touches a portfolio**. The client
  refuses any method and path outside a fixed allowlist, tests assert that, and a test scans
  `src/` for accept and order endpoints. `DRY_RUN` is `True` and `MAX_STAKE_USD` is `1` in
  `src/kalshi_edge_lab/safety.py`.

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

`settle` also covers `ungateable` combos, so you can compare them with the gated ones.

`settle` needs the network (the public NHL stats API). A combo is a win only if every leg's
player has at least the stated points. If any leg missed, it is a loss. If a player is not in
the box score and nothing else missed, the combo is left open for you to look at, because a
scratched player may mean a voided leg rather than a loss.

## Quote collector (Phase 0b)

Credentials come from the environment only (`KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY`; PEM or
bare base64 DER, RSA-PSS or Ed25519). They are never printed, logged or written to a file.

```
python scripts/run_collector.py LINEUPS.json /path/outside/repo/paper.sqlite
```

`LINEUPS.json` and the database must live outside the repo (the script refuses otherwise),
because this repo is public and data must not go in it. For each team it prices up to three
3-leg "2+ points" combos (top two forward lines, and 2 forwards plus 1 defenseman from PP1),
at most 40 RFQs per run, each sized to about $1 or less. The best executable Yes is
`1 - highest no_bid`; the multiple is `1 / Yes`; the fee is `0.07 x price x (1 - price)`. Every
RFQ is deleted after its quotes are read. Combos with an unclear or missing player, or no
defenseman on PP1, are logged `held` with a reason; failures are logged `error`. Quotes move
minute to minute, so a logged price is a snapshot, not a standing offer.

Export for a spreadsheet: `edge-lab --db PATH export-csv /path/outside/repo/combos.csv`.

## Settle workflow (after games end)

The paper log lives in a private Google Sheet ("Kalshi Paper Log", tab `Combos`), not in the repo.

1. In the sheet use File, Download, Comma Separated Values (current sheet) to get the Combos tab.
2. `edge-lab settle-csv ~/Downloads/combos.csv /path/outside/repo/settled.csv`
   This reads the legs and game from each `priced` row with a blank `result`, checks the NHL
   box scores (needs network), and writes the same CSV with `result` filled in as `win` or
   `loss`. A game that is not final, or a player missing from the box score, is left blank and
   the reason is printed.
3. Paste the `result` column of `settled.csv` back into the sheet.

If you keep the local SQLite file instead, `edge-lab --db PATH settle` does the same thing
directly. The sheet is read and written by hand (download and paste), not by code, so no
Google credentials are needed here.

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
