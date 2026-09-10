"""my-team/team.py — v11

v6 turned the balanced record from 5-16-19 into 17-17-6 by carrying the
ball instead of kicking it away and keeping the collector off; v8 and v9
kept that and loosened the shot gate — range out to 28, point-blank lanes
accepted with almost no room — which took the tuning seeds to 23-14-3.
Across five unseen seed ranges the extra goals were paid back in extra
concessions, from two leaks v10 closes while keeping the shooting:

*   the safety drops to bx - 14: deep enough to meet the break that follows
    a blocked shot, not just the one that follows a pass;
*   a lane or a landing spot is never discounted for desperation — the
    press feeds on exactly those balls, wherever they are played from;
*   the hoof out of our end only fires when no decent pass is on: a
    score-6 option beats a blind clearance.

v11 ran the 5-a-side formation book against the 200-match grid (the
3-1 defensive block was left out on principle): the 1-2-1 diamond kept
it tight but drew too much (78-110-12, 344 pts), the old 2-2 sat
mid-table (94-89-17, 371 pts), and the 1-3 high line won it — 95-91-14,
goals 130-24, +0.530, 376 pts. So v11 is the 1-3: one anchor back,
three outfielders pressed to halfway, so our kickoffs are taken a second
sooner and theirs is counterpressed at the line instead of at our box.
The packed-box stall on the hard seeds went with it (4000s: 11-21-8 to
17-21-2). Open-play roles are unchanged: they are ball-relative, not
slot-relative.

The rest — collector-off latency, dribble-first carrier, ETA chaser,
goal-side pressing and marking, crossing-point keeper, restart margins —
is v6 unchanged.
"""

import gc
import math

from soccer import TeamAction, TeamController, clamp

# One collector pause inside a decision is a 20 ms timeout and a free tick
# for the other side. Everything this file allocates per tick is acyclic and
# freed by refcounting, so the collector can stay off for a whole match.
gc.disable()

_HYP = math.hypot

# Ball prediction horizons, in ticks: fine through the first half-second
# (where most duels are settled), coarser out to the two seconds a pass
# spends rolling. Twelve points keep the ETA pass over both teams cheap.
_TICKS = (2, 4, 6, 8, 10, 14, 18, 22, 26, 30, 36, 42)


