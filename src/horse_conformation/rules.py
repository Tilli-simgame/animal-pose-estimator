"""Conformation rules for a side-view photo.

Every rule turns keypoints (in the horse-centred Frame) into one measured value and
compares it to an ideal and an acceptable range. The ranges are a first calibration
pass based on common conformation guides (UGA B1400, horseeducationonline.com,
Goubaux & Barrier proportions); tune them in RANGES as real evaluations accumulate.
"""

import math
from dataclasses import dataclass, field
from typing import Callable

from .geometry import Frame, Point, joint_angle_deg, slope_deg, tilt_from_vertical_deg


@dataclass(frozen=True)
class Range:
    ideal: tuple[float | None, float | None]
    acceptable: tuple[float | None, float | None]

    def status(self, value: float) -> str:
        if _within(value, self.ideal):
            return "ideal"
        if _within(value, self.acceptable):
            return "acceptable"
        return "deviation"


def _within(value: float, bounds: tuple[float | None, float | None]) -> bool:
    lo, hi = bounds
    return (lo is None or value >= lo) and (hi is None or value <= hi)


@dataclass
class Finding:
    id: str
    title: str
    group: str
    value: float
    unit: str
    ideal: tuple[float | None, float | None]
    acceptable: tuple[float | None, float | None]
    status: str
    interpretation: str
    # Line segments in image coordinates used to visualise the measurement
    overlay: list[list[Point]] = field(default_factory=list)


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    group: str
    unit: str
    range: Range
    measure: Callable[["Measure"], float]
    overlay: Callable[["Measure"], list[list[Point]]]
    low_text: str  # value below the ideal range
    high_text: str  # value above the ideal range
    ideal_text: str


class Measure:
    """Keypoints in both image and local coordinates, plus helpers."""

    def __init__(self, keypoints: dict[str, Point]):
        self.img = keypoints
        self.frame = Frame.from_keypoints(keypoints)
        self.p = {k: self.frame.to_local(v) for k, v in keypoints.items()}
        self.H = self.frame.head_length

    def dist(self, a: str, b: str) -> float:
        return math.dist(self.p[a], self.p[b])

    def height(self, k: str) -> float:
        return self.p[k][1]

    def seg(self, *names: str) -> list[Point]:
        return [self.img[n] for n in names]

    def vertical_at(self, k: str) -> list[Point]:
        x, y = self.p[k]
        return [self.frame.to_image((x, y)), self.frame.to_image((x, 0.0))]

    def ground_below(self, k: str) -> list[Point]:
        return self.vertical_at(k)


def _hpa(m: Measure, prefix: str) -> float:
    """Hoof-pastern axis: hoof wall angle minus pastern angle (degrees)."""
    pastern = slope_deg(m.p[f"{prefix}_fetlock"], m.p[f"{prefix}_coronet"])
    hoof = slope_deg(m.p[f"{prefix}_coronet"], m.p[f"{prefix}_toe"])
    return hoof - pastern


def _body_length(m: Measure) -> float:
    return abs(m.p["shoulder_point"][0] - m.p["buttock_point"][0])


