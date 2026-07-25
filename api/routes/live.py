"""WebSocket subscriptions for live market, signal, and analytics events."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from api.dependencies import get_container
from events.live_hub import LIVE_TOPICS

router = APIRouter(tags=["live"])


@router.websocket("/ws/{topic}")
async def live_updates(websocket: WebSocket, topic: str) -> None:
    """Keep a topic subscription active until the client closes its WebSocket."""
    if topic not in LIVE_TOPICS:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="unsupported live topic")
        return
    container = get_container(websocket)
    await container.live_hub.subscribe(topic, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await container.live_hub.unsubscribe(topic, websocket)
