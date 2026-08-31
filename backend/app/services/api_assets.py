import hashlib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.errors import AppError
from app.models import ApiImport,ApiInterface,ApiModule,User
from app.services.identity import require_membership
from app.services.openapi import diff_interfaces,parse_spec

def import_view(row): return {"id":row.id,"source_name":row.source_name,"spec_version":row.spec_version,"diff":row.diff,"warnings":row.warnings,"status":row.status,"revision":row.revision,"created_at":row.created_at.isoformat()}
def interface_view(row): return {"id":row.id,"module_id":row.module_id,"stable_key":row.stable_key,"method":row.method,"path":row.path,"summary":row.summary,"tags":row.tags,"parameters":row.parameters,"request_body":row.request_body,"responses":row.responses,"security":row.security,"manual_config":row.manual_config,"revision":row.revision,"is_deleted":row.is_deleted}

async def create_import(db:AsyncSession,project_id:str,user:User,filename:str,content:bytes):
    await require_membership(db,project_id,user); parsed=parse_spec(content)
    existing=list((await db.scalars(select(ApiInterface).where(ApiInterface.project_id==project_id))).all())
    old=[{**(row.imported_snapshot or {}),"stable_key":row.stable_key,"manual_config":row.manual_config,"revision":row.revision} for row in existing if not row.is_deleted and (row.imported_snapshot or {}).get("source_name")==filename]
    incoming=[{**item,"stable_key":hashlib.sha256(f"{filename}|{item['method']}|{item['normalized_path']}".encode()).hexdigest(),"source_name":filename} for item in parsed["interfaces"]]
    diff=diff_interfaces(old,incoming)
    conflicts=[]
    for item in diff["modified"]:
        if item["before"].get("manual_config"): conflicts.append({"stable_key":item["after"]["stable_key"],"reason":"manual_config_present"})
    diff["conflicts"]=conflicts
    row=ApiImport(project_id=project_id,source_name=filename,spec_version=parsed["version"],raw_snapshot=parsed["raw"],normalized_snapshot=incoming,diff=diff,warnings=parsed["warnings"],created_by=user.id)
    db.add(row); await db.commit(); await db.refresh(row); return row

async def confirm_import(db,project_id,user,import_id,revision:int):
    await require_membership(db,project_id,user); row=await db.scalar(select(ApiImport).where(ApiImport.id==import_id,ApiImport.project_id==project_id))
    if not row: raise AppError("RESOURCE_NOT_FOUND","导入记录不存在",404)
    if row.status!="pending_confirmation": raise AppError("IMPORT_ALREADY_APPLIED","导入已处理",409)
    if row.revision!=revision: raise AppError("REVISION_CONFLICT","导入记录已变更",409,{"current_revision":row.revision})
    if row.diff.get("conflicts"): raise AppError("OPENAPI_IMPORT_CONFLICT","存在人工配置冲突，请先处理",409,{"conflicts":row.diff["conflicts"]})
    modules={m.name:m for m in (await db.scalars(select(ApiModule).where(ApiModule.project_id==project_id))).all()}
    all_interfaces=list((await db.scalars(select(ApiInterface).where(ApiInterface.project_id==project_id))).all()); interfaces={i.stable_key:i for i in all_interfaces}
    for item in row.normalized_snapshot:
        module=modules.get(item["module"])
        if not module: module=ApiModule(project_id=project_id,name=item["module"],source="tag" if item["tags"] else "path",created_by=user.id); db.add(module); await db.flush(); modules[module.name]=module
        target=interfaces.get(item["stable_key"])
        fields={"module_id":module.id,"import_id":row.id,"method":item["method"],"path":item["path"],"summary":item["summary"],"tags":item["tags"],"parameters":item["parameters"],"request_body":item["request_body"],"responses":item["responses"],"security":item["security"],"imported_snapshot":item,"is_deleted":False}
        if target:
            for key,value in fields.items(): setattr(target,key,value)
            target.revision+=1
        else: db.add(ApiInterface(project_id=project_id,stable_key=item["stable_key"],manual_config={},created_by=user.id,**fields))
    incoming={item["stable_key"] for item in row.normalized_snapshot}
    for key,target in interfaces.items():
        if (target.imported_snapshot or {}).get("source_name")==row.source_name and key not in incoming: target.is_deleted=True; target.revision+=1
    row.status="applied"; row.revision+=1; await db.commit(); return row

async def list_interfaces(db,project_id,user): await require_membership(db,project_id,user); return list((await db.scalars(select(ApiInterface).where(ApiInterface.project_id==project_id,ApiInterface.is_deleted.is_(False)).order_by(ApiInterface.path,ApiInterface.method))).all())
