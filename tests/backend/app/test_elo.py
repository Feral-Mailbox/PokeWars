from types import SimpleNamespace

from app.elo import (
    apply_floor,
    build_placements,
    compute_elo_deltas,
    elo_attr_for_gamemode,
    elo_label_for_gamemode,
    expected_score,
)


def test_elo_attr_for_gamemode():
    assert elo_attr_for_gamemode("War") == "elo_war"
    assert elo_attr_for_gamemode("Conquest") == "elo_conquest"
    assert elo_attr_for_gamemode("Capture The Flag") == "elo_conquest"
    assert elo_attr_for_gamemode("Unknown Mode") == "elo_conquest"
    assert elo_attr_for_gamemode(SimpleNamespace(value="War")) == "elo_war"


def test_elo_label_for_gamemode():
    assert elo_label_for_gamemode("War") == "War Elo"
    assert elo_label_for_gamemode("Capture The Flag") == "Conquest Elo"
    assert elo_label_for_gamemode("Conquest") == "Conquest Elo"
    assert elo_label_for_gamemode(SimpleNamespace(value="War")) == "War Elo"


def test_expected_score_symmetric_equal_ratings():
    assert expected_score(1000, 1000) == 0.5


def test_build_placements_winner_and_elimination_order():
    places = build_placements(
        [1, 2, 3, 4],
        elimination_order=[4, 2],  # 4 out first (worst), then 2
        winner_id=1,
    )
    # Winner, then any non-eliminated leftovers, then reverse elimination.
    assert places == {1: 1, 3: 2, 2: 3, 4: 4}


def test_build_placements_draw_share_first():
    places = build_placements(
        [10, 20, 30],
        elimination_order=[30],
        winner_id=None,
        draw_ids=[10, 20],
    )
    assert places[10] == 1
    assert places[20] == 1
    assert places[30] == 2


def test_compute_elo_deltas_winner_gains_against_field():
    ratings = {1: 1000, 2: 1000, 3: 1000}
    places = {1: 1, 2: 2, 3: 3}
    deltas = compute_elo_deltas(ratings, places)
    assert deltas[1] > 0
    assert deltas[3] < 0
    # Rough zero-sum after rounding
    assert abs(sum(deltas.values())) <= 1


def test_equal_ratings_better_place_always_gets_better_delta():
    """Same-Elo FFA: each better finish must gain more / lose less than worse finishes."""
    for n in (3, 4, 5, 6, 8):
        ratings = {i: 1000 for i in range(1, n + 1)}
        places = {i: i for i in range(1, n + 1)}
        deltas = compute_elo_deltas(ratings, places)
        ordered = [deltas[i] for i in range(1, n + 1)]
        assert ordered == sorted(ordered, reverse=True), (n, deltas)
        # Adjacent places must differ (strict), including 3rd vs 4th in 4+ lobbies.
        for i in range(1, n):
            assert deltas[i] > deltas[i + 1], (n, i, deltas)


def test_four_player_equal_elo_third_beats_fourth():
    deltas = compute_elo_deltas(
        {1: 1000, 2: 1000, 3: 1000, 4: 1000},
        {1: 1, 2: 2, 3: 3, 4: 4},
    )
    assert deltas[3] > deltas[4]
    assert deltas[3] == -12
    assert deltas[4] == -36


def test_apply_floor():
    assert apply_floor(105, -20) == 100
    assert apply_floor(1200, 16) == 1216


def test_build_placements_empty_roster():
    assert build_placements([]) == {}


def test_build_placements_winner_appends_player_missing_from_ordered():
    # Winner path places remaining roster members after the winner.
    places = build_placements(
        [1, 2],
        elimination_order=[],
        winner_id=1,
    )
    assert places == {1: 1, 2: 2}

def test_build_placements_winner_with_straggler_not_in_elim():
    places = build_placements(
        [1, 2, 3],
        elimination_order=[3],
        winner_id=1,
    )
    assert places[1] == 1
    assert places[2] == 2
    assert places[3] == 3


def test_build_placements_no_winner_reverse_elim():
    places = build_placements(
        [1, 2, 3],
        elimination_order=[3, 2],
        winner_id=None,
    )
    # reverse elim: 2 then 3, then leftover 1
    assert places == {2: 1, 3: 2, 1: 3}


def test_build_placements_draw_adds_non_elim_leftovers():
    places = build_placements(
        [1, 2, 3, 4],
        elimination_order=[4],
        winner_id=None,
        draw_ids=[1, 2],
    )
    assert places[1] == 1
    assert places[2] == 1
    assert places[4] == 2
    assert places[3] == 3


def test_build_placements_ignores_unknown_elim_and_duplicate():
    places = build_placements(
        [1, 2],
        elimination_order=[99, 2, 2],
        winner_id=1,
    )
    assert places == {1: 1, 2: 2}


def test_compute_elo_deltas_needs_two_players():
    assert compute_elo_deltas({1: 1000}, {1: 1}) == {1: 0}
    assert compute_elo_deltas({1: 1000, 2: 1000}, {1: 1}) == {1: 0, 2: 0}


def test_compute_elo_deltas_tied_places():
    deltas = compute_elo_deltas(
        {1: 1000, 2: 1000},
        {1: 1, 2: 1},
    )
    assert deltas[1] == 0
    assert deltas[2] == 0
