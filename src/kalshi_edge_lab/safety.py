"""Safety constants. Phase 0 has no code that places orders of any kind."""

# Hard ceiling on any stake this tool will record, in US dollars.
MAX_STAKE_USD = 1

# Stays True. Nothing in this repo can trade, but later phases must keep checking it.
DRY_RUN = True
