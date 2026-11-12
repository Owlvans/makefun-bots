# This script forecasts future Roblox chart placements across upcoming hours using a Monte Carlo approach over rank intervals.
# It adjusts simulated transitions by factoring in each game's short-term momentum and reserves unallocated probability space for novel entries.
# roblox-up-and-coming-forecast-01 entry v2 (Python 3.13, standard library only, no network).
#
# Method: empirical rank-diffusion Monte Carlo (as v1) with three additions, each calibrated
# on the input history itself:
#  - Momentum-conditioned transitions: every game carries a momentum score z (rank trend over
#    the last ~72h plus ~24h player-count growth, standardised). Transition rows are tilted
#    exponentially by z * (log-rank improvement), so risers keep rising and fallers keep
#    falling for a few steps; z decays over the simulated window.
#  - Tenure hazard: implemented as a fade mixture (a game's chart tenure, advancing with the
#    simulation clock, shifts an increasing share of its transitions toward worse buckets /
#    off-chart past ~4 days of tenure; the history stats support the direction — at a 24h
#    horizon, top-20 games with 4d+ tenure keep a top-10 place ~0.30 of the time vs
#    ~0.45-0.48 for fresher games). BUT the ablation on the practice window is unambiguous:
#    every strength tried (q_max 0.1-0.45) made the score slightly worse, so the shipped
#    configuration sets HAZARD_QMAX = 0.0 (code path kept). The hard created+28d removal
#    from v1 is kept for inputs that carry details.
#  - Newcomer reserve: named mass per place is capped at NAMED_CAP (0.82 instead of 0.97),
#    so games the history has never seen keep a realistic share of every place; the scorer
#    spreads that unnamed mass over the unnamed chart games.
# Backtest on the kit's practice window: see roblox-v2-report.md.

import json
import math
import os
import random
from datetime import datetime

BUCKETS = [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 8), (9, 12), (13, 20), (21, 35), (36, 60), (61, 110)]
OFF = len(BUCKETS)
LOG_C = [math.log((lo + hi) / 2.0) for lo, hi in BUCKETS] + [math.log(150.0)]  # bucket log-rank centres; OFF ~ 150

SIMS = 4000
STEPS = 12
SEED = 20261113

# --- tunable parameters (module constants; the tuning driver overrides them) ---
TILT = 2.0        # within-bucket continuous-draw tilt per unit momentum z
BLEND = 0.2       # blend weight of the recent empirical occupancy
GAMMA_M = 1.6    # momentum tilt strength on transition rows (per unit z, per log-rank)
Z_DECAY = 0.65    # per-step decay of the momentum score
W_RANK = 0.35     # momentum mix: rank-trend weight
W_PLAY = 0.65     # momentum mix: playing-growth weight
HAZARD_QMAX = 0.0  # max fade-mixture share for very old games
HAZARD_T0 = 4.0     # tenure (days) where the fade starts to bite
HAZARD_SCALE = 1.2  # tenure days over which the fade ramps up
FADE_DELTA = 0.9    # fade tilt strength (per log-rank of worsening)
NAMED_CAP = 0.82    # max total named probability per place (rest is newcomer reserve)
MIN_P = 0.0015      # drop named rows below this (they would lose to the unnamed share)


def bucket_of(rank):
    if rank is None:
        return OFF
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo <= rank <= hi:
            return i
    return OFF


def parse_t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def build_kernel(reads):
    counts = [[0.0] * (OFF + 1) for _ in range(OFF + 1)]
    series = []
    for r in reads:
        chart = r.get("up_and_coming") or []
        series.append((parse_t(r["at"]), {g["universe_id"]: g["rank"] for g in chart}))
    for (t0, m0), (t1, m1) in zip(series, series[1:]):
        lag_h = (t1 - t0) / 3600.0
        if lag_h < 1.5 or lag_h > 16:
            continue
        for u in set(m0) | set(m1):
            counts[bucket_of(m0.get(u))][bucket_of(m1.get(u))] += 1.0
    for b in range(OFF + 1):
        for j in range(OFF + 1):
            counts[b][j] += 0.35 if j == b else 0.06
    kernel = []
    for b in range(OFF + 1):
        tot = sum(counts[b])
        kernel.append([c / tot for c in counts[b]])
    return kernel


