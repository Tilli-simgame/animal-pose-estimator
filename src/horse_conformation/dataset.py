"""Training/calibration dataset: photo + corrected keypoints + horse metadata.

Layout (one pair per horse photo):
    data/images/<id>.jpg         EXIF-orientated, metadata (GPS etc.) stripped
    data/annotations/<id>.json   Sample (see below)
"""

import io
import json
import os
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageOps
from pydantic import BaseModel, Field, HttpUrl

if TYPE_CHECKING:
    from .auth import User

DATA_DIR = Path(os.environ.get("HORSE_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))


class HorseType(StrEnum):
    COLDBLOOD_LIGHT = "kylmäverinen_kevyt"
    COLDBLOOD_HEAVY = "kylmäverinen_raskas"
    WARMBLOOD = "lämminverinen"
    THOROUGHBRED = "täysiverinen"
    PONY = "poni"


class Sex(StrEnum):
    STALLION = "ori"
    MARE = "tamma"
    GELDING = "ruuna"


class Award(StrEnum):
    """Studbook (kantakirja) result, I is the best."""

    I = "I"
    II = "II"
    III = "III"


class Judging(BaseModel):
    award: Award | None = None


class Horse(BaseModel):
    breed: str | None = Field(None, max_length=100)
    type: HorseType | None = None
    sex: Sex | None = None
    age_years: float | None = Field(None, ge=0, le=45)
    # The photographed horse's result at a real show
    irl: Judging = Judging()
    # Result the same photo got at a virtual show (un-real-life)
    url: Judging = Judging()
    link: HttpUrl | None = None
    notes: str | None = Field(None, max_length=2000)


class AnnotatedPoint(BaseModel):
    x: float
    y: float
    source: str  # "model" | "estimated" | "user"


class SampleIn(BaseModel):
    horse: Horse
    keypoints: dict[str, AnnotatedPoint]
    verified: bool = False  # user confirmed that every point is in place
    original_filename: str | None = None


class Sample(SampleIn):
    id: str
    image: str
    width: int
    height: int
    created: str
    updated: str
    created_by_id: int | None = None
    created_by: str | None = None  # username at the time of saving
    findings: list[dict] = []


def _annotation_path(sample_id: str) -> Path:
    return DATA_DIR / "annotations" / f"{sample_id}.json"


def _valid_id(sample_id: str) -> bool:
    return sample_id.replace("-", "").isalnum() and _annotation_path(sample_id).exists()


def save_new(image_bytes: bytes, sample: SampleIn, findings: list[dict], user: "User") -> Sample:
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sample_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]

    (DATA_DIR / "images").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "annotations").mkdir(parents=True, exist_ok=True)
    image_name = f"{sample_id}.jpg"
    # Re-encoding without exif drops camera/GPS metadata
    image.save(DATA_DIR / "images" / image_name, quality=95)

    stored = Sample(
        **sample.model_dump(), id=sample_id, image=f"images/{image_name}",
        width=image.width, height=image.height, created=now, updated=now, findings=findings,
        created_by_id=user.id, created_by=user.username,
    )
    _write(stored)
    return stored


def update(sample_id: str, sample: SampleIn, findings: list[dict], user: "User") -> Sample | None:
    """Returns None if the sample does not exist; PermissionError if it is someone else's."""
    if not _valid_id(sample_id):
        return None
    old = Sample.model_validate_json(_annotation_path(sample_id).read_text(encoding="utf-8"))
    if old.created_by_id != user.id and not user.is_admin:
        raise PermissionError(sample_id)
    stored = Sample(**{
        **old.model_dump(),
        **sample.model_dump(exclude={"original_filename"}),
        "findings": findings,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    _write(stored)
    return stored


def count() -> int:
    folder = DATA_DIR / "annotations"
    return len(list(folder.glob("*.json"))) if folder.exists() else 0


def _write(sample: Sample) -> None:
    path = _annotation_path(sample.id)
    path.write_text(json.dumps(sample.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
