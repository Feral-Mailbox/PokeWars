from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import (
    ChatInfraction,
    InfractionSeverity,
    InfractionStatus,
)
from app.moderation.filter import FilterResult, filter_message


def apply_chat_moderation(
    db: Session,
    *,
    user_id: int,
    game_id: int,
    message: str,
    wordlist_path: str | None = None,
) -> tuple[str, ChatInfraction | None]:
    result: FilterResult = filter_message(message, wordlist_path=wordlist_path)
    if not result.had_match:
        return message, None

    infraction = ChatInfraction(
        user_id=user_id,
        game_id=game_id,
        original_message=message,
        censored_message=result.censored_message,
        matched_terms=result.matched_terms,
        severity=InfractionSeverity.slur,
        status=InfractionStatus.pending_review,
        created_at=datetime.now(timezone.utc),
    )
    db.add(infraction)
    db.flush()
    return result.censored_message, infraction
