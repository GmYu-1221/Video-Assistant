"""Director-owned creative intent, deliberately independent of Remotion effects."""

from pydantic import AliasChoices, BaseModel, Field


class CreativeIntent(BaseModel):
    scene_id: str = Field(default="", max_length=120)
    description: str = Field(min_length=1, max_length=500, validation_alias=AliasChoices("description", "intent"))
    movement: str | None = Field(default=None, max_length=240)
    emotion: str | None = Field(default=None, max_length=120)
    timing: str | None = Field(default=None, max_length=160)
    style: str = Field(default="cinematic", max_length=80)
    energy: float = Field(default=0.5, ge=0, le=1)
    camera: str | None = Field(default=None, max_length=200)
    # Optional descriptive layers retained for richer direction, never effect IDs.
    effects: list[str] = Field(default_factory=list, max_length=12)
