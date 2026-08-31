import json
from redis import Redis
from app.config import get_settings

def execution_channel(execution_id:str)->str: return f"execution:{execution_id}"
def publish_execution(execution_id:str,event:dict)->None:
    Redis.from_url(get_settings().redis_url).publish(execution_channel(execution_id),json.dumps(event,ensure_ascii=False,default=str))
