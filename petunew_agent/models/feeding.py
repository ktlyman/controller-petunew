"""Feeding models for PetUNew feeders."""

from __future__ import annotations

from datetime import datetime, time
from enum import Enum
from pydantic import BaseModel, Field


class MealName(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    CUSTOM = "custom"


class FeedSchedule(BaseModel):
    """A scheduled feeding entry."""

    schedule_id: str | None = None
    label: str = ""
    meal_time: time
    portions: int = Field(ge=1, le=10, default=1)
    enabled: bool = True
    repeat_days: list[int] = Field(
        default_factory=lambda: [0, 1, 2, 3, 4, 5, 6],
        description="Days of week (0=Monday, 6=Sunday)",
    )

    def describe(self) -> str:
        time_str = self.meal_time.strftime("%I:%M %p")
        unit = "portion" if self.portions == 1 else "portions"
        state = "enabled" if self.enabled else "disabled"
        return f"{self.label or 'Unnamed'}: {time_str}, {self.portions} {unit} ({state})"


class FeedingRecord(BaseModel):
    """A historical feeding event."""

    record_id: str | None = None
    device_id: str
    timestamp: datetime
    portions: int
    source: str = "unknown"  # "schedule", "manual", "agent"
    schedule_label: str | None = None
    success: bool = True
    error_message: str | None = None


class ManualFeedRequest(BaseModel):
    """Request to dispense food immediately."""

    device_id: str
    portions: int = Field(ge=1, le=10, default=1)
    source: str = "agent"
