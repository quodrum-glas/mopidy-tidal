from __future__ import annotations

"""Base model and shared helpers."""

import logging
from typing import TYPE_CHECKING

import mopidy.models as mm

from mopidy_tidal.helpers import to_timestamp

if TYPE_CHECKING:
    import tidalapi as tdl

IMAGE_SIZE = 320

logger = logging.getLogger(__name__)


def _year_from(date_str: str) -> str | None:
    return date_str[:4] if date_str and len(date_str) >= 4 else None


class Model:
    def __init__(self, *, ref: mm.Ref, api: object, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.ref = ref
        self.api = api
        self._full: object | None = None

    @classmethod
    def from_api(cls, api: object) -> Model:
        raise NotImplementedError

    @classmethod
    def from_uri(cls, session: tdl.Session, /, *, uri: str) -> Model:
        raise NotImplementedError

    @property
    def uri(self) -> str:
        return self.ref.uri

    @property
    def name(self) -> str:
        return self.ref.name

    @property
    def full(self) -> object:
        if self._full is None:
            self._full = self.build()
        return self._full

    @property
    def last_modified(self) -> int:
        return to_timestamp("today")

    def build(self) -> object:
        raise NotImplementedError

    def items(self) -> list[Model]:
        raise NotImplementedError

    def tracks(self) -> list:
        raise NotImplementedError

    @property
    def images(self) -> list[mm.Image] | None:
        raise NotImplementedError