RULES: tuple[Rule, ...] = (
    # --- Angles -------------------------------------------------------------------
    Rule(
        "shoulder_slope", "Lavan kaltevuus", "Kulmat", "°",
        Range(ideal=(43, 52), acceptable=(38, 58)),
        lambda m: slope_deg(m.p["scapula_top"], m.p["shoulder_point"]),
        lambda m: [m.seg("scapula_top", "shoulder_point")],
        low_text="Hyvin viisto lapa.",
        high_text="Pysty lapa: askel jää lyhyemmäksi ja etujalkoihin kohdistuu enemmän iskua.",
        ideal_text="Hyvin viisto lapa mahdollistaa pitkän, joustavan askeleen.",
    ),
    Rule(
        "pelvis_slope", "Lantion kaltevuus", "Kulmat", "°",
        Range(ideal=(20, 30), acceptable=(15, 35)),
        lambda m: slope_deg(m.p["hip_point"], m.p["buttock_point"]),
        lambda m: [m.seg("hip_point", "buttock_point")],
        low_text="Laakea lantio: usein pitkä askel mutta vähemmän voimaa takaosan alle tuomiseen.",
        high_text="Jyrkkä (luisu) lantio: askel voi jäädä lyhyeksi.",
        ideal_text="Lantion kaltevuus on tasapainoinen.",
    ),
    Rule(
        "hock_angle", "Kinnerkulma", "Kulmat", "°",
        Range(ideal=(148, 162), acceptable=(140, 168)),
        lambda m: joint_angle_deg(m.p["stifle"], m.p["hock"], m.p["hind_fetlock"]),
        lambda m: [m.seg("stifle", "hock", "hind_fetlock")],
        low_text="Kulmikas kinner (sirppikinner): kintereeseen kohdistuu enemmän rasitusta.",
        high_text="Suora kinner: iskunvaimennus heikkenee, altistaa kinner- ja takapolviongelmille.",
        ideal_text="Kinnerkulma on normaali.",
    ),
    Rule(
        "front_pastern", "Etuvuohisen kulma", "Kulmat", "°",
        Range(ideal=(50, 57), acceptable=(45, 62)),
        lambda m: slope_deg(m.p["front_fetlock"], m.p["front_coronet"]),
        lambda m: [m.seg("front_fetlock", "front_coronet")],
        low_text="Laskeva vuohinen: jänteisiin ja nivelsiteisiin kohdistuu enemmän kuormaa.",
        high_text="Pysty vuohinen: iskut välittyvät jyrkemmin niveliin.",
        ideal_text="Vuohisen kulma on normaali.",
    ),
    Rule(
        "hind_pastern", "Takavuohisen kulma", "Kulmat", "°",
        Range(ideal=(52, 60), acceptable=(47, 65)),
        lambda m: slope_deg(m.p["hind_fetlock"], m.p["hind_coronet"]),
        lambda m: [m.seg("hind_fetlock", "hind_coronet")],
        low_text="Laskeva vuohinen: jänteisiin ja nivelsiteisiin kohdistuu enemmän kuormaa.",
        high_text="Pysty vuohinen: iskut välittyvät jyrkemmin niveliin.",
        ideal_text="Vuohisen kulma on normaali.",
    ),
    Rule(
        "front_hpa", "Etukavio-vuohisakseli", "Kulmat", "°",
        Range(ideal=(-3, 3), acceptable=(-6, 6)),
        lambda m: _hpa(m, "front"),
        lambda m: [m.seg("front_fetlock", "front_coronet", "front_toe")],
        low_text="Akseli taittuu taaksepäin (broken back): kavion kulma on vuohista loivempi, usein pitkä kärki/matala kanta.",
        high_text="Akseli taittuu eteenpäin (broken forward): kavion kulma on vuohista jyrkempi.",
        ideal_text="Kavio ja vuohinen ovat samassa linjassa.",
    ),
    Rule(
        "hind_hpa", "Takakavio-vuohisakseli", "Kulmat", "°",
        Range(ideal=(-3, 3), acceptable=(-6, 6)),
        lambda m: _hpa(m, "hind"),
        lambda m: [m.seg("hind_fetlock", "hind_coronet", "hind_toe")],
        low_text="Akseli taittuu taaksepäin (broken back): kavion kulma on vuohista loivempi.",
        high_text="Akseli taittuu eteenpäin (broken forward): kavion kulma on vuohista jyrkempi.",
        ideal_text="Kavio ja vuohinen ovat samassa linjassa.",
    ),
    # --- Proportions --------------------------------------------------------------
    Rule(
        "neck_length", "Kaulan pituus", "Mittasuhteet", "× pää",
        Range(ideal=(1.3, 1.7), acceptable=(1.1, 1.9)),
        lambda m: m.dist("poll", "withers") / m.H,
        lambda m: [m.seg("poll", "withers"), m.seg("muzzle", "poll")],
        low_text="Lyhyt kaula suhteessa päähän: tasapainon säätely kaulalla on rajallisempaa.",
        high_text="Pitkä kaula suhteessa päähän.",
        ideal_text="Kaulan pituus on sopusuhtainen pään kanssa.",
    ),
    Rule(
        "neck_top_under", "Kaulan ylä-/alalinja", "Mittasuhteet", "×",
        Range(ideal=(1.8, None), acceptable=(1.5, None)),
        lambda m: m.dist("poll", "withers") / m.dist("throatlatch", "neck_base_low"),
        lambda m: [m.seg("poll", "withers"), m.seg("throatlatch", "neck_base_low")],
        low_text="Alalinja on pitkä suhteessa ylälinjaan: kaula kiinnittyy matalalle, taipumus alakaulaan.",
        high_text="",
        ideal_text="Ylälinja on selvästi alalinjaa pidempi, kaula kiinnittyy hyvin.",
    ),
    Rule(
        "shoulder_length", "Lavan pituus", "Mittasuhteet", "× pää",
        Range(ideal=(0.95, 1.2), acceptable=(0.85, 1.3)),
        lambda m: m.dist("scapula_top", "shoulder_point") / m.H,
        lambda m: [m.seg("scapula_top", "shoulder_point"), m.seg("muzzle", "poll")],
        low_text="Lyhyt lapa: askeleen pituus voi jäädä rajallisemmaksi.",
        high_text="Pitkä lapa.",
        ideal_text="Lapa on noin pään mittainen.",
    ),
    Rule(
        "body_square", "Rungon pituus / säkäkorkeus", "Mittasuhteet", "×",
        Range(ideal=(0.95, 1.05), acceptable=(0.9, 1.12)),
        lambda m: _body_length(m) / m.height("withers"),
        lambda m: [m.seg("shoulder_point", "buttock_point"), m.vertical_at("withers")],
        low_text="Runko on lyhyt suhteessa korkeuteen (korkearaajainen).",
        high_text="Runko on pitkä suhteessa korkeuteen (pitkärunkoinen).",
        ideal_text="Hevonen on neliömäinen: rungon pituus ≈ säkäkorkeus.",
    ),
    Rule(
        "chest_depth", "Rintakehän syvyys / jalan pituus", "Mittasuhteet", "×",
        Range(ideal=(0.9, 1.1), acceptable=(0.8, 1.25)),
        lambda m: (m.height("withers") - m.height("girth_low")) / m.height("girth_low"),
        lambda m: [m.vertical_at("withers")],
        low_text="Matala rintakehä suhteessa jalkoihin (pitkäjalkainen).",
        high_text="Syvä rintakehä suhteessa jalkoihin (lyhytjalkainen).",
        ideal_text="Rintakehän syvyys ≈ jalan pituus.",
    ),
    Rule(
        "back_vs_underline", "Selän pituus / alalinja", "Mittasuhteet", "×",
        Range(ideal=(None, 0.75), acceptable=(None, 0.9)),
        lambda m: m.dist("withers", "loin") / m.dist("elbow", "stifle"),
        lambda m: [m.seg("withers", "loin"), m.seg("elbow", "stifle")],
        low_text="",
        high_text="Pitkä selkä suhteessa alalinjaan: selkä voi olla heikompi kantamaan.",
        ideal_text="Lyhyt ylälinja ja pitkä alalinja – vahva selkä ja tilaa askeleelle.",
    ),
    Rule(
        "hip_length", "Lantion pituus / rungon pituus", "Mittasuhteet", "×",
        Range(ideal=(0.3, None), acceptable=(0.27, None)),
        lambda m: m.dist("hip_point", "buttock_point") / _body_length(m),
        lambda m: [m.seg("hip_point", "buttock_point"), m.seg("shoulder_point", "buttock_point")],
        low_text="Lyhyt lantio: vähemmän lihaskiinnitystä ja työntövoimaa.",
        high_text="",
        ideal_text="Lantio on pitkä, hyvä työntövoima.",
    ),
    # --- Balance ------------------------------------------------------------------
    Rule(
        "uphill", "Säkä vs. lautanen", "Tasapaino", "%",
        Range(ideal=(0, 6), acceptable=(-2, 10)),
        lambda m: (m.height("withers") - m.height("croup_high")) / m.height("withers") * 100,
        lambda m: [m.vertical_at("withers"), m.vertical_at("croup_high")],
        low_text="Takakorkea: paino painottuu etuosalle.",
        high_text="Selvästi etukorkea.",
        ideal_text="Säkä on lautasen tasolla tai korkeammalla – kevyt etuosa.",
    ),
    # --- Leg set (side view) ------------------------------------------------------
    Rule(
        "front_cannon", "Etujalan asento", "Jalkojen asento", "°",
        Range(ideal=(-3, 3), acceptable=(-6, 6)),
        lambda m: tilt_from_vertical_deg(m.p["front_knee"], m.p["front_fetlock"]),
        lambda m: [m.seg("front_knee", "front_fetlock"), m.vertical_at("front_knee")],
        low_text="Etujalka on rungon alla (camped under).",
        high_text="Etujalka on rungon edessä (camped out).",
        ideal_text="Etusääri on pystysuora.",
    ),
    Rule(
        "hind_plumb", "Takajalan luotilinja", "Jalkojen asento", "× pää",
        # The fetlock point is the joint centre, slightly ahead of the back of the leg
        Range(ideal=(-0.05, 0.15), acceptable=(-0.15, 0.25)),
        lambda m: (m.p["hind_fetlock"][0] - m.p["buttock_point"][0]) / m.H,
        lambda m: [m.vertical_at("buttock_point"), m.seg("hock", "hind_fetlock")],
        low_text="Takajalka on luotilinjan takana (camped out).",
        high_text="Takajalka on rungon alla (camped under / sirppikinner).",
        ideal_text="Istuinluun luotilinja sivuaa kinnerkärkeä ja kulkee säären takareunaa pitkin.",
    ),
)


