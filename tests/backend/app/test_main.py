import asyncio
from unittest.mock import MagicMock

import app.main as main_module


def test_check_and_advance_turns_advances_games_with_state(monkeypatch):
    game = MagicMock(id=1)
    game_state = MagicMock()
    advance = MagicMock()

    session = MagicMock()
    session.query.return_value.join.return_value.filter.return_value.all.return_value = [game]
    session.query.return_value.filter_by.return_value.first.return_value = game_state

    sessionmaker = MagicMock(return_value=session)
    monkeypatch.setattr(main_module, "get_sessionmaker", lambda: sessionmaker)
    monkeypatch.setattr("app.routes.games.advance_if_expired", advance)

    main_module.check_and_advance_turns()

    advance.assert_called_once_with(game, game_state, session)
    session.close.assert_called_once()


def test_check_and_advance_turns_skips_missing_game_state(monkeypatch):
    game = MagicMock(id=2)
    advance = MagicMock()

    session = MagicMock()
    session.query.return_value.join.return_value.filter.return_value.all.return_value = [game]
    session.query.return_value.filter_by.return_value.first.return_value = None

    sessionmaker = MagicMock(return_value=session)
    monkeypatch.setattr(main_module, "get_sessionmaker", lambda: sessionmaker)
    monkeypatch.setattr("app.routes.games.advance_if_expired", advance)

    main_module.check_and_advance_turns()
    advance.assert_not_called()
    session.close.assert_called_once()


def test_check_and_advance_turns_swallows_inner_errors(monkeypatch):
    game = MagicMock(id=3)
    game_state = MagicMock()

    session = MagicMock()
    session.query.return_value.join.return_value.filter.return_value.all.return_value = [game]
    session.query.return_value.filter_by.return_value.first.return_value = game_state

    sessionmaker = MagicMock(return_value=session)
    monkeypatch.setattr(main_module, "get_sessionmaker", lambda: sessionmaker)
    monkeypatch.setattr(
        "app.routes.games.advance_if_expired",
        MagicMock(side_effect=RuntimeError("boom")),
    )

    main_module.check_and_advance_turns()
    session.close.assert_called_once()


def test_check_and_advance_turns_swallows_sessionmaker_errors(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_sessionmaker",
        MagicMock(side_effect=RuntimeError("no db")),
    )
    main_module.check_and_advance_turns()


def test_lifespan_handles_scheduler_start_failure(monkeypatch):
    monkeypatch.setattr(main_module, "acquire_background_leader_lock", lambda: True)
    monkeypatch.setattr(
        main_module.scheduler,
        "add_job",
        MagicMock(side_effect=RuntimeError("start failed")),
    )
    monkeypatch.setattr(main_module, "run_startup_tasks", MagicMock())
    monkeypatch.setattr(main_module.scheduler, "shutdown", MagicMock())

    async def _run():
        async with main_module.lifespan(MagicMock()):
            pass

    asyncio.run(_run())


def test_lifespan_handles_scheduler_shutdown_failure(monkeypatch):
    monkeypatch.setattr(main_module, "acquire_background_leader_lock", lambda: True)
    monkeypatch.setattr(main_module.scheduler, "add_job", MagicMock())
    monkeypatch.setattr(main_module.scheduler, "start", MagicMock())
    monkeypatch.setattr(main_module, "run_startup_tasks", MagicMock())
    monkeypatch.setattr(
        main_module.scheduler,
        "shutdown",
        MagicMock(side_effect=RuntimeError("shutdown failed")),
    )

    async def _run():
        async with main_module.lifespan(MagicMock()):
            pass

    asyncio.run(_run())


def test_lifespan_follower_worker_skips_scheduler(monkeypatch):
    startup = MagicMock()
    add_job = MagicMock()
    monkeypatch.setattr(main_module, "acquire_background_leader_lock", lambda: False)
    monkeypatch.setattr(main_module, "run_startup_tasks", startup)
    monkeypatch.setattr(main_module.scheduler, "add_job", add_job)
    monkeypatch.setattr(main_module.scheduler, "start", MagicMock())
    monkeypatch.setattr(main_module.scheduler, "shutdown", MagicMock())

    async def _run():
        async with main_module.lifespan(MagicMock()):
            pass

    asyncio.run(_run())
    startup.assert_not_called()
    add_job.assert_not_called()


def test_expire_pending_invitations_runs(monkeypatch):
    session = MagicMock()
    sessionmaker = MagicMock(return_value=session)
    expire = MagicMock()
    monkeypatch.setattr(main_module, "get_sessionmaker", lambda: sessionmaker)
    monkeypatch.setattr("app.routes.invitations.expire_due_invitations", expire)

    main_module.expire_pending_invitations()

    expire.assert_called_once_with(session)
    session.close.assert_called_once()


def test_expire_pending_invitations_swallows_inner_errors(monkeypatch):
    session = MagicMock()
    sessionmaker = MagicMock(return_value=session)
    monkeypatch.setattr(main_module, "get_sessionmaker", lambda: sessionmaker)
    monkeypatch.setattr(
        "app.routes.invitations.expire_due_invitations",
        MagicMock(side_effect=RuntimeError("boom")),
    )

    main_module.expire_pending_invitations()
    session.close.assert_called_once()


def test_expire_pending_invitations_swallows_sessionmaker_errors(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_sessionmaker",
        MagicMock(side_effect=RuntimeError("no db")),
    )
    main_module.expire_pending_invitations()
