from __future__ import annotations

import logging

import mopidy.models as mm
import tidalapi as tdl
from tidalapi.models.page import PageItem as TdlPageItem, PageLink as TdlPageLink

from mopidy_tidal.display import feat_item
from mopidy_tidal.helpers import to_timestamp
from mopidy_tidal.uri import URI, URIType

from ._base import Model

logger = logging.getLogger(__name__)


class Page(Model):
    @classmethod
    def from_api(cls, page: tdl.Page) -> Page:
        uri = URI(URIType.PAGE)
        return cls(
            ref=mm.Ref.directory(uri=str(uri), name=page.title),
            api=page,
        )

    @classmethod
    def from_uri(cls, session: tdl.Session, /, *, uri: str) -> Page:
        parsed = URI.from_string(uri)
        if parsed.type != URIType.PAGE:
            raise ValueError(f"Not a valid uri for Page: {uri}")
        page = session.page.get(parsed.page)
        return cls(
            ref=mm.Ref.directory(uri=str(parsed), name=page.title),
            api=page,
            api_path=parsed.page,
        )

    @property
    def last_modified(self) -> int:
        return to_timestamp("today")

    def build(self) -> mm.Ref:
        return self.ref

    def items(self) -> list[Model]:
        from . import model_factory_map

        return list(model_factory_map(self.api))

    def tracks(self) -> list:
        raise AttributeError

    @property
    def images(self) -> list[mm.Image] | None:
        return None


class PageLink:
    def __init__(self, title: str, api_path: str) -> None:
        self.ref = mm.Ref.directory(uri=str(URI(URIType.PAGE, api_path)), name=title)

    @classmethod
    def from_api(cls, page_link: TdlPageLink) -> PageLink:
        return cls(page_link.title, page_link.api_path)


class PageItem(Model):
    URI_REF_MAP: dict[URIType, str] = {
        URIType.TRACK: mm.Ref.TRACK,
        URIType.ALBUM: mm.Ref.ALBUM,
        URIType.ARTIST: mm.Ref.ARTIST,
        URIType.PLAYLIST: mm.Ref.PLAYLIST,
        URIType.MIX: mm.Ref.PLAYLIST,
        URIType.PAGE: mm.Ref.DIRECTORY,
    }

    @classmethod
    def from_api(cls, item: TdlPageItem) -> PageItem | None:
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
        ref = mm.Ref(type=ref_type, uri=str(uri), name=feat_item(item.header))
        return cls(ref=ref, api=item)

    def build(self) -> Model:
        from . import model_factory

        return model_factory(self.api.get())
