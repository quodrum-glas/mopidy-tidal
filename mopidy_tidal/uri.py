from __future__ import annotations

"""URI type system for tidal:// URIs."""

from enum import Enum, unique
from typing import NamedTuple

from mopidy_tidal import Extension


@unique
class URIType(Enum):
    TRACK = "track"
    ALBUM = "album"
    ARTIST = "artist"
    PLAYLIST = "playlist"
    MIX = "mix"
    PAGE = "page"
    FUTURE = "future"
    DIRECTORY = "directory"

    def __str__(self) -> str:
        return self.value


class URIData(NamedTuple):
    uri: str
    type: URIType | str
    id: str | None = None


class URI:
    _ext: str = Extension.ext_name
    _sep: str = ":"

    def __init__(self, _type: URIType | str, _id: str | None = None) -> None:
        uri = self._sep.join(str(p) for p in (_type, _id) if p is not None)
        self._data = URIData(f"{self._ext}:{uri}", _type, _id)

    @classmethod
    def from_string(cls, uri: str) -> URI:
        _ext, _type, *_id = uri.split(cls._sep, 2)
        if _ext != cls._ext:
            raise ValueError(f"Not a tidal URI: {uri}")
        try:
            _type = URIType(_type)
        except ValueError:
            pass
        return cls(_type, *_id)

    def typed_id(self, expected: URIType) -> str:
        """Return the id if the URI type matches, else raise AttributeError."""
        if self.type == expected and self.id:
            return self.id
        raise AttributeError(f"URI {self} is not a {expected.value}")

    @property
    def track(self) -> str:
        return self.typed_id(URIType.TRACK)

    @property
    def album(self) -> str:
        return self.typed_id(URIType.ALBUM)

    @property
    def artist(self) -> str:
        return self.typed_id(URIType.ARTIST)

    @property
    def playlist(self) -> str:
        return self.typed_id(URIType.PLAYLIST)

    @property
    def mix(self) -> str:
        return self.typed_id(URIType.MIX)

    @property
    def page(self) -> str:
        return self.typed_id(URIType.PAGE)

    @property
    def future(self) -> str:
        return self.typed_id(URIType.FUTURE)

    def __getattr__(self, item: str) -> object:
        return getattr(self._data, item)

    def __str__(self) -> str:
        return self.uri
