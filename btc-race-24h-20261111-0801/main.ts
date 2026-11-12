// btc-race entry: capitulation dip buyer on cbBTC, long only (Node 22, standard library only).
//
// What the dev window taught (and what generalises): on a 1-minute cbBTC pool, small wiggles around a
// mean do not pay for a round trip (fees + slippage + impact run 12-26 bps), and trend systems bleed.
// What pays is the capitulation: when the price has fallen 2% under its rolling 5-hour high, sellers
// are exhausted often enough that the snap-back covers costs many times over. So this bot waits flat,
// buys the capitulation at full size (one position, no averaging into a fall), and holds for the
// recovery: it sells at +0.9% over cost or after 600 minutes, whichever comes first, then may buy a
// later capitulation again after a 30-minute cooldown.
//
// Insurance for a quiet race window (the guardrails ask for at least one filled trade): if no trade
// has happened by bar 1200, the dip threshold relaxes to 1.2% at half size, and by bar 1380 to 0.7%
// at quarter size. On the dev window the capitulation comes early, so these never fire there.
//
// Determinism: pure arithmetic on the bars' integer closes; no clock, no environment, no random.

import { runBars, type Order } from './vendor/makefun-bars.ts';

const SYM = 'CBBTC';
const HIGH_WINDOW = 300;     // rolling high over 5 hours of closes
const WARMUP = 150;          // bars before the window means anything
const DIP = 0.020;           // capitulation: close at least 2.0% under the rolling high
const TAKE_PROFIT = 0.009;   // sell at +0.9% over the position's cost
const MAXHOLD = 600;         // minutes
const COOLDOWN = 30;         // minutes after an exit before the next entry
const LATE1_BAR = 1200;      // quiet-window fallbacks
const LATE1_DIP = 0.012;
const LATE2_BAR = 1380;
const LATE2_DIP = 0.007;
const MAX_SLIPPAGE_BPS = 60;
const MIN_NOTIONAL = 1_000_000n; // 1 USDC

const closes: number[] = [];
let heldSince = -1;
let lastExit = -1_000_000_000;
let barNo = -1;
let traded = false;

await runBars({
  onBatch(state, batch) {
    barNo += 1;
    const closeRaw = state.close(SYM);
    if (closeRaw === null) return [];
    const close = Number(closeRaw);
    closes.push(close);
    if (closes.length > HIGH_WINDOW) closes.shift();
    if (barNo < WARMUP) return [];

    let high = 0;
    for (const c of closes) if (c > high) high = c;
    const dd = 1 - close / high; // how far under the rolling high

    const held = state.positions.get(SYM);
    const orders: Order[] = [];

    if (held !== undefined && held.qty > 0n) {
      const value = state.value(SYM, held.qty);
      const pnl = held.cost_quote_units > 0n ? Number(value) / Number(held.cost_quote_units) - 1 : 0;
      if (pnl >= TAKE_PROFIT || barNo - heldSince >= MAXHOLD) {
        orders.push({ side: 'sell', symbol: SYM, qty: held.qty, max_slippage_bps: MAX_SLIPPAGE_BPS });
        heldSince = -1;
        lastExit = barNo;
      }
      return orders;
    }

    if (barNo - lastExit < COOLDOWN) return orders;

    let dip = DIP;
    let size = 1.0;
    if (!traded && barNo >= LATE2_BAR) { dip = LATE2_DIP; size = 0.25; }
    else if (!traded && barNo >= LATE1_BAR) { dip = LATE1_DIP; size = 0.5; }

    if (dd >= dip) {
      let spend = BigInt(Math.floor(Number(state.equity) * size));
      const room = state.weightRoom(SYM);
      if (room < spend) spend = room;
      if (state.cash < spend) spend = state.cash;
      if (spend >= MIN_NOTIONAL) {
        orders.push({ side: 'buy', symbol: SYM, notional_quote_units: spend, max_slippage_bps: MAX_SLIPPAGE_BPS });
        heldSince = barNo;
        traded = true;
      }
    }
    return orders;
  },
});
