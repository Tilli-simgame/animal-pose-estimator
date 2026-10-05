"""Spike: run DeepLabCut SuperAnimal-Quadruped zero-shot on sample horse photos.

Saves labeled images and a JSON of named keypoints per image to spike/out/.

    uv run python spike/run_superanimal.py [image_dir]
"""

import json
import sys
from pathlib import Path

import numpy as np
from deeplabcut.pose_estimation_pytorch import modelzoo
from deeplabcut.pose_estimation_pytorch.apis import superanimal_analyze_images

SUPERANIMAL = "superanimal_quadruped"
MODEL = "hrnet_w32"
DETECTOR = "fasterrcnn_resnet50_fpn_v2"

ROOT = Path(__file__).resolve().parent
IMAGES = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "samples"
OUT = ROOT / "out"


def main() -> None:
    images = sorted(str(p) for p in IMAGES.glob("*.jpg"))
    predictions = superanimal_analyze_images(
        superanimal_name=SUPERANIMAL,
        model_name=MODEL,
        detector_name=DETECTOR,
        images=images,
        max_individuals=1,
        out_folder=OUT,
        device="cuda",
        pose_threshold=0.3,
    )

    config = modelzoo.load_super_animal_config(SUPERANIMAL, MODEL, DETECTOR)
    bodyparts = config["metadata"]["bodyparts"]

    results = {}
    for image, pred in predictions.items():
        kpts = np.asarray(pred["bodyparts"])[0]  # first (only) individual: (n_kpts, 3)
        results[Path(image).name] = {
            name: {"x": float(x), "y": float(y), "score": float(s)}
            for name, (x, y, s) in zip(bodyparts, kpts)
        }
    (OUT / "keypoints.json").write_text(json.dumps(results, indent=2))
    print(f"{len(bodyparts)} bodyparts: {bodyparts}")
    print(f"Wrote {OUT / 'keypoints.json'}")


if __name__ == "__main__":
    main()
