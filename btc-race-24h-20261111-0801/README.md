# btc-race-24h-20261111-0801 — "Capitulation dip buyer"

Long-only cbBTC strategy on 1-minute bars (Node, standard library only):
buys a full-size dip of ≥2.0% from the 300-bar rolling high, exits at +0.9%
or after 600 minutes, with quieter fallback entries late in the window.
Small wiggles don't pay the round-trip fees on this pool — this only trades
real capitulation.

Dev grade: **+$7.90 USDC** over 2 trades, max drawdown 0.99%. The live 24h
race runs 2026-11-11 19:16 WIB → 2026-11-12 19:16 WIB; the official grade
is the post-race replay.
