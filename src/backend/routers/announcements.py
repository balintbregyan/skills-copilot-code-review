"""Announcement endpoints for public display and authenticated management."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(prefix="/announcements", tags=["announcements"])


class AnnouncementPayload(BaseModel):
    """Body for create/update announcement operations."""

    message: str = Field(min_length=1, max_length=500)
    expires_at: str
    starts_at: Optional[str] = None



def _parse_iso_datetime(value: str, field_name: str) -> datetime:
    """Parse ISO datetime string and normalize to UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be a valid ISO datetime"
        ) from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)



def _require_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(
            status_code=401,
            detail="Authentication required for this action"
        )

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher



def _serialize_announcement(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": raw["_id"],
        "message": raw["message"],
        "starts_at": raw.get("starts_at"),
        "expires_at": raw["expires_at"],
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
    }


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Return currently active announcements for public display."""
    now_iso = datetime.now(timezone.utc).isoformat()

    query = {
        "expires_at": {"$gte": now_iso},
        "$or": [
            {"starts_at": None},
            {"starts_at": {"$exists": False}},
            {"starts_at": {"$lte": now_iso}},
        ],
    }

    items = announcements_collection.find(query).sort("expires_at", 1)
    return [_serialize_announcement(item) for item in items]


@router.get("/manage", response_model=List[Dict[str, Any]])
def list_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """List all announcements, including expired, for authenticated users."""
    _require_teacher(teacher_username)
    items = announcements_collection.find({}).sort("expires_at", 1)
    return [_serialize_announcement(item) for item in items]


@router.post("/manage", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Create a new announcement."""
    _require_teacher(teacher_username)

    starts_at_dt = (
        _parse_iso_datetime(payload.starts_at, "starts_at")
        if payload.starts_at
        else None
    )
    expires_at_dt = _parse_iso_datetime(payload.expires_at, "expires_at")

    if starts_at_dt and starts_at_dt > expires_at_dt:
        raise HTTPException(
            status_code=400,
            detail="starts_at cannot be later than expires_at"
        )

    announcement = {
        "_id": str(uuid4()),
        "message": payload.message.strip(),
        "starts_at": starts_at_dt.isoformat() if starts_at_dt else None,
        "expires_at": expires_at_dt.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    announcements_collection.insert_one(announcement)
    return _serialize_announcement(announcement)


@router.put("/manage/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Update an existing announcement."""
    _require_teacher(teacher_username)

    starts_at_dt = (
        _parse_iso_datetime(payload.starts_at, "starts_at")
        if payload.starts_at
        else None
    )
    expires_at_dt = _parse_iso_datetime(payload.expires_at, "expires_at")

    if starts_at_dt and starts_at_dt > expires_at_dt:
        raise HTTPException(
            status_code=400,
            detail="starts_at cannot be later than expires_at"
        )

    update_doc = {
        "message": payload.message.strip(),
        "starts_at": starts_at_dt.isoformat() if starts_at_dt else None,
        "expires_at": expires_at_dt.isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    result = announcements_collection.update_one(
        {"_id": announcement_id},
        {"$set": update_doc}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": announcement_id})
    return _serialize_announcement(updated)


@router.delete("/manage/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, str]:
    """Delete an announcement."""
    _require_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
