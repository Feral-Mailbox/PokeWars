from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import (
    StaffAnnouncement,
    StaffAnnouncementDismissal,
    StaffAnnouncementStar,
    User,
)
from app.dependencies import get_current_user, get_db, require_admin
from app.routes.ws import publish_announcement_event
from app.schemas.announcements import (
    AnnouncementResponse,
    ClearAnnouncementsResponse,
    CreateAnnouncementRequest,
)

router = APIRouter(prefix="/announcements", tags=["announcements"])


def _to_response(
    row: StaffAnnouncement,
    author: User,
    *,
    starred: bool,
) -> AnnouncementResponse:
    return AnnouncementResponse(
        id=row.id,
        title=row.title,
        message=row.message,
        author_id=author.id,
        author_username=author.username,
        created_at=row.created_at,
        starred=starred,
    )


@router.get("", response_model=list[AnnouncementResponse])
def list_announcements(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    starred_ids = {
        int(aid)
        for (aid,) in db.query(StaffAnnouncementStar.announcement_id)
        .filter(StaffAnnouncementStar.user_id == user.id)
        .all()
    }
    dismissed_ids = {
        int(aid)
        for (aid,) in db.query(StaffAnnouncementDismissal.announcement_id)
        .filter(StaffAnnouncementDismissal.user_id == user.id)
        .all()
    }

    rows = (
        db.query(StaffAnnouncement)
        .order_by(StaffAnnouncement.created_at.desc(), StaffAnnouncement.id.desc())
        .limit(100)
        .all()
    )
    out: list[AnnouncementResponse] = []
    for row in rows:
        is_starred = row.id in starred_ids
        if row.id in dismissed_ids and not is_starred:
            continue
        author = db.query(User).filter(User.id == row.author_id).first()
        if not author:
            continue
        out.append(_to_response(row, author, starred=is_starred))
        if len(out) >= 50:
            break
    return out


@router.post("", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
def create_announcement(
    req: CreateAnnouncementRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    row = StaffAnnouncement(
        title=req.title,
        message=req.message,
        author_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    response = _to_response(row, user, starred=False)
    publish_announcement_event(
        {
            "event": "announcement",
            "action": "created",
            "announcement": response.model_dump(mode="json"),
        }
    )
    return response


@router.post("/clear", response_model=ClearAnnouncementsResponse)
def clear_announcements(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    starred_ids = {
        int(aid)
        for (aid,) in db.query(StaffAnnouncementStar.announcement_id)
        .filter(StaffAnnouncementStar.user_id == user.id)
        .all()
    }
    dismissed_ids = {
        int(aid)
        for (aid,) in db.query(StaffAnnouncementDismissal.announcement_id)
        .filter(StaffAnnouncementDismissal.user_id == user.id)
        .all()
    }

    rows = db.query(StaffAnnouncement).all()
    cleared = 0
    for row in rows:
        if row.id in starred_ids or row.id in dismissed_ids:
            continue
        db.add(
            StaffAnnouncementDismissal(
                user_id=user.id,
                announcement_id=row.id,
            )
        )
        cleared += 1
    db.commit()
    return ClearAnnouncementsResponse(cleared=cleared)


@router.post("/{announcement_id}/star", response_model=AnnouncementResponse)
def star_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.query(StaffAnnouncement).filter(StaffAnnouncement.id == announcement_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Announcement not found")

    existing = (
        db.query(StaffAnnouncementStar)
        .filter_by(user_id=user.id, announcement_id=announcement_id)
        .first()
    )
    if existing is None:
        db.add(
            StaffAnnouncementStar(
                user_id=user.id,
                announcement_id=announcement_id,
            )
        )
        # Starred items should remain visible even if previously cleared.
        db.query(StaffAnnouncementDismissal).filter_by(
            user_id=user.id,
            announcement_id=announcement_id,
        ).delete()
        db.commit()

    author = db.query(User).filter(User.id == row.author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    return _to_response(row, author, starred=True)


@router.delete("/{announcement_id}/star", response_model=AnnouncementResponse)
def unstar_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.query(StaffAnnouncement).filter(StaffAnnouncement.id == announcement_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Announcement not found")

    db.query(StaffAnnouncementStar).filter_by(
        user_id=user.id,
        announcement_id=announcement_id,
    ).delete()
    db.commit()

    author = db.query(User).filter(User.id == row.author_id).first()
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    return _to_response(row, author, starred=False)