def game_series(reads):
    """uid -> list of (t, rank, playing) over the history, plus first-seen time."""
    series = {}
    first_seen = {}
    for r in reads:
        t = parse_t(r["at"])
        for g in (r.get("up_and_coming") or []):
            uid = g["universe_id"]
            series.setdefault(uid, []).append((t, g["rank"], g.get("playing") or 0))
            if uid not in first_seen:
                first_seen[uid] = t
    return series, first_seen


def momentum_map(reads):
    """Standardised momentum z per game: rank trend (last ~72h) + playing growth (~24h)."""
    series, _ = game_series(reads)
    t_last = parse_t(reads[-1]["at"])
    raw = {}
    for uid, pts in series.items():
        if pts[-1][0] != t_last:
            continue  # only games on the last chart get a live momentum
        # rank trend: least-squares slope of log(rank) vs days over the last 72h
        win = [(t, rk) for (t, rk, _pl) in pts if t_last - t <= 72 * 3600]
        slope = 0.0
        if len(win) >= 3:
            xs = [(t - t_last) / 86400.0 for t, _ in win]
            ys = [math.log(rk) for _, rk in win]
            mx = sum(xs) / len(xs)
            my = sum(ys) / len(ys)
            den = sum((x - mx) ** 2 for x in xs)
            if den > 1e-9:
                slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
        rank_score = -slope  # negative slope = rank number falling = climbing
        # playing growth: last vs the point closest to 24h earlier (same-ish time of day)
        play_score = 0.0
        p_last = pts[-1][2]
        ref = None
        for (t, _rk, pl) in pts:
            if abs((t_last - t) - 24 * 3600) <= 5 * 3600:
                if ref is None or abs((t_last - t) - 24 * 3600) < abs((t_last - ref[0]) - 24 * 3600):
                    ref = (t, pl)
        if ref is not None and p_last > 30 and ref[1] > 30:
            play_score = math.log(p_last / ref[1])
        raw[uid] = (rank_score, play_score)
    out = {}
    if raw:
        for idx in (0, 1):
            vals = [v[idx] for v in raw.values()]
            mu = sum(vals) / len(vals)
            sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
            for uid, v in raw.items():
                z = max(-2.5, min(2.5, (v[idx] - mu) / sd))
                o = out.setdefault(uid, [0.0, 0.0])
                o[idx] = z
        out = {uid: W_RANK * v[0] + W_PLAY * v[1] for uid, v in out.items()}
    return out


def tilted_rows(kernel, z, tenure_days):
    """Transition rows for one game at one sim step: momentum tilt + tenure fade mixture."""
    q = 0.0
    if tenure_days > HAZARD_T0:
        q = HAZARD_QMAX / (1.0 + math.exp(-(tenure_days - HAZARD_T0) / HAZARD_SCALE))
    rows = []
    for b in range(OFF + 1):
        base = kernel[b]
        c_b = LOG_C[b]
        mom = []
        fad = []
        for j in range(OFF + 1):
            imp = c_b - LOG_C[j]  # >0 when j is a better (lower) bucket
            mom.append(base[j] * math.exp(GAMMA_M * z * imp))
            fad.append(base[j] * math.exp(-FADE_DELTA * imp))
        sm = sum(mom)
        sf = sum(fad)
        row = [((1.0 - q) * (m / sm) + q * (f / sf)) if (sm > 0 and sf > 0) else base[j]
               for j, (m, f) in enumerate(zip(mom, fad))]
        rows.append(row)
    return rows


