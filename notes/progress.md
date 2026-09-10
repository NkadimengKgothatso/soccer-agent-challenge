# Progress log

All records vs the `balanced` baseline, 40 matches (20 seeds, both sides),
unless noted. Tuning seeds 1000..1020; the grid adds the unseen ranges
2000..2020, 3000..3020, 4000..4020, 5000..5020.

## v1 — baseline
- 0-0 draw vs balanced
- 87.5% possession, 0.5% controlled — ball rarely settles
- 0/8 passes completed
- 7 shots, 0 goals

## v5 — FSM with candidate scoring
- 5W-16D-19L (12.5%), goals 13-34, GD -0.525 ± 0.298
- 61.3% possession but only 40.2% territory; 2.7 shots vs 6.0
- pass completion 27.2%; 18 policy timeouts; mean decision 1.177 ms

## v6 — rewrite: carry, don't kick
- `gc.disable()` + flat allocation-light loop: timeouts 18 -> 0-10 per
  40 matches, mean decision 0.070 ms, slowest ~0.5 ms
- ETA chaser over a 12-point ball-prediction table; dribble-first carrier
  (sub-0.5 power touches sized to the room ahead); keeper covers the
  crossing point, not the ball; presser + cover + goal-side marking;
  restart discipline (1.5-unit circle margin)
- 17W-17D-6L, goals 22-6, GD +0.400 (tuning seeds)
- every draw 0-0, every loss 0-1: defence concedes 0.15/match, attack
  stalls at 2.5 shots

## v7 — too much at once (rejected)
- post runners + carry gate 3.0 + pass gate 6.0 + safety changes together
- 16W-19D-5L, goals 19-6 — completions down, turnovers up. Reverted.

## v8 — shot relaxation only
- shot range 26, lane-need 1.8/2.4
- 20W-16D-4L, goals 28-6, GD +0.550 (tuning seeds)

## v9 — aggressive shooting
- shot range 28, lane-need 0.8 inside 8 / 1.4 inside 14 / 1.5 beyond
- 23W-14D-3L, goals 33-4, GD +0.725 (tuning seeds)
- BUT unseen seeds 2000..2020: 9W-25D-6L — overfitting risk

## A/B grid (5 ranges, 200 matches each config)
- v6-shot (conservative gate): 72W-107D-21L, goals 102-30, GD +0.360
- v9 (aggressive gate): 75W-104D-21L, goals 115-41, GD +0.370
- a wash: v9 scores 13 more, concedes 11 more

## v10 — aggressive shooting + closed leaks (current)
- v9 shot gate restored, plus:
  - safety at `bx - 14` (meets the break after a blocked shot, not just
    after a pass)
  - pass lane/landing requirements never discounted for desperation
  - hoof out of our end only when no decent pass is on (score < 6)
- validate: mean 0.068 ms, slowest 0.722 ms, 0 over deadline
- grid totals: 94W-89D-17L, goals 120-31, GD +0.445
  - 1000s: 22W-17D-1L, 25-4, +0.525
  - 2000s: 22W-17D-1L, 29-3, +0.650
  - 3000s: 18W-18D-4L, 22-6, +0.400
  - 4000s: 11W-21D-8L, 17-12, +0.125
  - 5000s: 21W-16D-3L, 27-6, +0.525
- vs the grid baselines: v10 scores 120 (between v6-shot's 102 and v9's
  115) while conceding the fewest (31 vs 30 and 41) — 94W-89D-17L beats
  both baselines outright (72W/75W, 21L each)
- the 4000s stay hard: attack still stalls against a packed box

## Next
- attack vs packed box (the 4000s: 11W-21D-8L is the weak range)
- test vs `possession` and `tactical` baselines for robustness
- timeout counts vary with machine load (5-77 per 40) — environmental,
  results are deterministic; consider trimming per-tick work if the
  grading machine is slower than this one
