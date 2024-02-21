from mopidy_tidal.backend import Quality
from string import ascii_uppercase

ASTERISK_CIRCLE = u"\u229B"
M_CIRCLE = u"\u24C2"
F_CIRCLE = u"\u24BB"
T_CIRCLE_NEGATIVE = u"\U0001F163"
LOSSLESS_SQUARE = u"\U0001F1A9"
HIRES_SQUARE = u"\U0001F1A8"
DOWN_UP_PAIRED_ARROWS = u"\u21F5"
DOWNWARDS_PAIRED_ARROWS = u"\u21CA"
BLACK_DOWN_POINTING_TRIANGLE = u"\u25BC"
WARNING_SIGN = u"\u26A0"

META_TAGS = {
    Quality.low_96k.value: DOWNWARDS_PAIRED_ARROWS,
    Quality.low_320k.value: DOWN_UP_PAIRED_ARROWS,
    Quality.high_lossless.value: None,
    "MQA": M_CIRCLE,
    Quality.hi_res.value: HIRES_SQUARE,
    Quality.hi_res_lossless.value: HIRES_SQUARE,
    "HIRES_LOSSLESS": HIRES_SQUARE,
}

FEAT_CHARS = "".join(
    v for k, v in vars().items()
    if isinstance(v, str)
    if k[0] != "_" and
    all(c in f"{ascii_uppercase}_" for c in k)
)


def tidal_item(s):
    return u"{1} {0}".format(s, T_CIRCLE_NEGATIVE)


def fav_item(s):
    return u"{1} {0}".format(s, ASTERISK_CIRCLE)


def feat_item(s):
    return u"{1} {0}".format(s, F_CIRCLE)


def master_title(s):
    return u"{1} {0}".format(s, M_CIRCLE)


def high_lossless(s):
    return u"{1} {0}".format(s, LOSSLESS_SQUARE)


def hi_res(s):
    return s


def low_320k(s):
    return u"{1} {0}".format(s, DOWN_UP_PAIRED_ARROWS)


def low_96k(s):
    return u"{1} {0}".format(s, DOWNWARDS_PAIRED_ARROWS)


def alert_item(s):
    return u"{1} {0}".format(s, WARNING_SIGN)


def strip_feat(s):
    return s.strip(f" {FEAT_CHARS}")


def track_display_name(tidal_track):
    if tidal_track.media_metadata_tags:
        tags = ' '.join(i for i in (META_TAGS.get(tag) for tag in tidal_track.media_metadata_tags) if i)
        return u"{0} {1}".format(tags, tidal_track.name)
    else:
        tag = META_TAGS.get(tidal_track.audio_quality.value)
        if tag:
            return u"{0} {1}".format(tag, tidal_track.name)
    return tidal_track.name