def make_forecast(reads, task):
    rng = random.Random(SEED)
    kernel = build_kernel(reads)
    last = reads[-1]
    chart = last.get("up_and_coming") or []
    details = last.get("details") or {}
    t_end = parse_t(task["history_until"])
    horizon_h = (parse_t(task["window"]["until"]) - t_end) / 3600.0
    step_h = horizon_h / STEPS
    cand = {}
    for r in reads[-5:]:
        for g in (r.get("up_and_coming") or []):
            cand[g["universe_id"]] = g["rank"]
    for g in chart:
        cand[g["universe_id"]] = g["rank"]
    ageout = {}
    for uid in cand:
        d = details.get(str(uid)) or {}
        if d.get("created"):
            ageout[uid] = parse_t(d["created"]) + 28 * 86400
    _series, first_seen = game_series(reads)
    tenure0 = {uid: max(0.0, (t_end - first_seen[uid]) / 86400.0) for uid in cand if uid in first_seen}
    mom = momentum_map(reads)
    state = {uid: bucket_of(rank) for uid, rank in cand.items()}
    uids = list(cand)
    # Tilted transition rows depend only on (game, step): precompute once for all sims.
    step_rows = []
    for st in range(STEPS):
        zfac = Z_DECAY ** st
        step_rows.append({
            uid: tilted_rows(kernel, mom.get(uid, 0.0) * zfac,
                             tenure0.get(uid, 0.0) + (st + 1) * step_h / 24.0)
            for uid in uids
        })
    occ = {}
    for _ in range(SIMS):
        cur = dict(state)
        for st in range(STEPS):
            t_now = t_end + (st + 1) * step_h * 3600
            zfac = Z_DECAY ** st
            draws = []
            for uid in uids:
                b = cur[uid]
                rows = step_rows[st][uid]
                if uid in ageout and t_now > ageout[uid]:
                    nb = OFF
                else:
                    row = rows[b]
                    x = rng.random()
                    acc = 0.0
                    nb = OFF
                    for j, p in enumerate(row):
                        acc += p
                        if x <= acc:
                            nb = j
                            break
                cur[uid] = nb
                if nb != OFF:
                    lo, hi = BUCKETS[nb]
                    v = lo + rng.random() * (hi - lo + 1) - TILT * mom.get(uid, 0.0) * zfac
                    draws.append((v, uid))
            draws.sort()
            for place, (_, uid) in enumerate(draws[:10], start=1):
                occ[(uid, place)] = occ.get((uid, place), 0) + 1
    total = SIMS * STEPS
    prob = {(uid, place): c / total for (uid, place), c in occ.items()}
    if BLEND > 0:
        emp = {}
        for r in reads[-3:]:
            for g in (r.get("up_and_coming") or [])[:14]:
                for dp, w in ((0, 0.7), (-1, 0.15), (1, 0.15)):
                    k = g["rank"] + dp
                    if 1 <= k <= 10:
                        emp[(g["universe_id"], k)] = emp.get((g["universe_id"], k), 0) + w / 3
        for k in set(prob) | set(emp):
            prob[k] = (1 - BLEND) * prob.get(k, 0.0) + BLEND * emp.get(k, 0.0)
    rows = []
    per_place = {}
    for (uid, place), p in prob.items():
        per_place.setdefault(place, []).append((uid, p))
    for place, lst in per_place.items():
        lst.sort(key=lambda t: -t[1])
        ssum = 0.0
        for uid, p in lst[:100]:
            p = min(p, NAMED_CAP - ssum)
            if p <= MIN_P:
                continue
            rows.append({"universe_id": uid, "place": place, "p": round(p, 6)})
            ssum += p
    exp = {}
    for (uid, place), p in prob.items():
        exp.setdefault(uid, []).append((place, p))
    cand10 = sorted(
        (sum(pl * p for pl, p in lst_) / sum(p for _, p in lst_) - sum(p for _, p in lst_) * 0.35, uid)
        for uid, lst_ in exp.items()
    )
    return {"probabilities": rows, "top10": [uid for _, uid in cand10[:10]]}


def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    with open(os.path.join(in_dir, "task.json")) as f:
        task = json.load(f)
    reads = []
    with open(os.path.join(in_dir, "history.ndjson")) as f:
        for line in f:
            line = line.strip()
            if line:
                reads.append(json.loads(line))
    fc = make_forecast(reads, task)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "forecast.json"), "w") as f:
        json.dump(fc, f, separators=(",", ":"))


# Execution loads historical chart records from the specified input directory and serializes the resulting forecast to the designated output path.
if __name__ == "__main__":
    main()
