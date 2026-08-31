import asyncio,json
from fastapi import APIRouter,WebSocket,WebSocketDisconnect
from redis.asyncio import Redis
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import ExecutionStep,ExecutionTask,ProjectMember,User
from app.security import decode_access_token
from app.services.events import execution_channel
from app.services.executions import task_view
from app.config import get_settings

router=APIRouter()
@router.websocket("/ws/projects/{project_id}/executions/{execution_id}")
async def execution_ws(ws:WebSocket,project_id:str,execution_id:str):
    await ws.accept()
    try:
        auth_message=json.loads(await asyncio.wait_for(ws.receive_text(),timeout=5))
        user_id=decode_access_token(str(auth_message.get("token") or "")) if auth_message.get("type")=="auth" else ""
        if not user_id: raise ValueError("missing auth")
    except Exception: await ws.close(code=4401); return
    async with AsyncSessionLocal() as db:
        user=await db.get(User,user_id); member=await db.scalar(select(ProjectMember).where(ProjectMember.project_id==project_id,ProjectMember.user_id==user_id)); task=await db.scalar(select(ExecutionTask).where(ExecutionTask.id==execution_id,ExecutionTask.project_id==project_id))
        if not user or not member or not task: await ws.close(code=4403); return
        steps=(await db.scalars(select(ExecutionStep).where(ExecutionStep.execution_id==task.id).order_by(ExecutionStep.seq))).all(); snapshot=task_view(task,steps)
    await ws.send_text(json.dumps({"type":"snapshot","version":snapshot["event_version"],"data":snapshot},ensure_ascii=False))
    redis=Redis.from_url(get_settings().redis_url); pubsub=redis.pubsub(); await pubsub.subscribe(execution_channel(execution_id))
    try:
        while True:
            message=await pubsub.get_message(ignore_subscribe_messages=True,timeout=1.0)
            if message: await ws.send_text(message["data"].decode() if isinstance(message["data"],bytes) else message["data"])
            try:
                text=await asyncio.wait_for(ws.receive_text(),timeout=0.05)
                if text.strip()=="ping": await ws.send_text('{"type":"pong"}')
            except asyncio.TimeoutError: pass
    except WebSocketDisconnect: pass
    finally: await pubsub.unsubscribe(execution_channel(execution_id)); await pubsub.close(); await redis.close()
