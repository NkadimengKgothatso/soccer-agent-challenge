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

## Formation book A/B — v11 (current)

The 5-a-side formation page's shapes, run against the same 200-match grid
(the 3-1 defensive block was left out on purpose). Only
`initial_formation` changed; open-play roles are ball-relative, so the
kickoff shape is the whole difference. 3 points a win, 1 a draw:

| shape | record | goals | GD | pts/200 |
|---|---|---|---|---|
| 2-2 (v10) | 94W-89D-17L | 120-31 | +0.445 | 371 |
| 1-2-1 diamond (v12) | 78W-110D-12L | 127-25 | +0.510 | 344 |
| **1-3 high line (v11/v13)** | **95W-91D-14L** | **130-24** | **+0.530** | **376** |

- 1-3: keeper, anchor back at x=-30, three pressed to x=-11/-12 — our
  kickoffs are taken a second sooner, theirs is counterpressed at
  halfway
- both aggressive shapes cut concessions (31 -> 24) and fixed the hard
  4000s range (11-21-8 -> 17-21-2): the packed-box stall was letting
  them settle deep, and the high line denies the settling
- diamond keeps losses lowest (12) but draws too much to win points
- v11 = the 1-3; validate clean (mean 0.062 ms, 0 over deadline)
- run grids with `powershell -File notes/grid.ps1 <label>`

## v12/v13 — shooting: the one-on-one rule and the range (current: v13)

- v12: a carrier past every outfield opponent, with only their keeper
  ahead near his line (x > gx_att - 9), shoots the far post from the
  keeper's shade immediately — no lane check, no carry. Halved the
  losses: 100W-93D-7L, 149-23, +0.630, 393 pts
- v13: measured shot range 28 -> 31. 104W-87D-9L, 160-25, +0.675,
  399 pts. Range 34 was a wash (163-25 but 397 pts) — 31 is the spot
- per-range (v13): 1000s 20-18-2 / 29-4, 2000s 23-13-4 / 36-10,
  3000s 20-20-0 / 34-4, 4000s 18-22-0 / 29-1, 5000s 23-14-3 / 32-6
- validate: mean 0.074 ms, slowest 0.651 ms, 0 over deadline

- v13 Linux fix: the bundled Linux engine (built 2026-08-14) has no
  field.simulation_hz or field.ball_friction, so v13 raised every tick
  there and drew every match 0-0. Both now read through getattr with the
  config defaults (20, 0.985). No behaviour change on Windows.
- Linux grid vs balanced (v13 + fix): 1000s 22-12-6 / 32-6, 2000s
  12-25-3 / 18-4, 3000s 23-15-2 / 38-5, 4000s 21-19-0 / 33-2, 5000s
  26-13-1 / 36-4; total 104W-84D-12L, 157-21. Close to the Windows grid
  but not identical, so the two engine builds differ slightly in physics
- public seeds 1001..1005 on Linux: balanced 5-2-1 (8-1), possession
  6-2-0 (15-1), tactical 4-1-3 (7-7); validate slowest 0.515 ms

## v14 — shots go where they are aimed (cloud, Linux engine)

- harness: `python3 launch.py tournament` over seeds 3000..3299 (600
  matches per opponent, both ends); held-out check on 7000..7299
- v13 baseline: balanced 316-253-31, possession 488-103-9, tactical
  271-237-92 — 3818 pts
- finding: a kick *adds* its impulse to the ball's current velocity. A
  ball rolling across the shooter (arriving pass, a touch running wide)
  went where the sum pointed, so about half of v13's shots went wide
- v14: shots point the boot so ball velocity + impulse lands on the
  target (solve |s*u - v| = impulse*power for s, kick along s*u - v)
- v14: balanced 408-177-15 (759-53), possession 541-56-3, tactical
  307-193-100 (574-225) — 4194 pts (+376); held-out 7000s 3812 -> 4169
- tried and dropped: compensating passes + clearances too (4020), and
  every touch (3906) — their power sizing already counts the ball's speed

## v15 — shot range 31 -> 55

- range sweep on v14 (seeds 3000..3299, bal+poss+tact): 26 -> 4034,
  31 -> 4194, 36 -> 4440, 40 -> 4560, 45 -> 4595, 55 -> 4926 pts. The
  lane test still gates every shot
- 55 covers the kickoff: a full-power shot from the spot beats
  tactical's keeper, which doesn't shift across (tactical 578-21-1)
- v15: balanced 436-137-27, possession 564-34-2, tactical 578-21-1 —
  4926 pts; held-out 7000s: 4954 (v14 4169)
