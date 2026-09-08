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

    def reset(self, seed):
        self.restart_wait_until = -1
        self.pass_receiver_id = None
        self.pass_target = None
        self.pass_follow_until = -1

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
        protecting_late_result = (
            obs.time_remaining <= 0.10
            and obs.score[0] >= obs.score[1]
        )

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

        def ball_distance_squared(player):
            dx = player.position[0] - obs.ball.position[0]
            dy = player.position[1] - obs.ball.position[1]
            return dx * dx + dy * dy

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

                if ball_is_heading_wide:
                    # It is already missing the goal. Touching it could
                    # redirect a harmless ball between the posts.
                    actions.set(player.id, PlayerAction.noop())
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

                # Follow the ball vertically.
                # Prevent leaving the goal mouth.
                keeper_y = max(
                    -keeper_limt,
                    min(
                        obs.ball.position[1],
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

                        for opponent in obs.opponents:
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

                    shooting_distance = 25.0
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

                    shot_target = max(shot_targets, key=shot_lane_clearance)
                    best_shot_clearance_squared = shot_lane_clearance(
                        shot_target
                    )[1]
                    shot_lane_is_clear = (
                        best_shot_clearance_squared >= 1.0 ** 2
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

                        def pass_score(teammate):
                            nearest_opponent_distance_squared = min(
                                (
                                    (teammate.position[0] - opponent.position[0]) ** 2
                                    + (teammate.position[1] - opponent.position[1]) ** 2
                                )
                                for opponent in obs.opponents
                            )

                            forward_progress = (
                                teammate.position[0]
                                - player.position[0]
                            )
                            pass_distance_squared = (
                                (teammate.position[0] - player.position[0]) ** 2
                                + (teammate.position[1] - player.position[1]) ** 2
                            )

                            if rear_pressure_count >= 3:
                                return (
                                    2.0 * nearest_opponent_distance_squared
                                    + 3.0 * forward_progress
                                    - 0.15 * pass_distance_squared
                                )

                            return (
                                nearest_opponent_distance_squared
                                + 6.0 * forward_progress
                                - 0.25 * pass_distance_squared
                            )

                        receiver = max(
                            teammates,
                            key=pass_score,
                        )
                        receiver_space_squared = min(
                            (
                                (receiver.position[0] - opponent.position[0]) ** 2
                                + (receiver.position[1] - opponent.position[1]) ** 2
                            )
                            for opponent in obs.opponents
                        )

                        in_final_third = (
                            player.position[0]
                            >= obs.opponent_goal[0] - 30.0
                        )
                        required_receiver_space = (
                            4.5 if in_final_third else 6.0
                        )
                        receiver_is_open = (
                            receiver_space_squared
                            >= required_receiver_space ** 2
                        )
                        receiver_is_within_range = (
                            (receiver.position[0] - player.position[0]) ** 2
                            + (receiver.position[1] - player.position[1]) ** 2
                            <= 22.0 ** 2
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
                        # Check whether an opponent blocks the passing lane.
                        pass_dx = receiver.position[0] - player.position[0]
                        pass_dy = receiver.position[1] - player.position[1]

                        pass_length_squared = (
                            pass_dx * pass_dx
                            + pass_dy * pass_dy
                        )

                        pass_lane_is_clear = True

                        for opponent in obs.opponents:
                            opponent_dx = (
                                opponent.position[0]
                                - player.position[0]
                            )
                            opponent_dy = (
                                opponent.position[1]
                                - player.position[1]
                            )

                            # Position of the opponent along the pass:
                            # 0 = passer, 1 = receiver.
                            t = (
                                opponent_dx * pass_dx
                                + opponent_dy * pass_dy
                            ) / pass_length_squared

                            if 0.0 < t < 1.0:
                                closest_x = (
                                    player.position[0]
                                    + t * pass_dx
                                )
                                closest_y = (
                                    player.position[1]
                                    + t * pass_dy
                                )

                                distance_from_lane_squared = (
                                    (opponent.position[0] - closest_x) ** 2
                                    + (opponent.position[1] - closest_y) ** 2
                                )

                                required_lane_clearance = (
                                    2.25 if in_final_third else 3.0
                                )

                                if (
                                    distance_from_lane_squared
                                    < required_lane_clearance ** 2
                                ):
                                    pass_lane_is_clear = False
                                    break

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

                        if (
                            (
                                receiver_is_forward
                                or receiver_is_safe_escape
                                or receiver_is_recycle_option
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
                            elif receiver_is_safe_escape:
                                pass_lead = 2.0
                            elif receiver_is_recycle_option:
                                pass_lead = 1.0
                            else:
                                pass_lead = 4.0

                            kick_target = (
                                min(
                                    receiver.position[0] + pass_lead,
                                    obs.opponent_goal[0] - 2.0,
                                ),
                                receiver.position[1],
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
                            lane_y_values = (
                                -18.0, -12.0, -6.0, 0.0, 6.0, 12.0, 18.0
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
                            if obs.ball.position[0] >= 0.0:
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
                    if ball_y < 0:
                        attacking_midfielder_id = 1
                    else:
                        attacking_midfielder_id = 2

                if player.id == rebound_supporter_id:
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

                elif player.id == 1:
                    # Left defender: remain behind the ball.
                    target_x = min(ball_x - 12.0, -5.0)
                    target_y = -12.0

                elif player.id == 2:
                    # Right defender: remain behind the ball.
                    target_x = min(ball_x - 12.0, -5.0)
                    target_y = 12.0

                elif player.id == 3:
                    # Left attacker: move ahead of the ball.
                    target_x = min(
                        ball_x + 10.0,
                        obs.field.opponent_goal[0] - 5.0,
                    )
                    target_y = -10.0

                else:
                    # Player 4 — right attacker.
                    target_x = min(
                        ball_x + 10.0,
                        obs.field.opponent_goal[0] - 5.0,
                    )
                    target_y = 10.0

                support_target = (target_x, target_y)

                actions.move(
                    player.id,
                    direction(player.position, support_target),
                )

            elif nearest:
                # Theirs, and I am the closest: go and win it back.
                actions.move(player.id, direction(player.position, obs.ball.position))

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

                elif player.id == 1:
                    # Left defender.
                    target_x = max(
                        goal_x + 8.0,
                        min(ball_x - 8.0, -20.0),
                    )
                    target_y = (ball_y - 12.0) / 2

                elif player.id == 2:
                    # Right defender.
                    target_x = max(
                        goal_x + 8.0,
                        min(ball_x - 8.0, -20.0),
                    )
                    target_y = (ball_y + 12.0) / 2

                elif player.id == 3:
                    # Left attacker drops into midfield.
                    target_x = max(
                        -18.0,
                        min(ball_x - 4.0, 0.0),
                    )
                    target_y = -10.0

                else:
                    # Player 4 — right attacker drops into midfield.
                    target_x = max(
                        -18.0,
                        min(ball_x - 4.0, 0.0),
                    )
                    target_y = 10.0

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
