import math

import pytest

from horse_conformation.detect import map_superanimal
from horse_conformation.geometry import Frame, joint_angle_deg, slope_deg, tilt_from_vertical_deg
from horse_conformation.keypoints import KEYPOINT_IDS
from horse_conformation.rules import RULES, Range, evaluate

# A plausible horse facing left, in pixels (y down)
HORSE = {
    "muzzle": (100, 300), "poll": (300, 100), "throatlatch": (285, 300), "neck_base_low": (350, 460),
    "withers": (590, 275), "back_low": (700, 320), "loin": (850, 280), "croup_high": (915, 280),
    "tail_base": (1050, 340), "scapula_top": (610, 300), "shoulder_point": (390, 510), "elbow": (480, 620),
    "girth_low": (545, 665), "front_knee": (512, 840), "front_fetlock": (512, 990),
    "front_coronet": (470, 1045), "front_toe": (430, 1090), "hip_point": (850, 370),
    "buttock_point": (1060, 450), "stifle": (935, 560), "hock": (1065, 780), "hind_fetlock": (1050, 975),
    "hind_coronet": (1015, 1040), "hind_toe": (980, 1090),
}


def values(kp):
    return {f.id: f.value for f in evaluate(kp)["findings"]}


def test_basic_angles():
    assert slope_deg((0, 0), (10, 10)) == pytest.approx(45)
    assert joint_angle_deg((0, 1), (0, 0), (1, 0)) == pytest.approx(90)
    assert tilt_from_vertical_deg((0, 10), (1, 0)) == pytest.approx(math.degrees(math.atan2(1, 10)))


def test_frame_roundtrip_and_orientation():
    frame = Frame.from_keypoints(HORSE)
    assert frame.facing == -1
    for p in HORSE.values():
        assert frame.to_image(frame.to_local(p)) == pytest.approx(p)
    # Ground at y=0, head forward (+x), withers above ground
    assert frame.to_local(HORSE["front_toe"]) == pytest.approx((0, 0))
    assert frame.to_local(HORSE["hind_toe"])[1] == pytest.approx(0)
    assert frame.to_local(HORSE["muzzle"])[0] > frame.to_local(HORSE["tail_base"])[0]
    assert frame.to_local(HORSE["withers"])[1] > 0


def test_mirrored_photo_gives_same_result():
    mirrored = {k: (2000 - x, y) for k, (x, y) in HORSE.items()}
    assert values(mirrored) == pytest.approx(values(HORSE))


def test_tilted_photo_gives_same_result():
    a = math.radians(5)
    tilted = {k: (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)) for k, (x, y) in HORSE.items()}
    assert values(tilted) == pytest.approx(values(HORSE), abs=1e-6)
    assert any("kallellaan" in w for w in evaluate(tilted)["warnings"])


def test_plausible_horse_has_no_warnings_and_all_rules():
    result = evaluate(HORSE)
    assert result["warnings"] == []
    assert [f.id for f in result["findings"]] == [r.id for r in RULES]


def test_steep_shoulder_is_flagged():
    steep = dict(HORSE, scapula_top=(450, 280))  # nearly above the point of shoulder
    finding = next(f for f in evaluate(steep)["findings"] if f.id == "shoulder_slope")
    assert finding.value > 70
    assert finding.status == "deviation"
    assert "Pysty lapa" in finding.interpretation


def test_broken_back_hoof_pastern_axis():
    # Hoof wall flatter than the pastern
    kp = dict(HORSE, front_toe=(380, 1090))
    finding = next(f for f in evaluate(kp)["findings"] if f.id == "front_hpa")
    assert finding.value < -6
    assert "broken back" in finding.interpretation


def test_camped_under_front_leg_sign():
    # Hoof under the body = fetlock behind (towards the tail of) the knee
    kp = dict(HORSE, front_fetlock=(560, 990))
    finding = next(f for f in evaluate(kp)["findings"] if f.id == "front_cannon")
    assert finding.value < -6
    assert "camped under" in finding.interpretation


def test_non_side_view_is_rejected():
    kp = dict(HORSE, muzzle=(1200, 300))  # head behind the tail
    assert "sivukuvalta" in evaluate(kp)["warnings"][0]


def test_range_status():
    r = Range(ideal=(10, 20), acceptable=(5, None))
    assert r.status(15) == "ideal"
    assert r.status(100) == "acceptable"
    assert r.status(1) == "deviation"


def test_map_superanimal_uses_near_side_and_fills_schema():
    raw = {name: (0.0, 0.0, 0.9) for name in (
        "nose", "neck_base", "throat_base", "throat_end", "back_base", "back_middle", "tail_base",
        "front_left_thai", "front_left_knee", "front_left_paw", "back_left_thai", "back_left_knee", "back_left_paw",
        "front_right_thai", "front_right_knee", "front_right_paw", "back_right_thai", "back_right_knee",
        "back_right_paw",
    )}
    raw.update(nose=(100, 300, 0.9), neck_base=(300, 100, 0.9), tail_base=(1050, 340, 0.9))
    raw.update(front_left_knee=(500, 800, 0.9), front_right_knee=(999, 999, 0.9))
    kp = map_superanimal(raw)
    assert set(kp) == set(KEYPOINT_IDS)
    # Facing left -> left side faces the camera
    assert (kp["front_knee"]["x"], kp["front_knee"]["y"]) == (500, 800)
    assert kp["front_knee"]["source"] == "model"
    assert kp["hip_point"]["source"] == "estimated"
    # Estimated hindquarter points lie in front of (towards the head from) the tail base
    assert kp["croup_high"]["x"] < 1050
