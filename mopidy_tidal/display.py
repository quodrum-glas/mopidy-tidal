from __future__ import annotations

"""Unicode quality indicators for track display names."""

from tidalapi import Quality

HIRES = "\U0001f1a8"  # 🆨  HI_RES_LOSSLESS
LOSSLESS = "\U0001f1a9"  # 🆩  LOSSLESS
HIGH = "\U000025b3"  # △ HIGH
LOW = "\U000025bc"  # ▼  LOW
TIDAL = "\U0001f163"  # 🅣  generic tidal item
STAR = "\u229b"  # ⊛  favorite
FEAT = "\u24bb"  # Ⓕ  featured
WARNING = "\u26a0"  # ⚠  alert
EXCLAMATION = "\U00002049"  # ⁉  exclamation

_QUALITY_BADGE: dict[str, str] = {
    Quality.HI_RES_LOSSLESS.value: HIRES,
    Quality.HIRES_LOSSLESS.value: HIRES,
    Quality.LOSSLESS.value: "",
    Quality.HIGH.value: HIGH,
    Quality.LOW.value: LOW,
}


def _badge(name: str, badge: str) -> str:
    return f"{badge} {name}" if badge else name


def track_quality(track: object) -> str:
    media_tags = getattr(track, "media_tags", None)
    if not media_tags:
        return "UNKNOWN"
    return next(iter(sorted(media_tags, key=lambda x: len(x), reverse=True)), None)


def track_display_name(track: object) -> str:
    audio_q = track_quality(track)
    badge = _QUALITY_BADGE.get(audio_q, EXCLAMATION)
    return _badge(track.name, badge)


def tidal_item(name: str) -> str:
    return _badge(name, TIDAL)


def fav_item(name: str) -> str:
    return _badge(name, STAR)


def feat_item(name: str) -> str:
    return _badge(name, FEAT)


def alert_item(name: str) -> str:
    return _badge(name, WARNING)
