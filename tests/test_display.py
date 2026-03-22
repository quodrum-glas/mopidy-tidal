from __future__ import annotations

from types import SimpleNamespace

from mopidy_tidal.display import (
    DOWNGRADE,
    FEAT,
    LOSSLESS,
    MASTER,
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
        t = SimpleNamespace(name="Track", audio_quality="HI_RES_LOSSLESS")
        assert track_display_name(t) == f"{MASTER} Track"

    def test_lossless(self):
        t = SimpleNamespace(name="Track", audio_quality="LOSSLESS")
        assert track_display_name(t) == f"{LOSSLESS} Track"

    def test_high_no_badge(self):
        t = SimpleNamespace(name="Track", audio_quality="HIGH")
        assert track_display_name(t) == "Track"

    def test_low(self):
        t = SimpleNamespace(name="Track", audio_quality="LOW")
        assert track_display_name(t) == f"{DOWNGRADE} Track"

    def test_unknown_quality_no_badge(self):
        t = SimpleNamespace(name="Track", audio_quality="SOMETHING_ELSE")
        assert track_display_name(t) == "Track"

    def test_missing_audio_quality(self):
        t = SimpleNamespace(name="Track")
        assert track_display_name(t) == "Track"
