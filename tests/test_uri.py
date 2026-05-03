from __future__ import annotations

import pytest

from mopidy_tidal.uri import URI, URIType


class TestURIType:
    def test_str_returns_value(self):
        assert str(URIType.TRACK) == "track"
        assert str(URIType.DIRECTORY) == "directory"

    def test_all_values_unique(self):
        values = [e.value for e in URIType]
        assert len(values) == len(set(values))


class TestURIConstruction:
    def test_with_type_and_id(self):
        u = URI(URIType.TRACK, "12345")
        assert str(u) == "tidal:track:12345"
        assert u.type == URIType.TRACK
        assert u.id == "12345"

    def test_with_type_only(self):
        u = URI(URIType.DIRECTORY)
        assert str(u) == "tidal:directory"
        assert u.type == URIType.DIRECTORY
        assert u.id is None

    def test_with_string_type(self):
        u = URI("unknown", "abc")
        assert str(u) == "tidal:unknown:abc"
        assert u.type == "unknown"
        assert u.id == "abc"


class TestFromString:
    @pytest.mark.parametrize("uri_type", list(URIType))
    def test_round_trip_all_types(self, uri_type: URIType):
        original = URI(uri_type, "999")
        parsed = URI.from_string(str(original))
        assert parsed.type == uri_type
        assert parsed.id == "999"
        assert str(parsed) == str(original)

    def test_round_trip_no_id(self):
        original = URI(URIType.DIRECTORY)
        parsed = URI.from_string(str(original))
        assert parsed.type == URIType.DIRECTORY
        assert parsed.id is None

    def test_unknown_type_kept_as_string(self):
        parsed = URI.from_string("tidal:somethingelse:42")
        assert parsed.type == "somethingelse"
        assert parsed.id == "42"

    def test_rejects_non_tidal_prefix(self):
        with pytest.raises(ValueError, match="Not a tidal URI"):
            URI.from_string("spotify:track:123")

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError):
            URI.from_string("")

    def test_id_with_colons_preserved(self):
        parsed = URI.from_string("tidal:playlist:abc:def:ghi")
        assert parsed.id == "abc:def:ghi"


class TestTypedId:
    def test_correct_type_returns_id(self):
        u = URI(URIType.ALBUM, "777")
        assert u.typed_id(URIType.ALBUM) == "777"

    def test_wrong_type_raises(self):
        u = URI(URIType.TRACK, "123")
        with pytest.raises(AttributeError, match="not a album"):
            u.typed_id(URIType.ALBUM)

    def test_no_id_raises(self):
        u = URI(URIType.TRACK)
        with pytest.raises(AttributeError):
            u.typed_id(URIType.TRACK)


class TestProperties:
    def test_track(self):
        assert URI(URIType.TRACK, "1").track == "1"

    def test_album(self):
        assert URI(URIType.ALBUM, "2").album == "2"

    def test_artist(self):
        assert URI(URIType.ARTIST, "3").artist == "3"

    def test_playlist(self):
        assert URI(URIType.PLAYLIST, "4").playlist == "4"

    def test_mix(self):
        assert URI(URIType.MIX, "5").mix == "5"

    def test_page(self):
        assert URI(URIType.PAGE, "6").page == "6"

    def test_future(self):
        assert URI(URIType.FUTURE, "7").future == "7"

    def test_wrong_property_raises(self):
        u = URI(URIType.TRACK, "1")
        with pytest.raises(AttributeError):
            _ = u.album


class TestGetattr:
    def test_delegates_uri(self):
        u = URI(URIType.TRACK, "42")
        assert u.uri == "tidal:track:42"

    def test_delegates_type(self):
        u = URI(URIType.ARTIST, "10")
        assert u.type == URIType.ARTIST

    def test_delegates_id(self):
        u = URI(URIType.MIX, "abc")
        assert u.id == "abc"

    def test_unknown_attr_raises(self):
        u = URI(URIType.TRACK, "1")
        with pytest.raises(AttributeError):
            _ = u.nonexistent
