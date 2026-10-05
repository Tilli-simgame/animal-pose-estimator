"""Web app: upload a side-view photo, adjust keypoints, get a conformation report.

    uv run uvicorn horse_conformation.app:app --port 8000

Every page and API except login requires a signed-in user (see auth.py).
Set COOKIE_SECURE=1 when serving over HTTPS.
"""

import io
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import numpy as np
from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pydantic import BaseModel, Field, ValidationError

from . import auth, dataset
from .keypoints import KEYPOINT_IDS, KEYPOINTS, SKELETON
from .rules import evaluate

STATIC = Path(__file__).parent / "static"
MAX_SIDE = 2000  # downscale large photos; keypoint accuracy does not need more
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def detector():
    from .detect import PoseDetector  # heavy import, load on first use

    return PoseDetector()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        detector()
    except Exception:  # The UI still works with manual placement
        log.exception("Pose model could not be loaded")
    yield


app = FastAPI(title="Hevosen rakenneanalyysi", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def no_stale_frontend(request, call_next):
    # Make browsers revalidate the UI files so code changes show up on reload
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---------------------------------------------------------------- auth


def optional_user(request: Request) -> auth.User | None:
    return auth.user_for_token(request.cookies.get(auth.SESSION_COOKIE))


def current_user(user: Annotated[auth.User | None, Depends(optional_user)]) -> auth.User:
    if user is None:
        raise HTTPException(401, "Kirjaudu sisään.")
    return user


def admin_user(user: Annotated[auth.User, Depends(current_user)]) -> auth.User:
    if not user.is_admin:
        raise HTTPException(403, "Vain ylläpitäjille.")
    return user


CurrentUser = Annotated[auth.User, Depends(current_user)]
AdminUser = Annotated[auth.User, Depends(admin_user)]


class LoginRequest(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


@app.post("/api/login")
def login(req: LoginRequest, response: Response) -> dict:
    try:
        token = auth.login(req.username, req.password)
    except auth.AuthError as e:
        raise HTTPException(401, str(e))
    response.set_cookie(
        auth.SESSION_COOKIE, token, max_age=auth.SESSION_DAYS * 24 * 3600,
        httponly=True, samesite="lax", secure=COOKIE_SECURE,
    )
    return {"user": auth.user_for_token(token).public()}


@app.post("/api/logout")
def logout(request: Request, response: Response) -> dict:
    auth.logout(request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(auth.SESSION_COOKIE)
    return {}


@app.get("/api/me")
def me(user: CurrentUser) -> dict:
    return {"user": user.public()}


class PasswordChange(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(max_length=200)


@app.post("/api/me/password")
def change_password(req: PasswordChange, request: Request, user: CurrentUser) -> dict:
    try:
        auth.change_own_password(user, req.current, req.new, request.cookies.get(auth.SESSION_COOKIE))
    except auth.AuthError as e:
        raise HTTPException(422, str(e))
    return {}


class NewUser(BaseModel):
    username: str = Field(max_length=50)
    display_name: str = Field("", max_length=100)
    role: auth.Role = auth.Role.JUDGE
    password: str = Field(max_length=200)


class UserChange(BaseModel):
    display_name: str | None = Field(None, max_length=100)
    role: auth.Role | None = None
    active: bool | None = None
    password: str | None = Field(None, max_length=200)


@app.get("/api/users")
def users(_: AdminUser) -> dict:
    return {"users": [u.public() for u in auth.list_users()]}


@app.post("/api/users")
def create_user(req: NewUser, _: AdminUser) -> dict:
    try:
        user = auth.create_user(req.username, req.password, req.role, req.display_name)
    except auth.AuthError as e:
        raise HTTPException(422, str(e))
    return {"user": user.public()}


@app.patch("/api/users/{user_id}")
def change_user(user_id: int, req: UserChange, admin: AdminUser) -> dict:
    try:
        user = auth.update_user(admin, user_id, **req.model_dump(exclude_none=True))
    except auth.AuthError as e:
        raise HTTPException(422, str(e))
    return {"user": user.public()}


# ---------------------------------------------------------------- pages


@app.get("/")
def index(user: Annotated[auth.User | None, Depends(optional_user)]):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC / "index.html")


@app.get("/login")
def login_page(user: Annotated[auth.User | None, Depends(optional_user)]):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return FileResponse(STATIC / "login.html")


@app.get("/users")
def users_page(user: Annotated[auth.User | None, Depends(optional_user)]):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not user.is_admin:
        return RedirectResponse("/", status_code=303)
    return FileResponse(STATIC / "users.html")


# ---------------------------------------------------------------- analysis


@app.get("/api/schema")
def schema(_: CurrentUser) -> dict:
    return {"keypoints": [asdict(k) for k in KEYPOINTS], "skeleton": SKELETON}


@app.post("/api/detect")
async def detect(file: UploadFile, _: CurrentUser) -> dict:
    try:
        image = Image.open(io.BytesIO(await file.read()))
        image = ImageOps.exif_transpose(image).convert("RGB")
    except Exception:
        raise HTTPException(400, "Tiedosto ei ole kuva.")
    scale = min(1.0, MAX_SIDE / max(image.size))
    if scale < 1:
        image = image.resize((round(image.width * scale), round(image.height * scale)))

    keypoints = detector().detect(np.asarray(image))
    if keypoints is None:
        raise HTTPException(422, "Kuvasta ei löytynyt hevosta.")
    for kp in keypoints.values():
        kp["x"] = round(kp["x"] / scale, 1)
        kp["y"] = round(kp["y"] / scale, 1)
    return {"keypoints": keypoints}


class AnalyzeRequest(BaseModel):
    keypoints: dict[str, tuple[float, float]]


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest, _: CurrentUser) -> dict:
    missing = [k for k in KEYPOINT_IDS if k not in req.keypoints]
    if missing:
        raise HTTPException(422, f"Puuttuvat pisteet: {', '.join(missing)}")
    try:
        result = evaluate(req.keypoints)
    except (ZeroDivisionError, ValueError):
        raise HTTPException(422, "Pisteet ovat päällekkäin – siirrä pisteet omille paikoilleen.")
    return {"findings": [asdict(f) for f in result["findings"]], "warnings": result["warnings"]}


# ---------------------------------------------------------------- dataset


def _findings(sample: dataset.SampleIn) -> list[dict]:
    try:
        result = evaluate({k: (p.x, p.y) for k, p in sample.keypoints.items()})
    except (KeyError, ZeroDivisionError, ValueError):
        return []
    return [{"id": f.id, "value": f.value, "unit": f.unit, "status": f.status} for f in result["findings"]]


def _check_keypoints(sample: dataset.SampleIn) -> None:
    missing = [k for k in KEYPOINT_IDS if k not in sample.keypoints]
    if missing:
        raise HTTPException(422, f"Puuttuvat pisteet: {', '.join(missing)}")


@app.get("/api/samples/count")
def sample_count(_: CurrentUser) -> dict:
    return {"count": dataset.count()}


@app.post("/api/samples")
async def create_sample(user: CurrentUser, file: UploadFile, data: str = Form(...)) -> dict:
    try:
        sample = dataset.SampleIn.model_validate_json(data)
    except ValidationError as e:
        raise HTTPException(422, str(e))
    _check_keypoints(sample)
    try:
        stored = dataset.save_new(await file.read(), sample, _findings(sample), user)
    except OSError:
        raise HTTPException(400, "Kuvaa ei voitu tallentaa.")
    return {"id": stored.id, "count": dataset.count()}


@app.put("/api/samples/{sample_id}")
def update_sample(sample_id: str, sample: dataset.SampleIn, user: CurrentUser) -> dict:
    _check_keypoints(sample)
    try:
        stored = dataset.update(sample_id, sample, _findings(sample), user)
    except PermissionError:
        raise HTTPException(403, "Voit muokata vain omia tallennuksiasi.")
    if stored is None:
        raise HTTPException(404, "Tallennettua hevosta ei löytynyt.")
    return {"id": stored.id, "count": dataset.count()}
