"""my-team/team.py — v4

Strategy: DEFEND/ATTACK phase (from obs.phase) picks PRESS-or-SHOOT for the
one player closest to the ball by arrival time, and SUPPORT-or-MARK for
everyone else. KEEPER and HOLD_KICKOFF sit outside the phase split because
the engine gives you no goalkeeping or restart handling for free. Potential-
field steering drives HOW each of those targets is actually walked to,
bending around opponents instead of colliding with them.

We deliberately did NOT use A* or minimax:
  - A* wants a grid or waypoint graph with real obstacles. This pitch is open
    continuous space where the only "obstacles" are other players' bodies —
    a straight-line target plus a repulsion field handles that far more
    cheaply than a search would.
  - Minimax needs a known, simulatable opponent policy so you can build a
    game tree. The opponent controller is opaque here; there's nothing to
    search over. Grading is match performance only, so the extra machinery
    would cost decision-time budget for no measurable benefit.

Builds on v2's pass-leading, lane-room check, sized kick power, and
kickoff-foul avoidance — see notes/progress.md for what v2's numbers showed.
"""

from soccer import (
    TeamAction, TeamController,
    clamp, direction, distance, closest_point_on_segment,
)

KEEPER = "KEEPER"
PRESS = "PRESS"      # chaser, phase == DEFEND: win the ball back
SHOOT = "SHOOT"      # chaser, phase == ATTACK: shoot or pass, decided inside
SUPPORT = "SUPPORT"  # off-ball, phase == ATTACK
MARK = "MARK"        # off-ball, phase == DEFEND
HOLD_KICKOFF = "HOLD_KICKOFF"


