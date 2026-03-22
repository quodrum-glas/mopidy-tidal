from __future__ import annotations

"""Unicode quality indicators for track display names."""

from tidalapi import Quality

MASTER = "\u24C2"          # Ⓜ  HI_RES_LOSSLESS
LOSSLESS = "\U0001F1A9"    # 🆩  LOSSLESS
DOWNGRADE = "\u21F5"       # ⇵  LOW
TIDAL = "\U0001F163"       # 🅣  generic tidal item
STAR = "\u229B"            # ⊛  favorite
FEAT = "\u24BB"            # Ⓕ  featured
WARNING = "\u26A0"         # ⚠  alert

_QUALITY_BADGE: dict[str, str] = {
    Quality.HI_RES_LOSSLESS.value: MASTER,
    Quality.LOSSLESS.value: LOSSLESS,
    Quality.HIGH.value: "",
    Quality.LOW.value: DOWNGRADE,
}


def _badge(name: str, badge: str) -> str:
    return f"{badge} {name}" if badge else name


def track_display_name(track: object) -> str:
    audio_q = getattr(track, "audio_quality", "")
    badge = _QUALITY_BADGE.get(audio_q, "")
    return _badge(track.name, badge)


def tidal_item(name: str) -> str:
    return _badge(name, TIDAL)


def fav_item(name: str) -> str:
    return _badge(name, STAR)


def feat_item(name: str) -> str:
    return _badge(name, FEAT)


def alert_item(name: str) -> str:
    return _badge(name, WARNING)
