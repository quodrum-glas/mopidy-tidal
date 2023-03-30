from mopidy_tidal.backend import Quality
from string import ascii_uppercase

ASTERISK_CIRCLE = u"\u229B"
M_CIRCLE = u"\u24C2"
F_CIRCLE = u"\u24BB"
T_CIRCLE_NEGATIVE = u"\U0001F163"
LOSSLESS_SQUARE = u"\U0001F1A9"
DOWNWARDS_PAIRED_ARROWS = u"\u21CA"
BLACK_DOWN_POINTING_TRIANGLE = u"\u25BC"
WARNING_SIGN = u"\u26A0"

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


def lossless_title(s):
    return s


def high_title(s):
    return u"{1} {0}".format(s, DOWNWARDS_PAIRED_ARROWS)


def low_title(s):
    return u"{1} {0}".format(s, BLACK_DOWN_POINTING_TRIANGLE)


def alert_item(s):
    return u"{1} {0}".format(s, WARNING_SIGN)


def strip_feat(s):
    return s.strip(f" {FEAT_CHARS}")


def track_display_name(tidal_track):
    track_name = tidal_track.name
    if tidal_track.audio_quality == Quality.master:
        return master_title(track_name)
    if tidal_track.audio_quality == Quality.lossless:
        return lossless_title(track_name)
    if tidal_track.audio_quality == Quality.high:
        return high_title(track_name)
    if tidal_track.audio_quality == Quality.low:
        return low_title(track_name)
    return track_name