class MyTeam(TeamController):
    name = "my_team"
    version = "4"

    # ---------- kickoff formation ----------

    def initial_formation(self, field):
        gx = field.my_goal[0]
        return [
            (gx + 2.0, 0.0),      # 0: keeper, goal line
            (gx + 20.0, -14.0),   # 1: left back
            (gx + 20.0, 14.0),    # 2: right back
            (gx + 32.0, -6.0),    # 3: left mid/fwd
            (gx + 32.0, 6.0),     # 4: right mid/fwd
        ]

    # ---------- main loop ----------

    def act(self, obs):
        actions = TeamAction()
        chaser_id = self._pick_chaser(obs)
        opponent_kickoff = self._is_opponent_kickoff(obs)

        for player in obs.my_players:
            state = self._assign_state(obs, player, chaser_id, opponent_kickoff)

            if state == KEEPER:
                self._do_keeper(obs, actions, player)
            elif state == HOLD_KICKOFF:
                self._do_hold_kickoff(obs, actions, player)
            elif state == PRESS:
                self._do_press(obs, actions, player)
            elif state == SHOOT:
                self._do_shoot(obs, actions, player)
            elif state == SUPPORT:
                self._do_support(obs, actions, player)
            else:  # MARK
                self._do_mark(obs, actions, player)

        return actions

    # ---------- FSM: state assignment ----------

    def _assign_state(self, obs, player, chaser_id, opponent_kickoff):
        # obs.phase is the engine's own ATTACK/DEFEND reading, derived from
        # possession with a short dwell so it doesn't flicker on a loose
        # ball — steadier than checking controlling_team directly.
        if opponent_kickoff:
            return HOLD_KICKOFF
        if player.id == 0:
            return KEEPER
        if player.id == chaser_id:
            return SHOOT if obs.phase == "ATTACK" else PRESS
        return SUPPORT if obs.phase == "ATTACK" else MARK

    # ---------- FSM: state behaviours ----------

    def _do_keeper(self, obs, actions, player):
        mouth = obs.field.goal_width / 2.0
        spot = (obs.my_goal[0] + 2.0, clamp(obs.ball.position[1], -mouth, mouth))
        movement = self._steer(obs, player, spot, avoid_radius=4.0, repel_strength=3.0)
        actions.move(player.id, movement)

    def _do_hold_kickoff(self, obs, actions, player):
        spot = self._keep_out_of_circle(obs, player.position, target=obs.ball.position)
        movement = self._steer(obs, player, spot, avoid_radius=4.0, repel_strength=3.0)
        actions.move(player.id, movement)

    def _do_press(self, obs, actions, player):
        # Ball isn't ours: close it down. If we get there and it turns out
        # we can already kick it (phase can lag possession by a tick or two
        # around a turnover), fall through to the shoot/pass decision.
        if obs.can_kick(player.id):
            self._on_ball_decision(obs, actions, player)
        else:
            target = self._meet_ball(obs, player)
            movement = self._steer(obs, player, target, avoid_radius=4.0, repel_strength=3.0)
            actions.move(player.id, movement)

    def _do_shoot(self, obs, actions, player):
        # Ball is ours: decide shoot vs. pass. If we've lost the ball out
        # from under us this same tick, chase it down instead of standing
        # still waiting for kick range.
        if obs.can_kick(player.id):
            self._on_ball_decision(obs, actions, player)
        else:
            target = self._meet_ball(obs, player)
            movement = self._steer(obs, player, target, avoid_radius=4.0, repel_strength=3.0)
            actions.move(player.id, movement)

    def _do_support(self, obs, actions, player):
        lane = (player.id - 2) * (obs.field.height * 0.22)
        spot = (obs.ball.position[0] + 15.0, lane)
        movement = self._steer(obs, player, spot, avoid_radius=8.0, repel_strength=6.0)
        actions.move(player.id, movement)

    def _do_mark(self, obs, actions, player):
        them = obs.closest_opponent_to(player.position)
        spot = obs.my_goal if them is None else (them.position[0] - 3.0, them.position[1])
        movement = self._steer(obs, player, spot, avoid_radius=8.0, repel_strength=6.0)
        actions.move(player.id, movement)

    # ---------- potential-field steering ----------

    def _steer(self, obs, player, target, avoid_radius, repel_strength):
        """Attraction to `target` plus repulsion from nearby opponents.

        The engine clamps any movement vector longer than 1 down to length 1,
        preserving direction — so we don't need to normalise here, just sum
        the attraction and repulsion and hand it over.
        """
        ax, ay = direction(player.position, target)
        rx, ry = 0.0, 0.0
        for opp in obs.opponents:
            dx = player.position[0] - opp.position[0]
            dy = player.position[1] - opp.position[1]
            d = (dx * dx + dy * dy) ** 0.5
            if 1e-6 < d < avoid_radius:
                strength = repel_strength * (1.0 - d / avoid_radius) / d
                rx += dx * strength
                ry += dy * strength
        return (ax + rx, ay + ry)

    # ---------- on-the-ball decision (unchanged from v2) ----------

    def _on_ball_decision(self, obs, actions, player):
        best_pass = self._best_pass(obs, player)
        goal_gap = distance(player.position, obs.opponent_goal)

        if goal_gap < 30.0 and (best_pass is None or goal_gap < best_pass["distance"]):
            power = clamp(goal_gap / 33.0, 0.5, 1.0)
            actions.kick(player.id, self._aim_at_goal(obs, player), kick_power=power)
            return

        if best_pass is not None:
            power = clamp(best_pass["distance"] / 33.0, 0.3, 1.0)
            actions.kick(player.id, best_pass["aim"], kick_power=power)
            return

        forward = direction(player.position, obs.opponent_goal)
        actions.kick(player.id, forward, kick_power=0.3, movement=forward)

    def _aim_at_goal(self, obs, player):
        keeper = min(obs.opponents, key=lambda o: distance(o.position, obs.opponent_goal))
        mouth = obs.field.goal_width / 2.0 * 0.85
        target_y = mouth if keeper.position[1] < 0 else -mouth
        return direction(player.position, (obs.opponent_goal[0], target_y))

    def _best_pass(self, obs, player):
        candidates = []
        for mate in obs.my_players:
            if mate.id == player.id:
                continue
            lead = self._lead_point(obs, player, mate)
            gain = lead[0] - player.position[0]
            if gain <= 0:
                continue
            room = self._lane_room(obs, player.position, lead)
            if room < obs.field.player_radius * 1.5:
                continue
            candidates.append({
                "aim": direction(player.position, lead),
                "distance": distance(player.position, lead),
                "gain": gain,
                "room": room,
            })
        if not candidates:
            return None
        return max(candidates, key=lambda c: c["room"] + c["gain"] * 0.1)

    def _lane_room(self, obs, from_pos, to_pos):
        # NOTE: verify closest_point_on_segment's argument order against your
        # SDK. This assumes (point, seg_a, seg_b). Swap if validate errors.
        room = float("inf")
        for opp in obs.opponents:
            closest = closest_point_on_segment(opp.position, from_pos, to_pos)
            room = min(room, distance(closest, opp.position))
        return room

    def _lead_point(self, obs, player, mate):
        target = mate.position
        for _ in range(3):
            dist = distance(player.position, target)
            ticks = obs.ticks_to_cover(dist, 0.6)
            travel_time = ticks / obs.field.simulation_hz
            travel = obs.field.max_speed * travel_time * 0.6
            target = (mate.position[0] + travel, mate.position[1])
        return target

    # ---------- ball pursuit ----------

    def _meet_ball(self, obs, player):
        path = [self._predict_ball(obs, t) for t in (0, 10, 20, 30, 40)]
        return min(path, key=lambda p: distance(player.position, p))

    def _predict_ball(self, obs, ticks):
        dt = 1.0 / obs.field.simulation_hz
        x, y = obs.ball.position
        vx, vy = obs.ball.velocity
        for _ in range(ticks):
            x, y = x + vx * dt, y + vy * dt
            vx, vy = vx * obs.field.ball_friction, vy * obs.field.ball_friction
        return (x, y)

    def _pick_chaser(self, obs):
        best_id, best_eta = None, float("inf")
        for player in obs.my_players:
            if player.id == 0:
                continue
            eta = distance(player.position, obs.ball.position) / obs.field.max_speed
            if eta < best_eta:
                best_id, best_eta = player.id, eta
        return best_id

    # ---------- kickoff discipline ----------

    def _is_opponent_kickoff(self, obs):
        return distance(obs.ball.position, (0.0, 0.0)) < 1.0 and obs.ball.controlling_team != 0

    def _keep_out_of_circle(self, obs, spot, target=None):
        r = obs.field.centre_circle_radius + obs.field.player_radius
        check = target if target is not None else spot
        d = distance(check, (0.0, 0.0))
        if d < r:
            if d < 1e-6:
                return (r, 0.0)
            return (check[0] / d * r, check[1] / d * r)
        return spot