class MyTeam(TeamController):
    name = "my_team"
    version = "11"

    def __init__(self):
        self._attack_hold = 0

    def reset(self, seed):
        self._attack_hold = 0

    # ---------- kickoff formation ----------

    def initial_formation(self, field):
        gx = field.my_goal[0]
        return [
            (gx + 2.0, 0.0),      # 0: keeper, on the line
            (gx + 20.0, 0.0),     # 1: anchor back, the one deep body
            (gx + 38.0, -14.0),   # 2: high line, left
            (gx + 39.0, 0.0),     # 3: high line, on the spot's doorstep
            (gx + 38.0, 14.0),    # 4: high line, right
        ]

    # ---------- main loop ----------

    def act(self, obs):
        f = obs.field
        ball = obs.ball
        bx, by = ball.position
        bvx, bvy = ball.velocity
        my = obs.my_players
        opp_xy = [(o.position[0], o.position[1]) for o in obs.opponents]
        hyp = _HYP
        dt = 1.0 / f.simulation_hz
        vmax = f.max_speed
        gx_def = f.my_goal[0]
        gx_att = f.opponent_goal[0]
        half_w = f.width * 0.5 - 1.2
        half_h = f.height * 0.5 - 1.2
        mouth = f.goal_width * 0.5
        n = len(my)
        actions = TeamAction()

        ctrl = ball.controlling_player
        theirs_ctrl = ctrl is not None and ctrl >= n
        their_restart = (bx * bx + by * by < 1.0
                         and hyp(bvx, bvy) < 0.5
                         and ball.controlling_team != 0)

        # -- where the ball is going -------------------------------------
        if ctrl is None:
            fr = f.ball_friction
            preds = []
            x, y, vx, vy = bx, by, bvx, bvy
            last = 0
            for t in _TICKS:
                for _ in range(t - last):
                    x += vx * dt
                    y += vy * dt
                    vx *= fr
                    vy *= fr
                preds.append((t, clamp(x, -half_w, half_w),
                                 clamp(y, -half_h, half_h)))
                last = t
        else:
            # a held ball travels with its holder: straight line, no drag
            preds = [(t, clamp(bx + bvx * t * dt, -half_w, half_w),
                          clamp(by + bvy * t * dt, -half_h, half_h))
                     for t in _TICKS]

        def eta(px, py):
            # seconds until this player can first get a boot on the ball
            for (t, x_, y_) in preds:
                if hyp(x_ - px, y_ - py) <= vmax * t * dt * 0.9 + 1.5:
                    return t * dt
            return hyp(bx - px, by - py) / vmax + 0.15

        def meet(px, py):
            for (t, x_, y_) in preds:
                if hyp(x_ - px, y_ - py) <= vmax * t * dt * 0.9 + 1.5:
                    return (x_, y_)
            return (bx, by)

        def lane_room(ax, ay, tx, ty):
            # smallest distance from any opponent to the segment ax-ay -> tx-ty
            room = 15.0
            dx, dy = tx - ax, ty - ay
            l2 = dx * dx + dy * dy
            if l2 < 1e-9:
                return 0.0
            for (ox, oy) in opp_xy:
                t = ((ox - ax) * dx + (oy - ay) * dy) / l2
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                d_ = hyp(ox - (ax + dx * t), oy - (ay + dy * t))
                if d_ < room:
                    room = d_
            return room

        def run_dir(px, py, tx, ty, avoid, ease):
            # unit direction to the target, bent away from close opponents,
            # throttled down inside `ease` so positioning doesn't oscillate
            dx, dy = tx - px, ty - py
            l = hyp(dx, dy)
            if l < 1e-6:
                return (0.0, 0.0)
            ux, uy = dx / l, dy / l
            if avoid > 0.0:
                for (ox, oy) in opp_xy:
                    rx, ry = px - ox, py - oy
                    d_ = hyp(rx, ry)
                    if 0.3 < d_ < avoid:
                        w = (avoid - d_) / avoid * 0.8
                        ux += rx / d_ * w
                        uy += ry / d_ * w
                l2 = hyp(ux, uy)
                if l2 > 1e-6:
                    ux, uy = ux / l2, uy / l2
            th = 1.0 if l >= ease else l / ease
            return (ux * th, uy * th)

        # -- who chases, who holds ---------------------------------------
        chaser = None
        chaser_eta = 1e9
        for p in my:
            if p.id == 0:
                continue
            e = eta(p.position[0], p.position[1])
            if e < chaser_eta:
                chaser, chaser_eta = p, e
        their_eta = 1e9
        for (ox, oy) in opp_xy:
            e = eta(ox, oy)
            if e < their_eta:
                their_eta = e

        # our own reading of the phase, with a little dwell so contested
        # balls don't flicker roles every tick
        raw_attack = (ball.controlling_team == 0
                      or (ctrl is None and chaser_eta < their_eta + 0.05))
        hold = self._attack_hold + (1 if raw_attack else -1)
        self._attack_hold = -3 if hold < -3 else (3 if hold > 3 else hold)
        attack_mode = ball.controlling_team == 0 or self._attack_hold > 0

        # the keeper claims anything loose or theirs inside our box area,
        # otherwise the outfield chaser owns the ball
        keeper = my[0]
        kx, ky = keeper.position
        k_eta = eta(kx, ky)
        keeper_rush = (bx < gx_def + 12.0 and not their_restart
                       and (theirs_ctrl
                            or (ctrl is None and k_eta < chaser_eta + 0.1)))
        eff_chaser = None if keeper_rush else chaser

        rest = [p for p in my
                if p.id != 0 and (eff_chaser is None or p.id != eff_chaser.id)]

        # -- off-ball role tables ----------------------------------------
        support_plan = {}
        mark_map = {}
        cover_id = None
        cx8 = cy8 = 0.0

        if attack_mode:
            if rest:
                safety = min(rest, key=lambda p: p.position[0])
                others = sorted((p for p in rest if p.id != safety.id),
                                key=lambda p: p.position[0])
                taken_y = []
                for i, p in enumerate(others):
                    sx = clamp(bx + 9.0 + 10.0 * i, gx_def + 10.0, gx_att - 7.0)
                    base_y = clamp(by * 0.7, -10.0, 10.0)
                    best = None
                    for lane in (-14.0, -7.0, 0.0, 7.0, 14.0):
                        sy = clamp(base_y + lane, -half_h + 2.0, half_h - 2.0)
                        open_ = 12.0
                        for (ox, oy) in opp_xy:
                            d_ = hyp(ox - sx, oy - sy)
                            if d_ < open_:
                                open_ = d_
                        near = min((abs(sy - ty_) for ty_ in taken_y),
                                   default=12.0)
                        score = min(open_, 10.0) * 1.3 + min(near, 10.0) * 0.8
                        if best is None or score > best[0]:
                            best = (score, sy)
                    support_plan[p.id] = (sx, best[1])
                    taken_y.append(best[1])
                # one player sits between the ball and our goal against
                # the counter — deep enough to meet the break that follows a
                # blocked shot, not just the one that follows a pass
                support_plan[safety.id] = (
                    clamp(bx - 14.0, gx_def + 6.0, gx_att - 25.0),
                    clamp(by * 0.5, -8.0, 8.0),
                )
        else:
            if rest:
                dxg, dyg = gx_def - bx, -by
                lg = hyp(dxg, dyg) or 1.0
                cx8 = clamp(bx + dxg / lg * 8.0, gx_def + 2.5, half_w)
                cy8 = by + dyg / lg * 8.0
                cover_id = min(
                    rest, key=lambda p: hyp(p.position[0] - cx8,
                                            p.position[1] - cy8)).id
                markers = [p for p in rest if p.id != cover_id]
                threats = sorted(opp_xy,
                                 key=lambda o: (gx_def - o[0]) ** 2 + o[1] ** 2)
                for opp in threats:
                    if not markers:
                        break
                    mk = min(markers, key=lambda p: hyp(p.position[0] - opp[0],
                                                        p.position[1] - opp[1]))
                    markers.remove(mk)
                    # goalside of the marked man, inside the pitch, and no
                    # deeper than the ball line
                    ox_, oy_ = opp
                    dxg, dyg = gx_def - ox_, -oy_
                    lg = hyp(dxg, dyg) or 1.0
                    tx_ = clamp(ox_ + dxg / lg * 2.6,
                                gx_def + 3.0, min(bx + 14.0, 38.0))
                    mark_map[mk.id] = (tx_, clamp(oy_ + dyg / lg * 2.6,
                                                  -half_h + 1.5, half_h - 1.5))
                for p in markers:
                    side = -8.0 if p.id % 2 else 8.0
                    mark_map[p.id] = (clamp(bx - 8.0, gx_def + 6.0, 0.0), side)

        # -- the man on the ball -----------------------------------------

        def on_ball(p):
            pid = p.id
            px, py = p.position

            # 1. the shot: only with measured room to a post
            d_goal = hyp(gx_att - px, -py)
            if d_goal < 28.0:
                post = mouth - 1.2
                best_room, best_ty = -1.0, 0.0
                for ty_ in (post, -post):
                    room = lane_room(px, py, gx_att, ty_)
                    if room > best_room:
                        best_room, best_ty = room, ty_
                need = (0.8 if d_goal < 8.0
                        else 1.4 if d_goal < 14.0 else 1.5)
                if best_room >= need:
                    dx, dy = gx_att - px, best_ty - py
                    l = hyp(dx, dy) or 1.0
                    aim = (dx / l, dy / l)
                    power = clamp(0.55 + d_goal / 45.0, 0.65, 1.0)
                    actions.kick(pid, aim, power, movement=aim)
                    return

            # 2. how much room there is to carry into
            gdx, gdy = gx_att - px, -py
            gl = hyp(gdx, gdy) or 1.0
            gdx, gdy = gdx / gl, gdy / gl
            space = 14.0
            for (ox, oy) in opp_xy:
                rx, ry = ox - px, oy - py
                d_ = hyp(rx, ry)
                if 0.3 < d_ < space and (rx * gdx + ry * gdy) / d_ > 0.45:
                    space = d_
            press = 15.0
            for (ox, oy) in opp_xy:
                d_ = hyp(ox - px, oy - py)
                if d_ < press:
                    press = d_

            # 3. the pass table: led by the receiver's own velocity. a
            #    pressed man may pass backwards, but never through a lane
            #    he wouldn't accept in open play — those are the passes the
            #    press feeds on
            desperate = px < gx_def + 22.0 and press < 3.5
            max_opp_x = -100.0
            for (ox, oy) in opp_xy:
                if gx_att - 6.0 > ox > max_opp_x:
                    max_opp_x = ox
            best = None
            for mate in my:
                if mate.id == pid:
                    continue
                mvx, mvy = mate.velocity
                lx = clamp(mate.position[0] + mvx * 1.8, -half_w, half_w)
                ly = clamp(mate.position[1] + mvy * 1.8, -half_h, half_h)
                d_ = hyp(lx - px, ly - py)
                if d_ < 8.0 or d_ > 34.0:
                    continue
                room = lane_room(px, py, lx, ly)
                need = 2.0 + d_ * 0.07
                if room < need:
                    continue
                opp_land = 15.0
                for (ox, oy) in opp_xy:
                    d2_ = hyp(ox - lx, oy - ly)
                    if d2_ < opp_land:
                        opp_land = d2_
                if opp_land < 2.6:
                    continue
                gain = lx - px
                score = gain + room * 0.5 + min(opp_land, 8.0) * 0.4 - d_ * 0.1
                if lx > max_opp_x + 1.0 and gain > 8.0:
                    score += 6.0      # releases a runner behind their line
                if gain < 0.0 and not desperate:
                    score -= 6.0
                if best is None or score > best[0]:
                    best = (score, (lx - px) / d_, (ly - py) / d_, d_)

            def take_pass():
                _, ux, uy, d_ = best
                bv = bvx * ux + bvy * uy
                if bv < 0.0:
                    bv = 0.0
                power = clamp((d_ - bv * 0.8) / 33.0, 0.5, 0.9)
                actions.kick(pid, (ux, uy), power, movement=(ux, uy))

            if best is not None and (space < 4.5 or best[0] >= 16.0):
                take_pass()
                return

            # 4. the carry: a touch sized to the room ahead, bent around
            #    the nearest bodies, taken at full stride
            if space >= 4.5:
                ax_, ay_ = gdx, gdy
                for (ox, oy) in opp_xy:
                    rx, ry = px - ox, py - oy
                    d_ = hyp(rx, ry)
                    if 0.4 < d_ < 6.5:
                        w = (6.5 - d_) / 6.5 * 0.9
                        ax_ += rx / d_ * w
                        ay_ += ry / d_ * w
                l = hyp(ax_, ay_) or 1.0
                ux, uy = ax_ / l, ay_ / l
                power = clamp(0.08 + space * 0.027, 0.18, 0.42)
                actions.kick(pid, (ux, uy), power, movement=(ux, uy))
                return

            # 5. nothing on: deep and pressed, put it up the better wing
            if px < gx_def + 18.0 and press < 3.5 \
                    and (best is None or best[0] < 6.0):
                hoof = None
                for ty_ in (half_h - 6.0, -(half_h - 6.0)):
                    tx_ = clamp(px + 45.0, -half_w, half_w)
                    room = lane_room(px, py, tx_, ty_)
                    if hoof is None or room > hoof[0]:
                        hoof = (room, tx_, ty_)
                _, tx_, ty_ = hoof
                dx, dy = tx_ - px, ty_ - py
                l = hyp(dx, dy) or 1.0
                aim = (dx / l, dy / l)
                actions.kick(pid, aim, 0.85, movement=aim)
                return

            # 6. protect it: a soft touch away from the nearest body
            ax_, ay_ = gdx, gdy
            for (ox, oy) in opp_xy:
                rx, ry = px - ox, py - oy
                d_ = hyp(rx, ry)
                if 0.4 < d_ < 6.5:
                    w = (6.5 - d_) / 6.5 * 0.9
                    ax_ += rx / d_ * w
                    ay_ += ry / d_ * w
            l = hyp(ax_, ay_) or 1.0
            ux, uy = ax_ / l, ay_ / l
            actions.kick(pid, (ux, uy), 0.22, movement=(ux, uy))

        def keeper_clear(p):
            px, py = p.position
            hoof = None
            for ty_ in (half_h - 4.0, -(half_h - 4.0)):
                tx_ = clamp(gx_def + 58.0, -half_w, half_w)
                room = lane_room(px, py, tx_, ty_)
                if hoof is None or room > hoof[0]:
                    hoof = (room, tx_, ty_)
            _, tx_, ty_ = hoof
            dx, dy = tx_ - px, ty_ - py
            l = hyp(dx, dy) or 1.0
            aim = (dx / l, dy / l)
            actions.kick(p.id, aim, 0.8, movement=aim)

        # -- one action per player, every tick ---------------------------
        for p in my:
            pid = p.id
            px, py = p.position

            if pid == 0:
                if keeper_rush:
                    if obs.can_kick(pid):
                        keeper_clear(p)
                    else:
                        tx, ty = meet(kx, ky)
                        actions.move(pid, run_dir(px, py, tx, ty, 0.0, 1.0))
                else:
                    # cover where the ball would cross the line, not where
                    # it is now
                    tx = gx_def + 1.6
                    ty = by * 0.55
                    if bvx < -2.5 and bx > tx:
                        tc = (tx - bx) / bvx
                        if 0.0 < tc < 2.0:
                            ty = by + bvy * tc
                    ty = clamp(ty, -mouth + 1.0, mouth - 1.0)
                    actions.move(pid, run_dir(px, py, tx, ty, 0.0, 1.5))
                continue

            if their_restart:
                # hold outside their circle with a margin; nobody chases a
                # restart — the walk back costs four seconds
                d0 = hyp(px, py)
                need = f.centre_circle_radius + f.player_radius + 1.5
                if d0 < need:
                    if d0 < 1e-6:
                        tx, ty = need, 0.0
                    else:
                        tx, ty = px / d0 * need, py / d0 * need
                    actions.move(pid, run_dir(px, py, tx, ty, 0.0, 2.0))
                else:
                    actions.move(pid, (0.0, 0.0))
                continue

            if eff_chaser is not None and pid == eff_chaser.id:
                if obs.can_kick(pid):
                    on_ball(p)
                else:
                    tx, ty = meet(px, py)
                    if theirs_ctrl:
                        # take the controlled ball from the goal side
                        dxg, dyg = gx_def - tx, -ty
                        lg = hyp(dxg, dyg) or 1.0
                        tx += dxg / lg * 1.5
                        ty += dyg / lg * 1.5
                    actions.move(pid, run_dir(px, py, tx, ty, 0.0, 1.0))
                continue

            if attack_mode:
                spot = support_plan.get(pid)
                if spot is None:
                    spot = (clamp(bx - 8.0, gx_def + 8.0, gx_att - 20.0),
                            clamp(by * 0.6, -10.0, 10.0))
                actions.move(pid, run_dir(px, py, spot[0], spot[1], 3.0, 2.5))
            elif pid == cover_id:
                actions.move(pid, run_dir(px, py, cx8, cy8, 2.0, 2.0))
            else:
                spot = mark_map.get(pid)
                if spot is None:
                    spot = (clamp(bx - 10.0, gx_def + 6.0, 0.0),
                            clamp(by * 0.5, -8.0, 8.0))
                actions.move(pid, run_dir(px, py, spot[0], spot[1], 1.5, 2.0))

        return actions
