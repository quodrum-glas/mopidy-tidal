from __future__ import annotations

from types import SimpleNamespace

from mopidy_tidal.display import (
    EXCLAMATION,
    FEAT,
    HIGH,
    HIRES,
    LOW,
    STAR,
    TIDAL,
    WARNING,
    alert_item,
    fav_item,
    feat_item,
    tidal_item,
    track_display_name,
)


class TestItemBadges:
    def test_tidal_item(self):
        assert tidal_item("My Playlist") == f"{TIDAL} My Playlist"

    def test_fav_item(self):
        assert fav_item("Song") == f"{STAR} Song"

    def test_feat_item(self):
        assert feat_item("Artist") == f"{FEAT} Artist"

    def test_alert_item(self):
        assert alert_item("radio") == f"{WARNING} radio"


class TestTrackDisplayName:
    def test_hi_res_lossless(self):
        t = SimpleNamespace(name="Track", media_tags=["HI_RES_LOSSLESS"])
        assert track_display_name(t) == f"{HIRES} Track"

    def test_lossless_no_badge(self):
        t = SimpleNamespace(name="Track", media_tags=["LOSSLESS"])
        assert track_display_name(t) == "Track"

    def test_high(self):
        t = SimpleNamespace(name="Track", media_tags=["HIGH"])
        assert track_display_name(t) == f"{HIGH} Track"

    def test_low(self):
        t = SimpleNamespace(name="Track", media_tags=["LOW"])
        assert track_display_name(t) == f"{LOW} Track"

    def test_unknown_quality_exclamation(self):
        t = SimpleNamespace(name="Track", media_tags=["SOMETHING_ELSE"])
        assert track_display_name(t) == f"{EXCLAMATION} Track"

    def test_missing_media_tags(self):
        t = SimpleNamespace(name="Track")
        assert track_display_name(t) == f"{EXCLAMATION} Track"

    def test_empty_media_tags(self):
        t = SimpleNamespace(name="Track", media_tags=[])
        assert track_display_name(t) == f"{EXCLAMATION} Track"

    def test_multiple_media_tags_picks_longest(self):
        t = SimpleNamespace(name="Track", media_tags=["LOSSLESS", "HI_RES_LOSSLESS"])
        assert track_display_name(t) == f"{HIRES} Track"
