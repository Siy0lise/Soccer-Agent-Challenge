"""Your team. Edit this file.

Everything you write goes in here. A submission is one file of code — extra
.py files next to it are not importable when the server loads your team, so
they are rejected rather than silently ignored.

This is a working team, so you can play it right now and see numbers come back:

    START.cmd play my-team --against balanced      (Windows)
    ./start.sh play my-team --against balanced     (macOS and Linux)

It is about as simple as a team can be while still playing football. Every
player asks two questions and does one of four things:

    is the ball ours?
        am I the closest of us to it?   ->  shoot at their goal
        otherwise                       ->  push up towards their goal
    otherwise
        am I the closest of us to it?   ->  go and get it
        otherwise                       ->  drop back towards our goal

It will lose to the reference opponents, which is the point — it is something
to improve, not something to hand in as it stands. Things wrong with it, in
roughly the order they cost you goals: nobody keeps goal, the four players who
are not chasing all run to the same place, nobody ever passes, and every shot
is struck at full power from wherever the player is standing.

This file is the whole submission: when you are done, upload it to Moodle. There
is nothing else to fill in — Moodle already knows who you are.

You write one method, `act`, and it is called on every tick of the match —
whether the ball is yours or theirs. Deciding which of those it is, and what
your players should be doing about it, is the assignment. There is no engine
call that will do it for you: an observation reports where everybody is and how
the ball behaves, and the football is yours to write.

You are always given the same pitch whichever side you are really playing:
your goal at the left, theirs at the right, forward is +x, your players are
ids 0..n-1. Write one team, not one per side.

The full API is in the student guide that came with this download.
"""

from soccer import PlayerAction, TeamAction, TeamController, direction


