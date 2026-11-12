# tiny-chess-01

A chess engine that fits in **4,095 bytes** (the competition cap is 4,096):
PVS + LMR alpha-beta search with a transposition table and quiescence,
deterministic under a fixed 150,000-node cap. The payload is an
lzma/base85-packed Python program that unpacks and runs itself.

Status: submitted to make.fun tiny-chess-01; passed every validity check
(15/15 local, all server-side checks green); dev grading in progress,
deadline 2026-11-24.