def evaluate(keypoints: dict[str, Point]) -> dict:
    m = Measure(keypoints)
    findings = []
    for rule in RULES:
        value = rule.measure(m)
        status = rule.range.status(value)
        if status == "ideal":
            text = rule.ideal_text
        else:
            lo = rule.range.ideal[0]
            text = rule.low_text if lo is not None and value < lo else rule.high_text
        findings.append(
            Finding(
                rule.id, rule.title, rule.group, round(value, 2), rule.unit,
                rule.range.ideal, rule.range.acceptable, status, text, rule.overlay(m),
            )
        )
    return {"findings": findings, "warnings": _quality_warnings(m)}


def _quality_warnings(m: Measure) -> list[str]:
    p = m.p
    order = ("muzzle", "withers", "croup_high", "tail_base")
    if any(p[a][0] <= p[b][0] for a, b in zip(order, order[1:])) or p["front_toe"][0] <= p["hind_toe"][0]:
        # Nothing else is meaningful if the body is not laid out head-to-tail
        return ["Kuva ei näytä sivukuvalta hevosesta – arvioita ei voi tehdä luotettavasti. "
                "Kuvaa hevonen suoraan sivulta, koko hevonen näkyvissä."]

    warnings = []
    body = _body_length(m) / m.height("withers")
    if not 0.75 <= body <= 1.35:
        warnings.append("Rungon mittasuhteet ovat epätavalliset – kuva on ehkä otettu vinosti edestä tai takaa.")
    if m.height("muzzle") < m.height("girth_low"):
        warnings.append("Pää on alhaalla. Kaulan mittasuhteet ja tasapaino arvioidaan luotettavimmin pään ollessa luonnollisessa asennossa.")
    front = tilt_from_vertical_deg(p["front_knee"], p["front_fetlock"])
    hind = tilt_from_vertical_deg(p["hock"], p["hind_fetlock"])
    if abs(front) > 10 or abs(hind) > 12:
        warnings.append("Hevonen ei näytä seisovan auki pystysuorin säärin (liikkeessä?) – jalkojen asentoarviot eivät ole luotettavia.")
    if abs(m.frame.ground_tilt_deg) > 4:
        warnings.append(
            f"Kavioiden kautta kulkeva maalinja on {abs(m.frame.ground_tilt_deg):.0f}° kallellaan. "
            "Kuva on voitu ottaa vinosti tai maa on epätasainen – kulmat on oikaistu maalinjan mukaan."
        )
    if m.height("withers") < 1.5 * m.H:
        warnings.append("Säkäkorkeus on poikkeuksellisen pieni suhteessa päähän – tarkista säkä-, kavio- ja päänpisteet.")
    return warnings
