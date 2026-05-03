from __future__ import annotations

import logging

from mopidy.models import Image as MopidyImage
from mopidy.models import Ref as MopidyRef
from tidalapi import Session as TidalSession
from tidalapi.models_v1 import Page as TidalPageV1
from tidalapi.models_v1.page import PageItem as TidalPageItemV1
from tidalapi.models_v1.page import PageLink as TidalPageLinkV1

from mopidy_tidal.display import feat_item
from mopidy_tidal.helpers import to_timestamp
from mopidy_tidal.uri import URI, URIType

from ._base import Model

logger = logging.getLogger(__name__)


class Page(Model):
    @classmethod
    def from_v1(cls, page: TidalPageV1) -> Page:
        uri = URI(URIType.PAGE)
        return cls(
            ref=MopidyRef.directory(uri=str(uri), name=page.title),
            api=page,
        )

    @classmethod
    def from_uri(cls, session: TidalSession, /, *, uri: str) -> Page:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.PAGE:
            raise ValueError(f"Not a valid uri for Page: {uri}")
        page = session.page.get(parsed.page)
        return cls(
            ref=MopidyRef.directory(uri=str(parsed), name=page.title),
            api=page,
            api_path=parsed.page,
        )

    @property
    def last_modified(self) -> int:
        return to_timestamp("today")

    def build(self) -> MopidyRef:
        return self.ref

    def items(self) -> list[Model]:
        from . import model_factory_map

        return list(model_factory_map(self.api))

    def tracks(self) -> list:
        raise AttributeError

    @property
    def images(self) -> list[MopidyImage] | None:
        return None


class PageLink:
    def __init__(self, title: str, api_path: str) -> None:
        self.ref = MopidyRef.directory(uri=str(URI(URIType.PAGE, api_path)), name=title)

    @classmethod
    def from_v1(cls, page_link: TidalPageLinkV1) -> PageLink:
        return cls(page_link.title, page_link.api_path)


class PageItem(Model):
    URI_REF_MAP: dict[URIType, str] = {
        URIType.TRACK: MopidyRef.TRACK,
        URIType.ALBUM: MopidyRef.ALBUM,
        URIType.ARTIST: MopidyRef.ARTIST,
        URIType.PLAYLIST: MopidyRef.PLAYLIST,
        URIType.MIX: MopidyRef.PLAYLIST,
        URIType.PAGE: MopidyRef.DIRECTORY,
    }

    @classmethod
    def from_v1(cls, item: TidalPageItemV1) -> PageItem | None:
        try:
            uri_type = URIType[item.type]
        except KeyError:
            logger.error("Future return type unknown: %s", item.type)
            return None
        ref_type = cls.URI_REF_MAP.get(uri_type)
        if ref_type is None:
            logger.error("Future return type not supported: %s", uri_type)
            return None
        uri = URI(uri_type, item.artifact_id)
        ref = MopidyRef(type=ref_type, uri=str(uri), name=feat_item(item.header))
        return cls(ref=ref, api=item)

    def build(self) -> Model:
        from . import model_factory

        return model_factory(self.api.get())
