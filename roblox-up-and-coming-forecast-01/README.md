# roblox-up-and-coming-forecast-01

Forecaster for the Roblox Up-and-Coming chart: a rank-diffusion Monte Carlo
whose transition kernel is tilted by each game's momentum (player-count
growth + rank trend), with a probability reserve kept for newcomers and
breakouts. Fully offline and deterministic, ~14 s runtime.

This is the submitted v2: practice log score **−30.498** (house baseline
−43.512), dev board **#12/499** — 0.098 log points off the #10 slot at last
check. The live forecast race runs 2026-11-13 → 2026-11-16.
