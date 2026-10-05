"""Initial keypoint placement with DeepLabCut SuperAnimal-Quadruped.

The SuperAnimal skeleton does not contain most conformation landmarks, so only some
points come straight from the model; the rest are estimated from them using typical
proportions (in head lengths). The user corrects the points in the UI.
"""

import math
import threading

import numpy as np

from .geometry import Point

SUPERANIMAL = "superanimal_quadruped"
MODEL = "hrnet_w32"
DETECTOR = "fasterrcnn_resnet50_fpn_v2"

# Our keypoint -> SuperAnimal bodypart. "{side}" is the near side (left/right).
DIRECT = {
    "muzzle": "nose",
    "poll": "neck_base",  # SuperAnimal "neck_base" sits at the poll
    "throatlatch": "throat_base",
    "neck_base_low": "throat_end",
    "back_low": "back_middle",
    "tail_base": "tail_base",
    "elbow": "front_{side}_thai",
    "front_knee": "front_{side}_knee",
    "hock": "back_{side}_knee",
}

# Estimated points: base point + (forward, down) offset in head lengths.
# Forward = towards the head. Order matters: later entries may use earlier ones.
OFFSETS = {
    # SuperAnimal "back_base" sits on the neck crest just in front of the withers
    "withers": ("_back_base", (-0.3, 0.05)),
    "croup_high": ("tail_base", (0.5, -0.2)),
    "loin": ("tail_base", (0.75, -0.2)),
    "hip_point": ("tail_base", (0.75, 0.1)),
    "buttock_point": ("tail_base", (-0.05, 0.35)),
    "scapula_top": ("withers", (0.1, 0.15)),
    "girth_low": ("elbow", (-0.25, 0.12)),
}


class PoseDetector:
    def __init__(self, device: str | None = None):
        import torch
        from deeplabcut.pose_estimation_pytorch import modelzoo
        from deeplabcut.pose_estimation_pytorch.apis.utils import (
            get_detector_inference_runner,
            get_pose_inference_runner,
        )

        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        config = modelzoo.load_super_animal_config(
            super_animal=SUPERANIMAL, model_name=MODEL, detector_name=DETECTOR,
            max_individuals=1, device=device,
        )
        config["metadata"]["individuals"] = ["animal0"]
        config["detector"]["model"]["box_score_thresh"] = 0.6
        self.bodyparts: list[str] = config["metadata"]["bodyparts"]
        self._detector = get_detector_inference_runner(
            model_config=config,
            snapshot_path=modelzoo.get_super_animal_snapshot_path(dataset=SUPERANIMAL, model_name=DETECTOR),
            device=device, max_individuals=1,
        )
        self._pose = get_pose_inference_runner(
            model_config=config,
            snapshot_path=modelzoo.get_super_animal_snapshot_path(dataset=SUPERANIMAL, model_name=MODEL),
            device=device, max_individuals=1,
        )
        self._lock = threading.Lock()

    def raw(self, image: np.ndarray) -> dict[str, tuple[float, float, float]] | None:
        """SuperAnimal bodyparts (x, y, score) for an RGB image, or None if no animal."""
        with self._lock:
            bboxes = self._detector.inference([image])[0]
            if len(bboxes.get("bboxes", [])) == 0:
                return None
            pred = self._pose.inference([(image, bboxes)])[0]
        kpts = np.asarray(pred["bodyparts"])[0]
        return {name: (float(x), float(y), float(s)) for name, (x, y, s) in zip(self.bodyparts, kpts)}

    def detect(self, image: np.ndarray) -> dict[str, dict] | None:
        raw = self.raw(image)
        return None if raw is None else map_superanimal(raw)


def map_superanimal(raw: dict[str, tuple[float, float, float]]) -> dict[str, dict]:
    """Map SuperAnimal bodyparts to conformation keypoints.

    Returns {id: {"x", "y", "source": "model" | "estimated", "score"}}.
    """
    facing = 1 if raw["nose"][0] > raw["tail_base"][0] else -1
    # A horse facing left shows its left side to the camera
    side = "left" if facing < 0 else "right"
    H = math.dist(raw["nose"][:2], raw["neck_base"][:2])

    out: dict[str, dict] = {}

    def put(k: str, p: Point, source: str, score: float | None = None) -> None:
        out[k] = {"x": round(p[0], 1), "y": round(p[1], 1), "source": source, "score": score}

    def offset(base: Point, fwd: float, down: float) -> Point:
        return base[0] + facing * fwd * H, base[1] + down * H

    def lerp(a: Point, b: Point, t: float) -> Point:
        return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])

    for k, bp in DIRECT.items():
        x, y, s = raw[bp.format(side=side)]
        put(k, (x, y), "model", round(s, 2))

    pt = {k: (v["x"], v["y"]) for k, v in out.items()}
    pt["_back_base"] = raw["back_base"][:2]
    for k, (base, (fwd, down)) in OFFSETS.items():
        put(k, offset(pt[base], fwd, down), "estimated")
        pt[k] = (out[k]["x"], out[k]["y"])

    # Point of shoulder: a little down from where the neck underline meets the chest
    put("shoulder_point", lerp(pt["neck_base_low"], pt["elbow"], 0.3), "estimated")
    # Stifle: in front of the SuperAnimal hind "thigh" point
    hx, hy, _ = raw[f"back_{side}_thai"]
    put("stifle", offset((hx, hy), 0.15, -0.05), "estimated")

    for leg, top, hoof in (("front", pt["front_knee"], f"front_{side}_paw"), ("hind", pt["hock"], f"back_{side}_paw")):
        px, py, s = raw[hoof]
        put(f"{leg}_fetlock", lerp(top, (px, py), 0.75), "estimated")
        put(f"{leg}_coronet", offset((px, py), 0.08, -0.02), "estimated")
        put(f"{leg}_toe", offset((px, py), 0.16, 0.08), "estimated")

    return out
