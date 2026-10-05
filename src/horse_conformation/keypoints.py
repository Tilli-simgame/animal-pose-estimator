"""Conformation keypoint schema for a single side-view photo of a horse.

Leg points refer to the near side (the legs closest to the camera).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Keypoint:
    id: str
    label: str  # Finnish UI label
    group: str
    hint: str  # Where exactly to place the point


KEYPOINTS: tuple[Keypoint, ...] = (
    # Head and neck
    Keypoint("muzzle", "Turpa", "Pää ja kaula", "Turvan etureuna sierainten kohdalla"),
    Keypoint("poll", "Niska", "Pää ja kaula", "Niskan korkein kohta korvien takana"),
    Keypoint("throatlatch", "Kurkku", "Pää ja kaula", "Kurkun ja kaulan alalinjan liitos"),
    Keypoint("neck_base_low", "Kaulan tyvi", "Pää ja kaula", "Kohta jossa kaulan alalinja kohtaa rinnan"),
    # Topline
    Keypoint("withers", "Säkä", "Ylälinja", "Säkäkyhmyn korkein kohta"),
    Keypoint("back_low", "Selän matalin kohta", "Ylälinja", "Selän alin kohta sään ja lanteen välissä"),
    Keypoint("loin", "Lanne", "Ylälinja", "Lanne-ristiluunivel, lonkkakyhmyjen tasalla ylälinjassa"),
    Keypoint("croup_high", "Lautasen korkein kohta", "Ylälinja", "Ristiluun korkein kohta"),
    Keypoint("tail_base", "Hännän tyvi", "Ylälinja", "Kohta jossa häntä irtoaa rungosta"),
    # Forehand
    Keypoint("scapula_top", "Lapaluun yläpää", "Etuosa", "Lapaluun yläreuna säkäkyhmyn alla"),
    Keypoint("shoulder_point", "Lavan kärki", "Etuosa", "Olkanivelen etureuna"),
    Keypoint("elbow", "Kyynärpää", "Etuosa", "Kyynärpään kärki rintakehän alla"),
    Keypoint("girth_low", "Rintakehän alin kohta", "Etuosa", "Vyönpaikan alin kohta heti kyynärpään takana"),
    Keypoint("front_knee", "Etupolvi", "Etuosa", "Etupolven (ranne) keskikohta"),
    Keypoint("front_fetlock", "Etuvuohisnivel", "Etuosa", "Vuohisnivelen keskikohta"),
    Keypoint("front_coronet", "Etukavion kruunu", "Etuosa", "Kavion kruunuraja kavion etuseinässä"),
    Keypoint("front_toe", "Etukavion kärki", "Etuosa", "Kavion kärki maan tasossa"),
    # Hindquarters
    Keypoint("hip_point", "Lonkkakyhmy", "Takaosa", "Lonkkakyhmyn (tuber coxae) kärki"),
    Keypoint("buttock_point", "Istuinluun kärki", "Takaosa", "Istuinkyhmyn takimmainen kohta"),
    Keypoint("stifle", "Takapolvi", "Takaosa", "Takapolven (stifle) etureuna"),
    Keypoint("hock", "Kintereen kärki", "Takaosa", "Kinnerluun kärki kintereen takana"),
    Keypoint("hind_fetlock", "Takavuohisnivel", "Takaosa", "Vuohisnivelen keskikohta"),
    Keypoint("hind_coronet", "Takakavion kruunu", "Takaosa", "Kavion kruunuraja kavion etuseinässä"),
    Keypoint("hind_toe", "Takakavion kärki", "Takaosa", "Kavion kärki maan tasossa"),
)

KEYPOINT_IDS: tuple[str, ...] = tuple(k.id for k in KEYPOINTS)

# Lines drawn between keypoints in the UI to make the structure easy to read.
SKELETON: tuple[tuple[str, str], ...] = (
    ("muzzle", "poll"),
    ("poll", "withers"),
    ("throatlatch", "neck_base_low"),
    ("withers", "back_low"),
    ("back_low", "loin"),
    ("loin", "croup_high"),
    ("croup_high", "tail_base"),
    ("scapula_top", "shoulder_point"),
    ("shoulder_point", "elbow"),
    ("elbow", "front_knee"),
    ("front_knee", "front_fetlock"),
    ("front_fetlock", "front_coronet"),
    ("front_coronet", "front_toe"),
    ("hip_point", "buttock_point"),
    ("hip_point", "stifle"),
    ("stifle", "hock"),
    ("hock", "hind_fetlock"),
    ("hind_fetlock", "hind_coronet"),
    ("hind_coronet", "hind_toe"),
)
