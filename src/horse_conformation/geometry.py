"""Geometry in a horse-centred frame.

Image coordinates (x right, y down) are mapped to a frame where:
  * the ground line (front toe -> hind toe) is horizontal and y = 0,
  * +x points towards the horse's head, +y points up.
So all rules can be written once, regardless of which way the horse faces.
"""

import math
from dataclasses import dataclass

Point = tuple[float, float]


@dataclass(frozen=True)
class Frame:
    origin: Point  # front toe in image coordinates
    cos: float
    sin: float
    facing: int  # +1 if the head points to image +x, else -1
    head_length: float
    ground_tilt_deg: float

    @classmethod
    def from_keypoints(cls, kp: dict[str, Point]) -> "Frame":
        facing = 1 if kp["muzzle"][0] > kp["tail_base"][0] else -1
        fx, fy = kp["front_toe"]
        hx, hy = kp["hind_toe"]
        # Ground direction pointing from hind toe towards front toe (= towards the head)
        angle = math.atan2(fy - hy, fx - hx)
        if facing < 0:
            angle -= math.pi  # keep the angle small; facing flips x separately
        tilt = math.degrees(angle)
        tilt = (tilt + 180) % 360 - 180
        head = math.dist(kp["muzzle"], kp["poll"])
        return cls(kp["front_toe"], math.cos(angle), math.sin(angle), facing, head, tilt)

    def to_local(self, p: Point) -> Point:
        dx, dy = p[0] - self.origin[0], p[1] - self.origin[1]
        # rotate by -angle
        rx = dx * self.cos + dy * self.sin
        ry = -dx * self.sin + dy * self.cos
        return rx * self.facing, -ry

    def to_image(self, q: Point) -> Point:
        rx, ry = q[0] * self.facing, -q[1]
        dx = rx * self.cos - ry * self.sin
        dy = rx * self.sin + ry * self.cos
        return dx + self.origin[0], dy + self.origin[1]


def slope_deg(a: Point, b: Point) -> float:
    """Unsigned angle of segment a-b to the horizontal, 0..90 degrees."""
    dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
    return math.degrees(math.atan2(dy, dx))


def joint_angle_deg(a: Point, vertex: Point, b: Point) -> float:
    """Angle a-vertex-b, 0..180 degrees."""
    v1 = (a[0] - vertex[0], a[1] - vertex[1])
    v2 = (b[0] - vertex[0], b[1] - vertex[1])
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (math.hypot(*v1) * math.hypot(*v2))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def tilt_from_vertical_deg(top: Point, bottom: Point) -> float:
    """Signed tilt of a top->bottom segment from vertical (local frame).

    Positive when the bottom end is forward (towards the head) of the top end.
    """
    return math.degrees(math.atan2(bottom[0] - top[0], top[1] - bottom[1]))

