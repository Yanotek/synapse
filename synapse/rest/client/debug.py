import gc
import logging
import tracemalloc
from typing import TYPE_CHECKING, Tuple

from twisted.internet.defer import Deferred

from synapse.http.server import HttpServer
from synapse.http.servlet import RestServlet
from synapse.http.site import SynapseRequest
from synapse.types import JsonDict
from ._base import client_patterns

if TYPE_CHECKING:
    from synapse.server import HomeServer

logger = logging.getLogger(__name__)


class DebugServlet(RestServlet):
    """
    GET /user/{user_id}/rooms/{room_id}/tags HTTP/1.1
    """

    PATTERNS = client_patterns("/debug/Wf6dzZKXwL$")
    CATEGORY = "Debug requests"

    def __init__(self, hs: "HomeServer"):
        super().__init__()
        self.hs = hs

    async def on_GET(self, request: SynapseRequest) -> Tuple[int, JsonDict]:
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics("lineno")

        stucked_deferreds = 0
        for obj in gc.get_objects():
            if not isinstance(obj, Deferred):
                continue

            if (
                obj.called and
                obj.result is None and
                getattr(obj, "_suppressAlreadyCalled", False)
            ):
                stucked_deferreds += 1

        notifier = self.hs.get_notifier()
        empty_rooms = 0
        for streams in notifier.room_to_user_streams.values():
            if not streams:
                empty_rooms += 1

        return (
            200,
            {
                "top50": [str(i) for i in top_stats[:50]],
                'stucked_deferreds': stucked_deferreds,
                'empty_rooms': empty_rooms,
                'all_rooms': len(notifier.room_to_user_streams)
            }
        )

    def register(self, http_server: HttpServer) -> None:
        tracemalloc.start()
        return super().register(http_server=http_server)


def register_servlets(hs: "HomeServer", http_server: HttpServer) -> None:
    DebugServlet(hs).register(http_server)