- also better vs man_marking (135/130W of 200 vs v13's 112),
  structured_attack (171W vs 132), ball_chaser — not just tactical
- a margin-gated long shot (only when nobody can reach the path) never
  fired vs tactical and gained less elsewhere (4208-4275): too strict

## v16 — shoot through tighter lanes (need 0.3) (current)

- lane room a shot needs, on v15 (seeds 3000..3299, bal+poss+tact):
  1.5 (v15) 4926, +0.04/unit past 25 4870, 1.2 5035, 0.9 5028,
  1.0 flat 5018, 0.6 5073, 0.3 5094, 0.0 5096
- v16 = 0.3: balanced 503-89-8 (1159-65), possession 569-27-4,
  tactical 581-19-0, man_marking 487-104-9, structured_attack 545-45-6
- held-out 7000s (bal, man_marking, structured_attack): v15 4456 ->
  v16 4786
- also tried on v15: shot power always 1.0 (+35), aim mouth-2.0 instead
  of mouth-1.2 (+48) — inside noise (~+/-50), not taken

## Tried on v16 and not taken (seeds 3000..3199, 5 opponents)

- pool: balanced, man_marking, structured_attack, tactical and the old
  v13 (a stand-in for a student team whose keeper tracks the crossing
  point). v16 = 5125 pts; v16 vs v13 goes 189-138-73
- keeper: crossing-point lookahead 2 -> 4.5 s, ty = by*0.4, keeper
  deeper at gx+1.0 — better against long shots, worse vs balanced;
  noise-level overall
- passes velocity-compensated with power re-sized to the wanted speed:
  /33 5053, /28 5000
- pass trigger 16 -> 12 (5104) / 20 (4997); support line +3 (4975)
- dropping the v12 one-on-one rule: 5181 here, but 7617 vs 7627 on the
  held-out 7000s — no real difference, kept
- validate (tactical, 2400 ticks): mean 0.064 ms, slowest 1.97 ms, 0 over
- check: passes; team.toml still has the example name and student number

## v17 — every shot at full power (current)

- the real ladder: Division 1 starts near 4075 pts over 1660 matches
  (~78% wins); the tactical reference sits at 1059, so the baselines are
  well below the class. New test pool: v16 itself and the old v13 (its
  keeper tracks the crossing point)
- on v16 vs the pool (seeds 3000..3299): power 1.0 1825 -> 1976; aim at
  the post away from their deepest player 1880; aim mouth-2.0 1846
- held-out 7000s (v16, v13, balanced, tactical): 5255 -> 5379; v13
  281-222-97 -> 324-209-67; far-post + power 5236 (not taken)
- keeper crossing point gated on whether the ball reaches the line,
  instead of within 2 s: 3410 / 3461 vs 3455 — noise, not taken
- goals v16 concedes to itself come from 10-30 units out (135 of 136),
  not long shots or kickoffs

## Tried on v17 and not taken (seeds 3000..3199)

- v17 vs every baseline, 400 matches each: do_nothing 100%, random_legal
  100%, ball_chaser 98.8%, tactical 97.2%, possession 97.0%,
  structured_attack 92.0%, balanced 85.5%, man_marking 82.2% — the gaps
  are 0-0 / 1-0 draws; vs man_marking ~60% of shots are blocked
- pushing the safety man up when not winning (4 variants): no gain
- 5 aim points instead of 2: +4 over 5 opponents (noise)
- coordinate search over 27 constants: 3986 -> 4186 on its own seeds,
  but held-out 7000s only 7545 -> 7597 (man_marking and v13 slightly
  worse) — overfitting, not shipped
- kickoff: pass (ko1) or carry (ko2) instead of the shot — tactical
  97% -> 80%; the shot stays

## v18 candidate: close-control dribbling (candidates/v18-dribble, not submitted)

The ladder (#90, division 5, 1989 pts) showed v17 at 3% ball control and 9 dribbles a match against the top teams' 34% and 148, losing 0-10 to each of the top ten. A dribble touch that sets the ball's velocity to the carrier's stride (instead of adding a 0.18-0.42 touch on top) took control to 20-40% and dribbles to 60-150. What it changed locally:

| variant (seeds 3000-3149, both ends) | v17 | v13 | balanced | dribbler s25 | total |
| --- | --- | --- | --- | --- | --- |
| v17 | 424 | 556 | 806 | 382 | |
| dribble, range 25 | 448 | 574 | 741 | 423 | |
| + passes only when pressed | 406 | 610 | 759 | 394 | |
| + shot only if nobody can reach its path (sm25) | 432 | 617 | 805 | 421 | |

Held-out 7000-7099: v17 gets 267 from v17 and 300 from sm25; sm25 gets 260 from v17 and only 340 from tactical (no kickoff shot). With the kickoff shot back (the candidate): v17 251, sm25 290, tactical 588. So it plays like the top teams but is not stronger than v17 against anything we have locally.

Tried and level within noise: dribble speed 6/7/8, lead 1.2/1.6, gain 1/2/3, protect speed 2/4, range 20/25/28/32/40, shielding the ball from the nearest body (weights 1.5, 3.0), reach-checked shots out to 40.

## Next
- test vs `possession` and `tactical` baselines for robustness
- timeout counts vary with machine load — environmental, results are
  deterministic; consider trimming per-tick work if the grading machine
  is slower than this one
