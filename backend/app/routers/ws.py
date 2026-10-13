from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..deps import user_from_token_str
from ..events import manager

router = APIRouter()


@router.websocket("/updates")
async def ws_updates(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        auth = websocket.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]

    # websocket can't use the normal Depends(); open our own session briefly
    db: Session = SessionLocal()
    try:
        user = user_from_token_str(token, db) if token else None
    finally:
        db.close()

    if not user:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "unauthorized"})
        await websocket.close(code=1008)
        return

    await manager.connect(websocket)
    try:
        await websocket.send_json(
            {
                "type": "hello",
                "message": "live updates enabled",
                "role": user.role,
            }
        )
        while True:
            await websocket.receive_text()  # heartbeat / pings; content ignored
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
