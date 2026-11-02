# Plan

Status: Phase 0 is built in this repo. Phases 1 to 3 are not built and are described here only
so the order of work is clear. Everything is research; nothing is proven.

## Background

Combo-builder prices on Kalshi for correlated NHL player-prop combos (for example three
forwards from one line each scoring 2 or more points) sometimes look better than FanDuel's
same-game-parlay price for the same legs. Evidence so far is thin: 17 copies at $1 each went
3 wins and 14 losses for +$6.68. That is far too few to separate skill from luck, and it also
mixes two prices. The builder price shown on screen differs from the price the API (RFQ)
returns, so the executable price is worse than the one the copies were gated on.

So the test is not "Kalshi pays more than FanDuel". It is: executable yes price plus taker fee
versus our best estimate of the true probability.

## Phase 0: paper log (this PR)

- Log each priced combo: legs with thresholds, builder payout multiple, executable RFQ quote
  (yes price, no bid), FanDuel SGP price, any single-leg prices from other books, fee, notes,
  source timestamp, status.
- Settle from NHL box scores.
- Calibration report: hits against hits expected at the executable price, ROI after fees, luck
  probability, sample-size note.
- Exit criterion: 200 or more settled combos, logged without cherry-picking (log the ones that
  fail the gate too, as `ungateable`, so the sample is not only the good-looking ones).
- No trading code. `DRY_RUN = True`, `MAX_STAKE_USD = 1`.

## Phase 1: own joint-probability model

- Build a model of the joint chance that several named skaters each reach N points, from
  historical NHL game data (public API game logs). The key input is correlation: teammates on a
  line share goals, so independence will understate the joint probability. Estimate it from
  observed co-occurrence by line, ice time, and game context rather than assuming it.
- Get single-leg prices from The Odds API free tier to anchor each player's marginal
  probability. It has no SGP prices, so it cannot give us the combo price; it only gives legs.
- Request budget: the free tier is roughly 500 requests per month, which is about 16 a day.
  Confirm the current limit and how each endpoint is charged before building on it, since both
  change. Plan: only query games with a combo being considered, once shortly before puck drop,
  one region, one market, and cache every response on disk (gitignored) so nothing is fetched
  twice. Track a running count and stop before the cap.
- Validate against the Phase 0 log: does the model's probability beat executable price plus fee
  on out-of-sample combos?

## Phase 2: alerts only

- Compute model probability against executable price plus fee and send an alert when the gap
  clears a threshold set in Phase 1. A human decides. No orders.

## Phase 3: auto-buy at $1 behind caps

- Only if Phases 1 and 2 hold up. Buys of at most `MAX_STAKE_USD` (1), daily and weekly caps,
  a kill switch, `DRY_RUN` default on, and the key kept in the OS secret store or an
  environment variable on Tanner's machine only. See `docs/SECURITY.md`.

Phases 2 and 3 are not built here.
