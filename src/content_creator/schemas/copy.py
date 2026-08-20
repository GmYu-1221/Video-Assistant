from pydantic import BaseModel, Field, field_validator


class VideoCopy(BaseModel):
    """Compact localized copy retained for the mature article analysis tools."""
    headline: str = Field(default="", max_length=80)
    subtitle: str = Field(default="", max_length=40)
    body: str = Field(default="", max_length=400)

    @field_validator("headline", "subtitle", "body")
    @classmethod
    def validate_line_count(cls, value: str, info) -> str:
        limits = {"headline": 2, "subtitle": 2, "body": 8}
        if len(value.splitlines() or [value]) > limits[info.field_name]:
            raise ValueError(f"{info.field_name} exceeds {limits[info.field_name]} lines")
        return value
