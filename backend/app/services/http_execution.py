from __future__ import annotations
import asyncio,json,time
import httpx,jmespath
from app.errors import AppError
from app.services.masking import mask_data,mask_url
from app.services.request_engine import evaluate_assertions

async def execute_request(request:dict,*,connect_timeout_ms:int=5000,read_timeout_ms:int=30000,total_timeout_ms:int=60000,max_response_bytes:int=2*1024*1024,known_secrets:set[str]|None=None,transport:httpx.AsyncBaseTransport|None=None,cookie_jar:dict[str,str]|None=None)->dict:
    method=str(request.get("method") or "GET").upper(); body_type=request.get("body_type") or "none"; kwargs={"headers":request.get("headers") or {},"params":request.get("params") or {},"cookies":{**(cookie_jar or {}),**(request.get("cookies") or {})}}
    body=request.get("body")
    if body_type=="json": kwargs["json"]=body
    elif body_type=="raw": kwargs["content"]=(body if isinstance(body,(str,bytes)) else json.dumps(body,ensure_ascii=False))
    elif body_type in {"urlencoded","form-data"}: kwargs["data"]=body or {}
    elif body_type=="binary": kwargs["content"]=body if isinstance(body,bytes) else str(body or "").encode()
    timeout=httpx.Timeout(total_timeout_ms/1000,connect=connect_timeout_ms/1000,read=read_timeout_ms/1000)
    started=time.perf_counter()
    try:
        async with asyncio.timeout(total_timeout_ms/1000):
            async with httpx.AsyncClient(timeout=timeout,follow_redirects=False,transport=transport) as client:
                async with client.stream(method,request["url"],**kwargs) as response:
                    chunks=[]; size=0
                    async for chunk in response.aiter_bytes():
                        size+=len(chunk)
                        if size>max_response_bytes: raise AppError("RESPONSE_TOO_LARGE","响应体超过限制",422,{"limit":max_response_bytes})
                        chunks.append(chunk)
                    raw=b"".join(chunks); content_type=response.headers.get("content-type","")
                    text=raw.decode(response.encoding or "utf-8",errors="replace")
                    try: json_body=json.loads(text)
                    except (ValueError,json.JSONDecodeError): json_body=None
                    snapshot={"status_code":response.status_code,"headers":dict(response.headers),"text":text,"json":json_body,"size":size}
                    if cookie_jar is not None: cookie_jar.update({str(name):str(value) for name,value in response.cookies.items()})
    except (httpx.TimeoutException,TimeoutError) as exc: raise AppError("EXECUTION_TIMEOUT","请求超时",422) from exc
    except httpx.RequestError as exc: raise AppError("REQUEST_FAILED","请求失败",422,{"type":type(exc).__name__}) from exc
    duration=int((time.perf_counter()-started)*1000)
    extracts={}
    for rule in request.get("extracts") or []:
        if rule.get("type","jmespath")=="jmespath":
            value=jmespath.search(str(rule.get("expression") or ""),snapshot.get("json"))
            extracts[str(rule.get("name"))]={"value":value,"sensitive":bool(rule.get("sensitive")),"scope":rule.get("scope","scenario")}
    assertions=evaluate_assertions(snapshot,request.get("assertions") or [])
    passed=all(item["passed"] for item in assertions)
    known=set(known_secrets or set()) | {str(item["value"]) for item in extracts.values() if item.get("sensitive") and item.get("value") not in (None,"")}
    masked_response=mask_data(snapshot,known_secrets=known)
    return {"status":"passed" if passed else "failed","duration_ms":duration,"response":masked_response,"extracted":mask_data(extracts,known_secrets=known),"runtime_extracted":{k:v["value"] for k,v in extracts.items()},"assertions":assertions,"error_category":None if passed else "assertion_failed","error_message":None if passed else "响应断言失败"}

def request_snapshot(request:dict)->dict:
    copy=mask_data(request); copy["url"]=mask_url(str(request.get("url") or "")); return copy
