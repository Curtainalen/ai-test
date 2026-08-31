from fastapi import APIRouter,Body,File,Form,Request,UploadFile
from app.dependencies import CurrentUser,DbSession
from app.errors import AppError
from app.response import success
from app.schemas.assets import ApiImportConfirmRequest,OpenApiUrlImportRequest,RequirementModuleUpdate
from app.services import api_assets,requirement_assets
from app.services.identity import require_membership
from app.services.remote_openapi import fetch_remote_openapi

router=APIRouter(prefix="/projects/{project_id}",tags=["assets"])

@router.post("/requirements/upload",status_code=202)
async def upload_requirement(project_id:str,request:Request,db:DbSession,user:CurrentUser,file:UploadFile=File(...),title:str|None=Form(default=None),document_id:str|None=Form(default=None)):
    content=await file.read(); doc,version,job=await requirement_assets.create_upload(db,project_id,user,file.filename or "",file.content_type or "",content,title,document_id)
    return success({"document_id":doc.id,"version":requirement_assets.version_view(version,job)},request.state.trace_id)

@router.get("/requirements/{document_id}")
async def requirement_detail(project_id:str,document_id:str,request:Request,db:DbSession,user:CurrentUser): return success(await requirement_assets.get_document(db,project_id,user,document_id),request.state.trace_id)

@router.patch("/requirement-modules/{module_id}")
async def edit_module(project_id:str,module_id:str,data:RequirementModuleUpdate,request:Request,db:DbSession,user:CurrentUser): return success(requirement_assets.module_view(await requirement_assets.update_module(db,project_id,user,module_id,data)),request.state.trace_id)

@router.get("/requirement-modules")
async def list_requirement_modules(project_id:str,request:Request,db:DbSession,user:CurrentUser,status:str|None=None):
    return success(await requirement_assets.list_modules(db,project_id,user,status),request.state.trace_id)

@router.post("/requirement-modules/{module_id}/confirm")
async def confirm_module(project_id:str,module_id:str,request:Request,db:DbSession,user:CurrentUser): return success(requirement_assets.module_view(await requirement_assets.update_module(db,project_id,user,module_id,None,True)),request.state.trace_id)

@router.post("/api-imports",status_code=201)
async def upload_openapi(project_id:str,request:Request,db:DbSession,user:CurrentUser,file:UploadFile=File(...)):
    if not (file.filename or "").lower().endswith((".json",".yaml",".yml")): raise AppError("OPENAPI_UNSUPPORTED_FILE","仅支持 JSON/YAML",415)
    row=await api_assets.create_import(db,project_id,user,file.filename or "openapi",await file.read()); return success(api_assets.import_view(row),request.state.trace_id)

@router.post("/api-imports/url",status_code=201)
async def import_openapi_url(project_id:str,data:OpenApiUrlImportRequest,request:Request,db:DbSession,user:CurrentUser):
    await require_membership(db,project_id,user)
    content,source_url=await fetch_remote_openapi(data.url,data.auth)
    row=await api_assets.create_import(db,project_id,user,source_url,content,"url",source_url)
    return success(api_assets.import_view(row),request.state.trace_id)

@router.post("/api-imports/{import_id}/confirm")
async def confirm_openapi(project_id:str,import_id:str,revision:int,request:Request,db:DbSession,user:CurrentUser,data:ApiImportConfirmRequest|None=Body(default=None)):
    selected = data.selected_stable_keys if data else None
    return success(api_assets.import_view(await api_assets.confirm_import(db,project_id,user,import_id,revision,selected)),request.state.trace_id)

@router.get("/interfaces")
async def interfaces(project_id:str,request:Request,db:DbSession,user:CurrentUser): return success([api_assets.interface_view(row) for row in await api_assets.list_interfaces(db,project_id,user)],request.state.trace_id)
