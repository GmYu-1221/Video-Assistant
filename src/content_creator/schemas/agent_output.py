from pydantic import BaseModel, Field

class ImageAnalysis(BaseModel):
    image_id: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    aspect_ratio: float = Field(gt=0)
    dominant_color: dict[str, int]
    information_density: float = Field(ge=0, le=1)
    recommended_duration: int = Field(gt=0)

class RemotionAdvice(BaseModel):
    component: str = "Slideshow"
    image_fit: str = "contain"
    motion_default: str = "static"
    transition_registry_required: bool = True
    allowed_animation_apis: tuple[str, ...] = ("interpolate", "spring", "Easing")
    prohibited_patterns: tuple[str, ...] = ("object-fit: cover", "scaleX", "scaleY", "requestAnimationFrame", "setTimeout")
    skill_documents: tuple[str, ...]