class MyTeam(TeamController):
    # What this team calls itself in your own results and replays. Name it
    # whatever you like; the leaderboard uses the identity Moodle has for you.
    name = "SYOZAEATS"
    version = "1"
    restart_wait_until = -1
    pass_receiver_id = None
    pass_target = None
    pass_follow_until = -1
    quick_shot_player_id = None
    quick_shot_until = -1
    attacking_lane_phase = 0
    had_possession_last_tick = False
    second_ball_player_id = None
    second_ball_until = -1

    def reset(self, seed):
        self.restart_wait_until = -1
        self.pass_receiver_id = None
        self.pass_target = None
        self.pass_follow_until = -1
        self.quick_shot_player_id = None
        self.quick_shot_until = -1
        self.attacking_lane_phase = 0
        self.had_possession_last_tick = False
        self.second_ball_player_id = None
        self.second_ball_until = -1

    def initial_formation(self, field):
        """Where your team stands at every kickoff. Optional — delete for the default.

        One (x, y) per player in slot order, slot 0 the goalkeeper. It has to be
        inside the pitch, on your own half and outside the centre circle; a spot
        that is not gets moved to the nearest one that is, rather than refused.
        """
        keeper_x = field.my_goal[0] + field.player_radius * 2
        # Just outside the centre circle: as close to the ball as the rules
        # allow, which is where the kickoff is won or lost.
        forward_x = -field.centre_circle_radius - 1.0
        return [
            (keeper_x, 0.0),        # keeper
            (-20.0, -12.0),         # left back
            (-20.0, 12.0),          # right back
            (forward_x, -6.0),      # left forward
            (forward_x, 6.0),       # right forward
        ]

    @staticmethod
    def distance_squared(first_position, second_position):
        """Squared distance, avoiding a square root when comparing players."""
        dx = first_position[0] - second_position[0]
        dy = first_position[1] - second_position[1]
        return dx * dx + dy * dy

    def lane_clearance_squared(self, start, target, opponents):
        """Return the smallest squared distance from an opponent to a lane."""
        lane_dx = target[0] - start[0]
        lane_dy = target[1] - start[1]
        lane_length_squared = lane_dx * lane_dx + lane_dy * lane_dy

        if lane_length_squared == 0.0:
            return 0.0

        minimum_clearance_squared = float("inf")

        for opponent in opponents:
            opponent_dx = opponent.position[0] - start[0]
            opponent_dy = opponent.position[1] - start[1]
            progress = (
                opponent_dx * lane_dx + opponent_dy * lane_dy
            ) / lane_length_squared
            progress = max(0.0, min(progress, 1.0))
            closest_point = (
                start[0] + progress * lane_dx,
                start[1] + progress * lane_dy,
            )
            minimum_clearance_squared = min(
                minimum_clearance_squared,
                self.distance_squared(opponent.position, closest_point),
            )

        return minimum_clearance_squared

    def defensive_challenge_action(self, obs, player):
        """Challenge for the ball without clearing it away unnecessarily."""
        emergency_tackle = (
            obs.ball.position[0]
            < obs.field.my_goal[0] + 25.0
        )

        if emergency_tackle:
            # Preserve the strong wide clearance near our goal.
            tackle_target_y = (
                18.0 if obs.ball.position[1] >= 0.0 else -18.0
            )
            tackle_target = (
                min(
                    obs.ball.position[0] + 25.0,
                    obs.opponent_goal[0] - 5.0,
                ),
                tackle_target_y,
            )
            tackle_power = 1.0
        else:
            # Farther upfield, greedily choose a safe short forward lane while
            # preferring useful central space over an empty touchline.
            tackle_target_x = min(
                obs.ball.position[0] + 8.0,
                obs.opponent_goal[0] - 2.0,
            )
            maximum_target_y = obs.field.height / 2 - 3.0
            tackle_targets = [
                (
                    tackle_target_x,
                    max(
                        -maximum_target_y,
                        min(
                            obs.ball.position[1] + lane_offset,
                            maximum_target_y,
                        ),
                    ),
                )
                for lane_offset in (-6.0, 0.0, 6.0)
            ]
            tackle_target = max(
                tackle_targets,
                key=lambda target: (
                    min(
                        self.lane_clearance_squared(
                            obs.ball.position,
                            target,
                            obs.opponents,
                        ),
                        64.0,
                    )
                    - 1.5 * abs(target[1])
                ),
            )
            tackle_power = 0.3

        return PlayerAction(
            movement=direction(
                player.position,
                obs.ball.position,
            ),
            kick_direction=direction(
                obs.ball.position,
                tackle_target,
            ),
            kick_power=tackle_power,
        )

    def act(self, obs):
        """Called on every tick. Return one action per player.

        The first thing this does is work out whose ball it is, because almost
        everything else follows from that. `obs.ball.controlling_team == 0` is
        the engine's own reading of possession, and it persists while the ball
        runs loose. `closest_to_ball(obs)` — import it from `soccer` — is the
        other way to ask, and it flips the moment somebody outruns you. They
        disagree often, and choosing between them is your first real decision.

        Your split does not have to be this one, either. It can be per player,
        or by where the ball is on the pitch, or something else entirely.
        """
        actions = TeamAction()
        ours = obs.ball.controlling_team == 0
        if ours and not self.had_possession_last_tick:
            self.attacking_lane_phase = 1 - self.attacking_lane_phase
        self.had_possession_last_tick = ours
        protecting_late_result = (
            obs.time_remaining <= 0.10
            and obs.score[0] >= obs.score[1]
        )

        if (
            obs.tick > self.quick_shot_until
            or obs.ball.controlling_team == 1
        ):
            self.quick_shot_player_id = None
            self.quick_shot_until = -1

        for event in obs.events:
            if event.get("kind") == "goal" and event.get("team") == 0:
                self.restart_wait_until = obs.tick + 59

        ball_at_centre = (
            obs.ball.position[0] ** 2 + obs.ball.position[1] ** 2
            <= 1.0 ** 2
        )
        ball_is_stationary = (
            obs.ball.velocity[0] ** 2 + obs.ball.velocity[1] ** 2
            <= 0.05 ** 2
        )
        do_nothing_restart = (
            not ours
            and ball_at_centre
            and ball_is_stationary
        )

        if self.pass_receiver_id is not None:
            receiver = next(
                (
                    player
                    for player in obs.my_players
                    if player.id == self.pass_receiver_id
                ),
                None,
            )
            pass_is_finished = (
                receiver is None
                or obs.tick > self.pass_follow_until
                or obs.ball.controlling_team == 1
                or receiver.has_control
                or obs.can_kick(receiver.id)
            )

            if pass_is_finished:
                self.pass_receiver_id = None
                self.pass_target = None
                self.pass_follow_until = -1

                # Select the chaser.
        keeper = obs.my_players[0]
        defenders = obs.my_players[1:3]
        outfield_players = obs.my_players[1:]

        coordinated_attack = (
            ours
            and not protecting_late_result
            and obs.ball.position[0] >= obs.opponent_goal[0] - 30.0
        )
        coordinated_run_targets = {}

        if coordinated_attack:
            carrier = next(
                (
                    player
                    for player in outfield_players
                    if player.has_control
                ),
                None,
            )
            available_attackers = [
                player
                for player in obs.my_players[3:]
                if carrier is None or player.id != carrier.id
            ]
            ball_side = -1.0 if obs.ball.position[1] < 0.0 else 1.0
            crossing_target = (
                min(obs.ball.position[0] + 8.0, obs.opponent_goal[0] - 8.0),
                -ball_side * 3.0,
            )
            far_post_target = (
                obs.opponent_goal[0] - 6.0,
                -ball_side * (obs.field.goal_width / 2 - 2.0),
            )

            if available_attackers:
                crossing_runner = min(
                    available_attackers,
                    key=lambda player: (
                        (player.position[0] - crossing_target[0]) ** 2
                        + (player.position[1] - crossing_target[1]) ** 2
                    ),
                )
                coordinated_run_targets[crossing_runner.id] = crossing_target
                remaining_attackers = [
                    player
                    for player in available_attackers
                    if player.id != crossing_runner.id
                ]

                if remaining_attackers:
                    far_post_runner = remaining_attackers[0]
                    coordinated_run_targets[far_post_runner.id] = far_post_target

        # Calculate each player's ball distance once this tick and reuse it
        # for chaser selection, role assignment, and second-ball selection.
        ball_distances_squared = {
            player.id: self.distance_squared(
                player.position,
                obs.ball.position,
            )
            for player in obs.my_players
        }

        def ball_distance_squared(player):
            return ball_distances_squared[player.id]

        def receiver_target(receiver):
            distance_to_ball_squared = (
                (receiver.position[0] - obs.ball.position[0]) ** 2
                + (receiver.position[1] - obs.ball.position[1]) ** 2
            )

            if distance_to_ball_squared <= 12.0 ** 2:
                return obs.ball.position

            return self.pass_target

        keeper_is_closest = ball_distance_squared(keeper) < min(
            ball_distance_squared(defender) for defender in defenders
        )

        ball_in_defensive_area = (
            obs.ball.position[0] < obs.field.my_goal[0] + 12.0
            and abs(obs.ball.position[1]) < obs.field.goal_width / 2 + 8.0
        )

        keeper_should_clear = keeper_is_closest and ball_in_defensive_area

        if keeper_should_clear:
            chaser_id = keeper.id
        else:
            chaser_id = min(
                outfield_players,
                key=ball_distance_squared,
            ).id

        # Outfield responsibilities follow the play rather than belonging to
        # permanent player numbers. One presses, one protects, one supports,
        # and one stays ahead as the attacking outlet.
        role_chaser = min(
            outfield_players,
            key=ball_distance_squared,
        )
        dynamic_roles = {role_chaser.id: "chaser"}
        unassigned = [
            player
            for player in outfield_players
            if player.id != role_chaser.id
        ]
        role_defender = min(
            unassigned,
            key=lambda player: player.position[0],
        )
        dynamic_roles[role_defender.id] = "defender"
        unassigned = [
            player
            for player in unassigned
            if player.id != role_defender.id
        ]
        role_striker = max(
            unassigned,
            key=lambda player: player.position[0],
        )
        dynamic_roles[role_striker.id] = "striker"
        role_support = next(
            player
            for player in unassigned
            if player.id != role_striker.id
        )
        dynamic_roles[role_support.id] = "support"

        if ours or obs.tick > self.second_ball_until:
            self.second_ball_player_id = None
            self.second_ball_until = -1

        lost_ball_this_tick = any(
            event.get("kind") == "turnover"
            and event.get("from_team") == 0
            and event.get("to_team") == 1
            for event in obs.events
        )
        counterpress_is_safe = (
            obs.ball.position[0] > obs.field.my_goal[0] + 25.0
        )

        if lost_ball_this_tick and counterpress_is_safe:
            # The normal chaser attacks the loose ball. Add the nearer of the
            # support and striker briefly, while the dynamic defender stays
            # behind the play as protection.
            second_ball_player = min(
                (role_support, role_striker),
                key=ball_distance_squared,
            )
            self.second_ball_player_id = second_ball_player.id
            self.second_ball_until = obs.tick + 16

        for player in obs.my_players:
            # GOALKEEPER
            if player.id == 0:
                keeper_min_x = (
                    obs.field.my_goal[0]
                    + obs.field.player_radius * 2
                )

                keeper_max_x = (
                    obs.field.my_goal[0]
                    + 8.0
                )

                keeper_max_y = (
                    obs.field.goal_width / 2
                    + 4.0
                )

                keeper_clear_target = (
                    max(
                        keeper_min_x,
                        min(
                            obs.ball.position[0],
                            keeper_max_x,
                        ),
                    ),
                    max(
                        -keeper_max_y,
                        min(
                            obs.ball.position[1],
                            keeper_max_y,
                        ),
                    ),
                )
                ball_is_heading_wide = False
                incoming_shot_y = None

                if obs.ball.velocity[0] < -0.1:
                    time_to_goal = (
                        obs.field.my_goal[0] - obs.ball.position[0]
                    ) / obs.ball.velocity[0]
                    predicted_goal_y = (
                        obs.ball.position[1]
                        + obs.ball.velocity[1] * time_to_goal
                    )
                    ball_is_heading_wide = (
                        abs(predicted_goal_y)
                        > obs.field.goal_width / 2
                    )
                    if (
                        0.0 <= time_to_goal <= 3.0
                        and not ball_is_heading_wide
                    ):
                        incoming_shot_y = predicted_goal_y

                if ball_is_heading_wide:
                    opponent_near_wide_ball = any(
                        self.distance_squared(
                            opponent.position,
                            obs.ball.position,
                        ) <= 6.0 ** 2
                        for opponent in obs.opponents
                    )
                    wide_ball_can_be_shot = (
                        opponent_near_wide_ball
                        and obs.ball.position[0]
                        < obs.field.my_goal[0] + 18.0
                    )

                    if wide_ball_can_be_shot:
                        # A nearby attacker can still shoot across goal, so
                        # cover the near post without leaving the goal mouth.
                        near_post_limit = (
                            obs.field.goal_width / 2
                            - obs.field.player_radius
                        )
                        keeper_wide_target = (
                            keeper_min_x,
                            max(
                                -near_post_limit,
                                min(
                                    obs.ball.position[1],
                                    near_post_limit,
                                ),
                            ),
                        )
                    else:
                        # The ball is already missing the goal and no nearby
                        # attacker can redirect it, so safely recenter.
                        keeper_wide_target = (keeper_min_x, 0.0)

                    actions.move(
                        player.id,
                        direction(
                            player.position,
                            keeper_wide_target,
                        ),
                    )
                    continue

                if keeper_should_clear:
                    if (
                        obs.can_kick(player.id)
                        and obs.ball.velocity[0] < -10.0
                    ):
                        # Meet a fast on-target shot straight on. This puts
                        # all available kick force into stopping its movement
                        # toward our goal instead of deflecting it across goal.
                        straight_clear_target = (
                            obs.ball.position[0] + 30.0,
                            obs.ball.position[1],
                        )
                        actions.set(
                            player.id,
                            PlayerAction(
                                movement=direction(
                                    player.position,
                                    keeper_clear_target,
                                ),
                                kick_direction=direction(
                                    obs.ball.position,
                                    straight_clear_target,
                                ),
                                kick_power=1.0,
                            ),
                        )

                    elif obs.can_kick(player.id):
                        opponents_above = sum(
                            1
                            for opponent in obs.opponents
                            if opponent.position[1] >= 0
                        )

                        opponents_below = (
                            len(obs.opponents)
                            - opponents_above
                        )

                        if opponents_above < opponents_below:
                            emergency_clear_y = 18.0
                        else:
                            emergency_clear_y = -18.0

                        emergency_clear_target = (
                            min(
                                player.position[0] + 30.0,
                                0.0,
                            ),
                            emergency_clear_y,
                        )

                        actions.set(
                            player.id,
                            PlayerAction(
                                movement=direction(
                                    player.position,
                                    keeper_clear_target,
                                ),
                                kick_direction=direction(
                                    obs.ball.position,
                                    emergency_clear_target,
                                ),
                                kick_power=1.0,
                            ),
                        )
                    else:
                        if player.kick_cooldown_ticks > 0:
                            recovery_y = max(
                                -obs.field.goal_width / 2,
                                min(
                                    obs.ball.position[1],
                                    obs.field.goal_width / 2,
                                ),
                            )
                            recovery_target = (
                                obs.field.my_goal[0]
                                + obs.field.player_radius * 2,
                                recovery_y,
                            )
                        else:
                            recovery_target = keeper_clear_target

                        actions.move(
                            player.id,
                            direction(
                                player.position,
                                recovery_target,
                            ),
                        )

                    continue

                # Fixed horizontal position
                keeper_x = (
                    obs.field.my_goal[0]
                    + obs.field.player_radius * 2
                )
                keeper_limt = (
                    obs.field.goal_width / 2
                    - obs.field.player_radius
                )

                # Follow ordinary play vertically. For an incoming shot,
                # move toward where it will cross the goal line instead of
                # chasing its current position and reacting too late.
                keeper_tracking_y = (
                    incoming_shot_y
                    if incoming_shot_y is not None
                    else obs.ball.position[1]
                )
                keeper_y = max(
                    -keeper_limt,
                    min(
                        keeper_tracking_y,
                        keeper_limt,
                    ),
                )
                keeper_target = (keeper_x, keeper_y)

                # Pass to the defender with the most space.
                if obs.can_kick(player.id):
                # Possible forward clearance lanes.
                    clear_x = min(
                        player.position[0] + 30.0,
                        0.0,
                    )

                    clearance_targets = [
                        (clear_x, -18.0),
                        (clear_x, -9.0),
                        (clear_x, 0.0),
                        (clear_x, 9.0),
                        (clear_x, 18.0),
                    ]

                    def clearance_lane_space(target):
                        clear_dx = (
                            target[0]
                            - obs.ball.position[0]
                        )
                        clear_dy = (
                            target[1]
                            - obs.ball.position[1]
                        )

                        clear_length_squared = (
                            clear_dx * clear_dx
                            + clear_dy * clear_dy
                        )

                        minimum_space_squared = float("inf")

                        # A clearance lane is unsafe if either an opponent or
                        # one of our outfield players can collide with it.
                        # The latter can reverse a good clearance into our
                        # own goal, so both teams must be considered here.
                        for opponent in [*obs.opponents, *outfield_players]:
                            opponent_dx = (
                                opponent.position[0]
                                - obs.ball.position[0]
                            )
                            opponent_dy = (
                                opponent.position[1]
                                - obs.ball.position[1]
                            )

                            t = (
                                opponent_dx * clear_dx
                                + opponent_dy * clear_dy
                            ) / clear_length_squared

                            t = max(0.0, min(t, 1.0))

                            closest_x = (
                                obs.ball.position[0]
                                + t * clear_dx
                            )
                            closest_y = (
                                obs.ball.position[1]
                                + t * clear_dy
                            )

                            space_squared = (
                                (
                                    opponent.position[0]
                                    - closest_x
                                ) ** 2
                                + (
                                    opponent.position[1]
                                    - closest_y
                                ) ** 2
                            )

                            minimum_space_squared = min(
                                minimum_space_squared,
                                space_squared,
                            )

                        return minimum_space_squared

                    best_clearance_target = max(
                        clearance_targets,
                        key=clearance_lane_space,
                    )

                    actions.set(
                        player.id,
                        PlayerAction(
                            movement=direction(
                                player.position,
                                keeper_target,
                            ),
                            kick_direction=direction(
                                obs.ball.position,
                                best_clearance_target,
                            ),
                            kick_power=1.0,
                        ),
                    )

                else:
                    actions.move(
                        player.id,
                        direction(
                            player.position,
                            keeper_target,
                        ),
                    )
                continue

            if do_nothing_restart:
                restart_is_live = obs.tick >= self.restart_wait_until

                if player.id == 3:
                    if restart_is_live:
                        if obs.can_kick(player.id):
                            restart_target = (8.0, 0.0)
                            actions.set(
                                player.id,
                                PlayerAction(
                                    movement=direction(
                                        player.position,
                                        restart_target,
                                    ),
                                    kick_direction=direction(
                                        player.position,
                                        restart_target,
                                    ),
                                    kick_power=0.25,
                                ),
                            )
                        else:
                            actions.move(
                                player.id,
                                direction(player.position, obs.ball.position),
                            )
                    else:
                        collector_wait_target = (
                            -obs.field.centre_circle_radius - 1.0,
                            0.0,
                        )
                        actions.move(
                            player.id,
                            direction(player.position, collector_wait_target),
                        )

                elif player.id == 4:
                    if restart_is_live:
                        receiver_target = (8.0, 8.0)
                    else:
                        receiver_target = (
                            -obs.field.centre_circle_radius - 1.0,
                            8.0,
                        )
                    actions.move(
                        player.id,
                        direction(player.position, receiver_target),
                    )

                elif player.id == 1:
                    actions.move(
                        player.id,
                        direction(player.position, (-20.0, -12.0)),
                    )

                else:
                    actions.move(
                        player.id,
                        direction(player.position, (-20.0, 12.0)),
                    )

                continue

            if player.id == self.pass_receiver_id:
                actions.move(
                    player.id,
                    direction(player.position, receiver_target(player)),
                )
                continue

            nearest = player.id == chaser_id

            if ours and nearest:
                # Ours, and I am the one on it: have a go at goal. Check
                # can_kick first — a kick from out of range is a wasted tick,
                # and comes back to you as a "kick_rejected" event.
                if obs.can_kick(player.id):
                    goal_x = obs.opponent_goal[0]
                    goal_y = obs.opponent_goal[1]

                    distance_to_goal_squared = (
                        (player.position[0] - goal_x) ** 2
                        + (player.position[1] - goal_y) ** 2
                    )

                    quick_shot_opportunity = (
                        player.id == self.quick_shot_player_id
                        and obs.tick <= self.quick_shot_until
                    )
                    decisive_shot_opportunity = (
                        dynamic_roles[player.id] in (
                            "chaser",
                            "support",
                            "striker",
                        )
                        and player.position[0]
                        >= obs.opponent_goal[0] - 32.0
                        and abs(player.position[1] - goal_y)
                        <= obs.field.goal_width / 2 + 8.0
                    )
                    shooting_distance = (
                        32.0
                        if decisive_shot_opportunity
                        else 30.0
                        if quick_shot_opportunity
                        else 25.0
                    )
                    kick_origin = player.position
                    shot_is_in_range = (
                        distance_to_goal_squared <= shooting_distance ** 2
                    )

                    shot_limit = (
                        obs.field.goal_width / 2
                        - obs.field.player_radius * 2
                    )
                    shot_limit *= 0.75
                    shot_targets = [
                        (goal_x, -shot_limit),
                        (goal_x, -shot_limit / 2),
                        (goal_x, goal_y),
                        (goal_x, shot_limit / 2),
                        (goal_x, shot_limit),
                    ]
                    opponent_keeper = min(
                        obs.opponents,
                        key=lambda opponent: (
                            (opponent.position[0] - goal_x) ** 2
                            + (opponent.position[1] - goal_y) ** 2
                        ),
                    )

                    def shot_lane_clearance(target):
                        shot_dx = target[0] - obs.ball.position[0]
                        shot_dy = target[1] - obs.ball.position[1]
                        shot_length_squared = (
                            shot_dx * shot_dx + shot_dy * shot_dy
                        )
                        minimum_clearance_squared = float("inf")

                        for opponent in obs.opponents:
                            opponent_dx = (
                                opponent.position[0] - obs.ball.position[0]
                            )
                            opponent_dy = (
                                opponent.position[1] - obs.ball.position[1]
                            )
                            t = (
                                opponent_dx * shot_dx
                                + opponent_dy * shot_dy
                            ) / shot_length_squared
                            t = max(0.0, min(1.0, t))
                            closest_x = obs.ball.position[0] + t * shot_dx
                            closest_y = obs.ball.position[1] + t * shot_dy
                            clearance_squared = (
                                (opponent.position[0] - closest_x) ** 2
                                + (opponent.position[1] - closest_y) ** 2
                            )
                            minimum_clearance_squared = min(
                                minimum_clearance_squared,
                                clearance_squared,
                            )

                        keeper_distance_squared = (
                            (opponent_keeper.position[0] - target[0]) ** 2
                            + (opponent_keeper.position[1] - target[1]) ** 2
                        )
                        shot_quality = (
                            min(minimum_clearance_squared, 100.0)
                            + 0.35 * min(keeper_distance_squared, 100.0)
                            - 0.15 * abs(target[1] - goal_y)
                        )

                        return shot_quality, minimum_clearance_squared

                    shot_options = [
                        (target, shot_lane_clearance(target))
                        for target in shot_targets
                    ]
                    shot_target, best_shot_measurement = max(
                        shot_options,
                        key=lambda option: option[1][0],
                    )
                    best_shot_clearance_squared = (
                        best_shot_measurement[1]
                    )
                    close_range_finish = (
                        distance_to_goal_squared <= 15.0 ** 2
                    )
                    required_shot_clearance = (
                        obs.field.player_radius
                        + (0.5 if close_range_finish else 1.25)
                    )
                    shot_lane_is_clear = (
                        best_shot_clearance_squared
                        >= required_shot_clearance ** 2
                    )
                    shooting_angle_is_good = (
                        abs(obs.ball.position[1] - goal_y)
                        <= obs.field.goal_width / 2 + 6.0
                    )

                    if (
                        shot_is_in_range
                        and shot_lane_is_clear
                        and shooting_angle_is_good
                    ):
                        kick_origin = obs.ball.position
                        kick_target = shot_target
                        kick_power = 1.0
                        self.quick_shot_player_id = None
                        self.quick_shot_until = -1

                    else:
                        # Find the furthest-forward teammate.
                        teammates = [
                            teammate
                            for teammate in outfield_players
                            if teammate.id != player.id
                        ]
                        rear_pressure_count = sum(
                            1
                            for opponent in obs.opponents
                            if (
                                opponent.position[0] <= player.position[0] + 2.0
                                and (
                                    (opponent.position[0] - player.position[0]) ** 2
                                    + (opponent.position[1] - player.position[1]) ** 2
                                    <= 12.0 ** 2
                                )
                            )
                        )
                        nearby_teammates = [
                            teammate
                            for teammate in teammates
                            if (
                                (teammate.position[0] - player.position[0]) ** 2
                                + (teammate.position[1] - player.position[1]) ** 2
                                <= 22.0 ** 2
                            )
                        ]

                        if nearby_teammates and rear_pressure_count < 3:
                            teammates = nearby_teammates

                        forward_teammates = [
                            teammate
                            for teammate in teammates
                            if teammate.position[0] > player.position[0] + 3.0
                        ]

                        if forward_teammates and rear_pressure_count < 3:
                            teammates = forward_teammates

                        in_final_third = (
                            player.position[0]
                            >= obs.opponent_goal[0] - 30.0
                        )
                        carrier_under_close_pressure = any(
                            self.distance_squared(
                                player.position,
                                opponent.position,
                            ) <= 3.5 ** 2
                            for opponent in obs.opponents
                        )
                        required_receiver_space = (
                            3.5
                            if (
                                in_final_third
                                and carrier_under_close_pressure
                            )
                            else 4.5 if in_final_third else 6.0
                        )
                        required_lane_clearance = (
                            2.25 if in_final_third else 3.0
                        )

                        receiver_measurements = {}

                        for teammate in teammates:
                            nearest_opponent_distance_squared = min(
                                self.distance_squared(
                                    teammate.position,
                                    opponent.position,
                                )
                                for opponent in obs.opponents
                            )
                            pass_distance_squared = self.distance_squared(
                                teammate.position,
                                player.position,
                            )
                            lane_clearance_squared = (
                                self.lane_clearance_squared(
                                    player.position,
                                    teammate.position,
                                    obs.opponents,
                                )
                            )
                            receiver_measurements[teammate.id] = (
                                nearest_opponent_distance_squared,
                                pass_distance_squared,
                                lane_clearance_squared,
                            )

                        def pass_score(teammate):
                            (
                                nearest_opponent_distance_squared,
                                pass_distance_squared,
                                lane_clearance_squared,
                            ) = receiver_measurements[teammate.id]
                            openness_score = min(
                                nearest_opponent_distance_squared,
                                100.0,
                            )
                            lane_score = min(
                                lane_clearance_squared,
                                100.0,
                            )
                            forward_progress = (
                                teammate.position[0]
                                - player.position[0]
                            )
                            coordinated_run_bonus = 0.0
                            if teammate.id in coordinated_run_targets:
                                run_target = coordinated_run_targets[teammate.id]
                                run_distance_squared = (
                                    (teammate.position[0] - run_target[0]) ** 2
                                    + (teammate.position[1] - run_target[1]) ** 2
                                )
                                if run_distance_squared <= 6.0 ** 2:
                                    coordinated_run_bonus = 120.0

                            if rear_pressure_count >= 3:
                                return (
                                    2.0 * openness_score
                                    + 2.5 * lane_score
                                    + 3.0 * forward_progress
                                    - 0.15 * pass_distance_squared
                                    + coordinated_run_bonus
                                )

                            return (
                                openness_score
                                + 2.0 * lane_score
                                + 6.0 * forward_progress
                                - 0.25 * pass_distance_squared
                                + coordinated_run_bonus
                            )

                        safe_receivers = [
                            teammate
                            for teammate in teammates
                            if (
                                receiver_measurements[teammate.id][0]
                                >= required_receiver_space ** 2
                                and receiver_measurements[teammate.id][2]
                                >= required_lane_clearance ** 2
                            )
                        ]
                        receiver = max(
                            safe_receivers if safe_receivers else teammates,
                            key=pass_score,
                        )
                        (
                            receiver_space_squared,
                            pass_length_squared,
                            receiver_lane_clearance_squared,
                        ) = receiver_measurements[receiver.id]

                        receiver_is_open = (
                            receiver_space_squared
                            >= required_receiver_space ** 2
                        )
                        receiver_is_within_range = (
                            pass_length_squared <= 22.0 ** 2
                        )
                        opponents_near_carrier = sum(
                            1
                            for opponent in obs.opponents
                            if (
                                (opponent.position[0] - player.position[0]) ** 2
                                + (opponent.position[1] - player.position[1]) ** 2
                                <= 12.0 ** 2
                            )
                        )
                        pass_lane_is_clear = (
                            receiver_lane_clearance_squared
                            >= required_lane_clearance ** 2
                        )

                        receiver_is_forward = (
                            receiver.position[0] > player.position[0] + 3.0
                        )
                        receiver_is_safe_escape = (
                            rear_pressure_count >= 3
                            and receiver.position[0] >= player.position[0] - 6.0
                        )
                        receiver_is_recycle_option = (
                            shot_is_in_range
                            and not shot_lane_is_clear
                            and receiver.position[0] >= player.position[0] - 10.0
                        )
                        receiver_is_pressure_release = (
                            in_final_third
                            and carrier_under_close_pressure
                            and pass_length_squared <= 12.0 ** 2
                            and receiver.position[0]
                            >= player.position[0] - 6.0
                        )

                        if (
                            (
                                receiver_is_forward
                                or receiver_is_safe_escape
                                or receiver_is_recycle_option
                                or receiver_is_pressure_release
                            )
                            and receiver_is_open
                            and pass_lane_is_clear
                            and (
                                receiver_is_within_range
                                or (
                                    rear_pressure_count >= 3
                                    and not protecting_late_result
                                )
                            )
                        ):
                            # Lead an available teammate beyond the group
                            # chasing the ball instead of passing to their feet.
                            use_through_ball = (
                                player.id >= 3
                                and (
                                    opponents_near_carrier >= 3
                                    or (
                                        shot_is_in_range
                                        and not shot_lane_is_clear
                                        and opponents_near_carrier >= 2
                                    )
                                )
                            )

                            if use_through_ball:
                                pass_lead = 8.0
                            elif receiver_is_pressure_release:
                                pass_lead = 1.0
                            elif receiver_is_safe_escape:
                                pass_lead = 2.0
                            elif receiver_is_recycle_option:
                                pass_lead = 1.0
                            else:
                                pass_lead = 4.0

                            receiver_has_completed_run = False
                            if receiver.id in coordinated_run_targets:
                                run_target = coordinated_run_targets[receiver.id]
                                receiver_has_completed_run = (
                                    (receiver.position[0] - run_target[0]) ** 2
                                    + (receiver.position[1] - run_target[1]) ** 2
                                    <= 6.0 ** 2
                                )

                            if receiver_has_completed_run:
                                kick_target = coordinated_run_targets[receiver.id]
                            else:
                                receiver_marker = min(
                                    obs.opponents,
                                    key=lambda opponent: (
                                        (
                                            opponent.position[0]
                                            - receiver.position[0]
                                        ) ** 2
                                        + (
                                            opponent.position[1]
                                            - receiver.position[1]
                                        ) ** 2
                                    ),
                                )
                                receiver_marker_distance_squared = (
                                    (
                                        receiver_marker.position[0]
                                        - receiver.position[0]
                                    ) ** 2
                                    + (
                                        receiver_marker.position[1]
                                        - receiver.position[1]
                                    ) ** 2
                                )
                                pass_target_y = receiver.position[1]

                                if receiver_marker_distance_squared <= 8.0 ** 2:
                                    # Lead a marked receiver into the space on
                                    # the opposite side of their defender.
                                    marker_escape_direction = (
                                        -1.0
                                        if receiver_marker.position[1]
                                        >= receiver.position[1]
                                        else 1.0
                                    )
                                    pass_target_y += (
                                        marker_escape_direction * 5.0
                                    )
                                    pass_target_y = max(
                                        -obs.field.height / 2 + 3.0,
                                        min(
                                            pass_target_y,
                                            obs.field.height / 2 - 3.0,
                                        ),
                                    )

                                kick_target = (
                                    min(
                                        receiver.position[0] + pass_lead,
                                        obs.opponent_goal[0] - 2.0,
                                    ),
                                    pass_target_y,
                                )
                            pass_distance = (
                                (player.position[0] - kick_target[0]) ** 2
                                + (player.position[1] - kick_target[1]) ** 2
                            ) ** 0.5
                            if use_through_ball:
                                kick_power = max(
                                    0.40,
                                    min(pass_distance / 26.0, 0.85),
                                )
                            else:
                                kick_power = max(
                                    0.35,
                                    min(pass_distance / 30.0, 0.8),
                                )

                            self.pass_receiver_id = receiver.id
                            self.pass_target = kick_target
                            if coordinated_attack:
                                self.quick_shot_player_id = receiver.id
                                self.quick_shot_until = obs.tick + 24
                            receiver_commitment = int(
                                max(
                                    12.0,
                                    min(30.0, 8.0 + pass_distance * 0.6),
                                )
                            )
                            self.pass_follow_until = (
                                obs.tick + receiver_commitment
                            )
                        else:
                            # Nobody is safely available: compare several
                            # forward lanes and dribble into the best one.
                            target_x = min(
                                player.position[0] + 7.0,
                                obs.opponent_goal[0] - 2.0,
                            )
                            if coordinated_attack:
                                lane_y_values = (-6.0, 0.0, 6.0)
                            else:
                                lane_y_values = (
                                    -18.0, -12.0, -6.0,
                                    0.0,
                                    6.0, 12.0, 18.0,
                                )

                            def lane_score(target_y):
                                lane_dx = target_x - player.position[0]
                                lane_dy = target_y - player.position[1]
                                lane_length_squared = (
                                    lane_dx * lane_dx + lane_dy * lane_dy
                                )
                                clearance_squared = float("inf")

                                for opponent in obs.opponents:
                                    opponent_dx = (
                                        opponent.position[0] - player.position[0]
                                    )
                                    opponent_dy = (
                                        opponent.position[1] - player.position[1]
                                    )
                                    t = (
                                        opponent_dx * lane_dx
                                        + opponent_dy * lane_dy
                                    ) / lane_length_squared
                                    t = max(0.0, min(1.0, t))
                                    closest_x = player.position[0] + t * lane_dx
                                    closest_y = player.position[1] + t * lane_dy
                                    distance_squared = (
                                        (opponent.position[0] - closest_x) ** 2
                                        + (opponent.position[1] - closest_y) ** 2
                                    )
                                    clearance_squared = min(
                                        clearance_squared,
                                        distance_squared,
                                    )

                                return (
                                    min(clearance_squared, 100.0)
                                    - 0.8 * abs(target_y)
                                    - 0.5 * abs(target_y - player.position[1])
                                )

                            dribble_y = max(lane_y_values, key=lane_score)
                            kick_target = (target_x, dribble_y)
                            if in_final_third:
                                # Keep the ball close enough to follow the
                                # touch with a shot before the keeper arrives.
                                kick_power = 0.20
                            elif obs.ball.position[0] >= 0.0:
                                kick_power = 0.30
                            else:
                                kick_power = 0.25

                    kick_dx = kick_target[0] - obs.ball.position[0]
                    kick_dy = kick_target[1] - obs.ball.position[1]
                    kick_threatens_own_goal = False

                    if obs.ball.position[0] < 0.0 and kick_dx < 0.0:
                        goal_projection = (
                            obs.field.my_goal[0] - obs.ball.position[0]
                        ) / kick_dx
                        projected_goal_y = (
                            obs.ball.position[1]
                            + goal_projection * kick_dy
                        )
                        kick_threatens_own_goal = (
                            abs(projected_goal_y)
                            <= obs.field.goal_width / 2
                            + obs.field.player_radius
                        )

                    if kick_threatens_own_goal:
                        safe_clear_y = (
                            18.0 if obs.ball.position[1] <= 0.0 else -18.0
                        )
                        kick_origin = obs.ball.position
                        kick_target = (
                            min(
                                obs.ball.position[0] + 20.0,
                                obs.opponent_goal[0] - 5.0,
                            ),
                            safe_clear_y,
                        )
                        kick_power = max(kick_power, 0.6)

                    actions.set(
                        player.id,
                        PlayerAction(
                            movement=direction(
                                player.position,
                                kick_target,
                            ),
                            kick_direction=direction(
                                kick_origin,
                                kick_target,
                            ),
                            kick_power=kick_power,
                        ),
                    )

                else:
                    actions.move(
                        player.id, direction(player.position, obs.ball.position)
                    )

                """""
                # Ours, and somebody else is on it: get up the pitch. Running
                # at the goal puts all four of you in the same place, which is
                # the first thing worth fixing — nobody can receive a pass
                # standing on top of the carrier.
                """""
            elif ours:
                ball_x = obs.ball.position[0]
                ball_y = obs.ball.position[1]
                attacking_midfielder_id = None
                rebound_supporter_id = None

                ball_is_heading_toward_goal = (
                    not protecting_late_result
                    and ball_x > obs.opponent_goal[0] - 25.0
                    and obs.ball.velocity[0] > 0.15
                )

                if ball_is_heading_toward_goal:
                    rebound_target = (
                        obs.opponent_goal[0] - 8.0,
                        max(-8.0, min(ball_y * 0.5, 8.0)),
                    )
                    rebound_supporter_id = min(
                        obs.my_players[3:],
                        key=lambda teammate: (
                            (teammate.position[0] - rebound_target[0]) ** 2
                            + (teammate.position[1] - rebound_target[1]) ** 2
                        ),
                    ).id

                if ball_x > -5.0 and not protecting_late_result:
                    attacking_midfielder_id = role_support.id

                if player.id in coordinated_run_targets:
                    # In the final third, supporting attackers make distinct
                    # crossing and far-post runs instead of occupying the same
                    # channel as the carrier.
                    target_x, target_y = coordinated_run_targets[player.id]

                elif player.id == rebound_supporter_id:
                    # While a shot is travelling, one attacker anticipates a
                    # loose save without committing a defender or chasing a
                    # fixed target after the situation has changed.
                    target_x, target_y = rebound_target

                elif player.id == attacking_midfielder_id:
                    # The defender on the ball's side becomes a temporary
                    # midfielder and attacks the central channel behind it.
                    target_x = min(
                        ball_x - 4.0,
                        obs.field.opponent_goal[0] - 12.0,
                    )
                    target_x = max(target_x, -5.0)
                    target_y = max(
                        -8.0,
                        min(ball_y * 0.35, 8.0),
                    )

                elif protecting_late_result and player.id == 1:
                    target_x = obs.field.my_goal[0] + 12.0
                    target_y = -6.0

                elif protecting_late_result and player.id == 2:
                    target_x = obs.field.my_goal[0] + 12.0
                    target_y = 6.0

                elif protecting_late_result and player.id == 3:
                    target_x = -10.0
                    target_y = -10.0

                elif protecting_late_result:
                    target_x = -10.0
                    target_y = 10.0

                elif dynamic_roles[player.id] == "defender":
                    # The current deepest outfielder protects the attack.
                    target_x = min(ball_x - 12.0, -5.0)
                    target_y = (
                        -12.0 if player.position[1] <= 0.0 else 12.0
                    )

                elif dynamic_roles[player.id] == "striker":
                    # The current furthest outfielder stays ahead and changes
                    # lanes whenever possession is regained.
                    target_x = min(
                        ball_x + 12.0,
                        obs.field.opponent_goal[0] - 5.0,
                    )
                    target_y = (
                        10.0
                        if self.attacking_lane_phase == 1
                        else -10.0
                    )

                else:
                    # The support player occupies the opposite lane, close
                    # enough to contest an incomplete pass or loose touch.
                    target_x = min(
                        ball_x + 5.0,
                        obs.field.opponent_goal[0] - 9.0,
                    )
                    target_y = (
                        -10.0
                        if self.attacking_lane_phase == 1
                        else 10.0
                    )

                if (
                    dynamic_roles[player.id] in ("support", "striker")
                    and player.id not in coordinated_run_targets
                    and player.id != rebound_supporter_id
                    and not protecting_late_result
                ):
                    marker = min(
                        obs.opponents,
                        key=lambda opponent: (
                            (opponent.position[0] - player.position[0]) ** 2
                            + (opponent.position[1] - player.position[1]) ** 2
                        ),
                    )
                    marker_distance_squared = (
                        (marker.position[0] - player.position[0]) ** 2
                        + (marker.position[1] - player.position[1]) ** 2
                    )

                    if marker_distance_squared <= 8.0 ** 2:
                        # A tightly followed attacker cuts away from their
                        # marker while continuing forward. This creates a
                        # moving passing lane instead of asking for the ball
                        # with the defender standing beside the receiver.
                        escape_direction = (
                            -1.0
                            if marker.position[1] >= player.position[1]
                            else 1.0
                        )
                        target_x = min(
                            max(target_x, player.position[0] + 6.0),
                            obs.opponent_goal[0] - 7.0,
                        )
                        target_y = max(
                            -obs.field.height / 2 + 3.0,
                            min(
                                target_y + escape_direction * 8.0,
                                obs.field.height / 2 - 3.0,
                            ),
                        )

                support_target = (target_x, target_y)

                actions.move(
                    player.id,
                    direction(player.position, support_target),
                )

            elif (
                player.id == self.second_ball_player_id
                and obs.tick <= self.second_ball_until
                and not nearest
            ):
                # Commit briefly to the second ball, then return to the
                # current dynamic role if possession has not been recovered.
                actions.move(
                    player.id,
                    direction(player.position, obs.ball.position),
                )

            elif nearest:
                # Theirs, and I am the closest: close down the carrier and
                # actively play the ball as soon as it enters kicking range.
                if obs.can_kick(player.id):
                    actions.set(
                        player.id,
                        self.defensive_challenge_action(obs, player),
                    )
                else:
                    actions.move(
                        player.id,
                        direction(player.position, obs.ball.position),
                    )

                "Theirs, and somebody else is closer: get behind the ball."
            else:
                ball_x = obs.ball.position[0]
                ball_y = obs.ball.position[1]
                goal_x = obs.field.my_goal[0]

                if protecting_late_result and player.id == 1:
                    target_x = goal_x + 12.0
                    target_y = -6.0

                elif protecting_late_result and player.id == 2:
                    target_x = goal_x + 12.0
                    target_y = 6.0

                elif protecting_late_result and player.id == 3:
                    target_x = -10.0
                    target_y = -10.0

                elif protecting_late_result:
                    target_x = -10.0
                    target_y = 10.0

                elif dynamic_roles[player.id] == "defender":
                    # The deepest available outfielder protects the goal.
                    target_x = max(
                        goal_x + 8.0,
                        min(ball_x - 8.0, -20.0),
                    )
                    target_y = ball_y * 0.35

                elif dynamic_roles[player.id] == "support":
                    # Stay close behind the defensive contest instead of
                    # waiting in midfield while the chaser and defender face
                    # the attack alone.
                    target_x = max(
                        goal_x + 18.0,
                        min(ball_x - 3.0, 0.0),
                    )
                    target_y = max(
                        -12.0,
                        min(ball_y * 0.6, 12.0),
                    )

                else:
                    # Preserve one outlet instead of dropping everybody onto
                    # the ball and carrying every marker toward our goal.
                    target_x = max(
                        -10.0,
                        min(ball_x + 2.0, 8.0),
                    )
                    target_y = (
                        -10.0 if player.position[1] <= 0.0 else 10.0
                    )

                defensive_target = (target_x, target_y)

                actions.move(
                    player.id,
                    direction(player.position, defensive_target),
                )

        if self.pass_receiver_id is not None:
            receiver = next(
                player
                for player in obs.my_players
                if player.id == self.pass_receiver_id
            )
            actions.move(
                receiver.id,
                direction(receiver.position, receiver_target(receiver)),
            )

        return actions
