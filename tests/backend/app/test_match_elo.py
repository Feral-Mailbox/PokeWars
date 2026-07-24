from tests.backend.conftest import make_test_map
import app.db.models as models
from app.routes.games import settle_match_elo


def _make_completed_match(
    db,
    *,
    gamemode,
    elos,
    elimination_order,
    winner_index=0,
    link="elo-match",
):
    users = []
    for i, elo in enumerate(elos):
        user = models.User(
            username=f"p{i}-{link}",
            email=f"p{i}-{link}@example.com",
            hashed_password="x",
            elo_conquest=elo,
            elo_war=elo,
        )
        users.append(user)
    db.add_all(users)
    db.commit()

    host = users[0]
    game_map = make_test_map(db, name=f"Map {link}", creator_id=host.id)
    game = models.Game(
        game_name=f"Match {link}",
        map_id=game_map.id,
        map_name=f"Map {link}",
        host_id=host.id,
        link=link,
        max_players=len(elos),
        turn_seconds=60,
        gamemode=gamemode,
    )
    db.add(game)
    db.commit()

    winner = users[winner_index]
    state = models.GameState(
        game_id=game.id,
        current_turn=8,
        status=models.GameStatus.completed,
        players=[u.id for u in users],
        winner_id=winner.id,
        elimination_order=[users[i].id for i in elimination_order],
        elo_applied=False,
        replay_log=[],
    )
    db.add(state)
    for user in users:
        db.add(models.GamePlayer(game_id=game.id, player_id=user.id, cash_remaining=0))
    db.commit()
    return game, state, users


def test_settle_match_elo_updates_conquest_and_is_idempotent(db, monkeypatch):
    published = []
    monkeypatch.setattr(
        "app.routes.games.publish_game_ws_event",
        lambda link, payload: published.append(payload),
    )
    game, state, users = _make_completed_match(
        db,
        gamemode=models.GameMode.conquest,
        elos=[1000, 1000],
        elimination_order=[1],
        link="elo-conquest-2p",
    )
    host, rival = users

    settle_match_elo(game, state, db)
    db.commit()
    db.refresh(host)
    db.refresh(rival)
    db.refresh(state)

    assert state.elo_applied is True
    assert host.elo_conquest > 1000
    assert rival.elo_conquest < 1000
    # War ladder untouched
    assert host.elo_war == 1000
    assert rival.elo_war == 1000
    assert any(p.get("message") == "Conquest Elo updates" for p in published)

    host_c = host.elo_conquest
    rival_c = rival.elo_conquest
    settle_match_elo(game, state, db)
    db.commit()
    db.refresh(host)
    db.refresh(rival)
    assert host.elo_conquest == host_c
    assert rival.elo_conquest == rival_c


def test_settle_match_elo_updates_war_ladder_only(db, monkeypatch):
    monkeypatch.setattr("app.routes.games.publish_game_ws_event", lambda *a, **k: None)
    game, state, users = _make_completed_match(
        db,
        gamemode=models.GameMode.war,
        elos=[1000, 1000],
        elimination_order=[1],
        link="elo-war-2p",
    )
    host, rival = users
    settle_match_elo(game, state, db)
    db.commit()
    db.refresh(host)
    db.refresh(rival)

    assert host.elo_war > 1000
    assert rival.elo_war < 1000
    assert host.elo_conquest == 1000
    assert rival.elo_conquest == 1000


def test_settle_four_equal_players_third_loses_less_than_fourth(db, monkeypatch):
    monkeypatch.setattr("app.routes.games.publish_game_ws_event", lambda *a, **k: None)
    game, state, users = _make_completed_match(
        db,
        gamemode=models.GameMode.conquest,
        elos=[1000, 1000, 1000, 1000],
        elimination_order=[3, 2, 1],
        link="elo-ffa-4",
    )
    settle_match_elo(game, state, db)
    db.commit()
    for user in users:
        db.refresh(user)

    assert users[2].elo_conquest > users[3].elo_conquest
    assert users[1].elo_conquest > users[2].elo_conquest
    assert users[0].elo_conquest > users[1].elo_conquest
    assert users[2].elo_conquest == 1000 - 12
    assert users[3].elo_conquest == 1000 - 36
    assert all(u.elo_war == 1000 for u in users)
