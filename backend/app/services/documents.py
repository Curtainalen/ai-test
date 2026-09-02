from __future__ import annotations
import hashlib, io, re, subprocess, tempfile
from pathlib import Path
from docx import Document
from openpyxl import load_workbook
from PIL import Image
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from app.errors import AppError

ALLOWED = {".pdf":"application/pdf", ".doc":"application/msword", ".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".md":"text/markdown", ".markdown":"text/markdown", ".txt":"text/plain", ".xlsx":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xls":"application/vnd.ms-excel", ".png":"image/png", ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".gif":"image/gif", ".bmp":"image/bmp", ".tiff":"image/tiff"}

def validate_filename(filename: str) -> tuple[str,str]:
    safe = Path(filename or "").name
    if safe != filename or not safe: raise AppError("FILE_INVALID_NAME", "文件名无效", 422)
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED: raise AppError("FILE_UNSUPPORTED", "仅支持 PDF、Word、Excel、图片、Markdown 和 TXT", 415)
    return safe, ext

def sha256_bytes(content: bytes) -> str: return hashlib.sha256(content).hexdigest()

def parse_document(filename: str, content: bytes, max_pdf_pages: int = 200, max_docx_images: int = 200) -> list[dict]:
    _, ext = validate_filename(filename)
    if ext == ".pdf": return _parse_pdf(content, max_pdf_pages)
    if ext == ".docx": return _parse_docx(content, max_docx_images)
    if ext == ".doc": return _parse_doc(content, max_docx_images)
    if ext in {".xlsx", ".xls"}: return _parse_excel(content)
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"}: return _parse_image(content, ext)
    text = decode_text(content)
    return _parse_markdown(text) if ext in {".md", ".markdown"} else _parse_txt(text)

def decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try: return content.decode(encoding)
        except UnicodeDecodeError: continue
    raise AppError("DOCUMENT_ENCODING_UNSUPPORTED", "文本编码无法识别", 422)

def _block(seq, kind, content, locator, structured=None, confidence=1.0, needs=False):
    return {"seq":seq,"block_type":kind,"content":content,"structured_content":structured or {},"source_locator":locator,"confidence":confidence,"needs_correction":needs}

def _parse_txt(text: str) -> list[dict]:
    blocks=[]
    for i,line in enumerate(text.splitlines(),1):
        value=line.strip()
        if value: blocks.append(_block(len(blocks)+1,"paragraph",value,{"line_start":i,"line_end":i}))
    return blocks

def _parse_markdown(text: str) -> list[dict]:
    blocks=[]; headings=[]; code=[]; in_code=False; lines=text.splitlines(); i=1
    while i <= len(lines):
        line=lines[i-1]
        if line.strip().startswith("```"):
            if in_code: blocks.append(_block(len(blocks)+1,"code","\n".join(code),{"line_start":i-len(code),"line_end":i,"heading_path":headings.copy()})); code=[]
            in_code=not in_code; i+=1; continue
        if in_code: code.append(line); i+=1; continue
        match=re.match(r"^(#{1,6})\s+(.+)$",line)
        if match:
            level=len(match.group(1)); headings=headings[:level-1]+[match.group(2).strip()]
            blocks.append(_block(len(blocks)+1,"heading",headings[-1],{"line_start":i,"line_end":i,"heading_path":headings.copy()},{"level":level})); i+=1; continue
        value=line.strip()
        if not value: i+=1; continue
        if "|" in value and i < len(lines) and re.match(r"^\s*\|?\s*:?-+", lines[i]):
            table_lines=[value,lines[i].strip()]; end=i+1
            while end < len(lines) and "|" in lines[end]: table_lines.append(lines[end].strip()); end+=1
            rows=[[cell.strip() for cell in row.strip("|").split("|")] for row in table_lines if not re.match(r"^\s*\|?\s*:?-+",row)]
            blocks.append(_block(len(blocks)+1,"table","\n".join(table_lines),{"line_start":i,"line_end":end,"heading_path":headings.copy()},{"headers":rows[0] if rows else [],"rows":rows[1:] if len(rows)>1 else []})); i=end+1; continue
        kind="list" if re.match(r"^([-*+] |\d+\. )",value) else "paragraph"
        blocks.append(_block(len(blocks)+1,kind,value,{"line_start":i,"line_end":i,"heading_path":headings.copy()}))
        i+=1
    return blocks

def _parse_pdf(content: bytes, max_pages: int) -> list[dict]:
    try: reader=PdfReader(io.BytesIO(content))
    except Exception as exc: raise AppError("DOCUMENT_PARSE_FAILED", "PDF 无法解析", 422) from exc
    if reader.is_encrypted: raise AppError("DOCUMENT_PASSWORD_REQUIRED", "加密 PDF 暂不接受解析密码，请上传解密版本", 422)
    if len(reader.pages)>max_pages: raise AppError("DOCUMENT_PAGE_LIMIT", "PDF 页数超过限制", 413, {"pages":len(reader.pages),"limit":max_pages})
    blocks=[]
    for page_no,page in enumerate(reader.pages,1):
        text=(page.extract_text() or "").strip(); confidence=1.0 if text else 0.0
        if text: blocks.append(_block(len(blocks)+1,"paragraph",text,{"page":page_no},confidence=confidence))
        else: blocks.append(_block(len(blocks)+1,"image","",{"page":page_no,"ocr_status":"not_implemented"},confidence=0.0,needs=True))
    return blocks

def _parse_docx(content: bytes, max_images: int) -> list[dict]:
    try: doc=Document(io.BytesIO(content))
    except Exception as exc: raise AppError("DOCUMENT_PARSE_FAILED", "DOCX 无法解析", 422) from exc
    if len(doc.inline_shapes)>max_images: raise AppError("DOCUMENT_IMAGE_LIMIT", "DOCX 图片数量超过限制", 413)
    blocks=[]; paragraph_map={p._element:(index,p) for index,p in enumerate(doc.paragraphs)}; table_map={t._element:(index,t) for index,t in enumerate(doc.tables)}
    image_order=0
    # 按 Word 正文 XML 的实际顺序遍历，避免段落、表格和图片被分段重排。
    for element in doc.element.body:
        if element.tag.endswith("p") and element in paragraph_map:
            index,p=paragraph_map[element]; text=p.text.strip(); style=p.style.name or ""
            if text:
                kind="heading" if style.lower().startswith("heading") else ("list" if "list" in style.lower() else "paragraph")
                blocks.append(_block(len(blocks)+1,kind,text,{"paragraph_index":index},{"style":style}))
            for rid in _paragraph_image_relationship_ids(element):
                relation=doc.part.rels.get(rid)
                if relation is None or not hasattr(relation.target_part, "blob"): continue
                image_id=f"img_{image_order:03d}"; image_order+=1
                blob=relation.target_part.blob; mime=relation.target_part.content_type
                # 图片字节只在 worker 落盘前临时携带，不能写入 JSON 内容块。
                blocks.append(_block(len(blocks)+1,"image",f"![图片](docimg://{image_id})",{"paragraph_index":index,"image_id":image_id},{"image_id":image_id,"mime_type":mime,"file_size":len(blob),"_image_bytes":blob},confidence=0.0,needs=False))
        elif element.tag.endswith("tbl") and element in table_map:
            index,table=table_map[element]; rows=[[cell.text.strip() for cell in row.cells] for row in table.rows]
            markdown=_table_markdown(rows)
            blocks.append(_block(len(blocks)+1,"table",markdown,{"table_index":index},{"headers":rows[0] if rows else [],"rows":rows[1:] if len(rows)>1 else []}))
    return blocks


def _paragraph_image_relationship_ids(element) -> list[str]:
    namespace={"a":"http://schemas.openxmlformats.org/drawingml/2006/main", "r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships", "v":"urn:schemas-microsoft-com:vml"}
    result=[]
    for node in element.findall(".//a:blip", namespace):
        rid=node.get(qn("r:embed"))
        if rid: result.append(rid)
    for node in element.findall(".//v:imagedata", namespace):
        rid=node.get(qn("r:id"))
        if rid: result.append(rid)
    return list(dict.fromkeys(result))


def _table_markdown(rows: list[list[str]]) -> str:
    if not rows: return ""
    width=max(len(row) for row in rows); normalized=[row+[""]*(width-len(row)) for row in rows]
    escaped=[[cell.replace("|", "\\|").replace("\n", "<br>") for cell in row] for row in normalized]
    return "\n".join(["| " + " | ".join(escaped[0]) + " |", "| " + " | ".join(["---"]*width) + " |", *["| " + " | ".join(row) + " |" for row in escaped[1:]]])


def _parse_doc(content: bytes, max_images: int) -> list[dict]:
    with tempfile.TemporaryDirectory() as temp_dir:
        source=Path(temp_dir)/"source.doc"; source.write_bytes(content)
        # 优先转为 DOCX，以保留表格和图片；轻量部署没有 LibreOffice 时再退化为纯文本。
        try:
            subprocess.run(["libreoffice", "--headless", "--convert-to", "docx", "--outdir", temp_dir, str(source)], check=True, timeout=60, capture_output=True)
            converted=Path(temp_dir)/"source.docx"
            if converted.exists(): return _parse_docx(converted.read_bytes(), max_images)
        except (FileNotFoundError, subprocess.SubprocessError): pass
        try:
            result=subprocess.run(["antiword", "-w", "0", str(source)], check=True, timeout=30, capture_output=True)
            return _parse_txt(decode_text(result.stdout))
        except (FileNotFoundError, subprocess.SubprocessError):
            raise AppError("DOCUMENT_LEGACY_DOC_UNAVAILABLE", "DOC 解析需要 LibreOffice 或 antiword，请转换为 DOCX/PDF 后重试", 422)

def _parse_excel(content: bytes) -> list[dict]:
    try: workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as exc: raise AppError("DOCUMENT_PARSE_FAILED", "Excel 无法解析", 422) from exc
    blocks=[]
    for sheet in workbook.worksheets:
        rows=[["" if value is None else str(value) for value in row] for row in sheet.iter_rows(values_only=True)]
        rows=[row for row in rows if any(cell.strip() for cell in row)]
        if rows:
            blocks.append(_block(len(blocks)+1,"table",_table_markdown(rows),{"sheet_name":sheet.title,"row_start":1,"row_end":len(rows)},{"sheet_name":sheet.title,"headers":rows[0],"rows":rows[1:]}))
    return blocks

def _parse_image(content: bytes, ext: str) -> list[dict]:
    try: image=Image.open(io.BytesIO(content)); width,height=image.size
    except Exception as exc: raise AppError("DOCUMENT_PARSE_FAILED", "图片无法解析", 422) from exc
    return [_block(1,"image","",{"image_format":ext.lstrip("."),"width":width,"height":height,"ocr_status":"not_available"},{"image_ref":"original_file","ocr_text":"","width":width,"height":height},confidence=0.0,needs=True)]

def build_sections(blocks: list[dict]) -> tuple[list[dict], list[int]]:
    """Create stable sections. H1 is retained as document context, never a module by itself."""
    sections=[]; context=[]; stack=[]
    for block in blocks:
        if block.get("block_type") == "heading":
            level=int((block.get("structured_content") or {}).get("level", 6)); stack=[item for item in stack if item["level"] < level]
            section={"id":f"section-{block['seq']}","heading_seq":block["seq"],"title":block.get("content", ""),"level":level,"block_sequences":[block["seq"]],"parent_id":stack[-1]["id"] if stack else None}
            sections.append(section); stack.append(section)
            if level == 1: context.append(block["seq"])
        elif stack: stack[-1]["block_sequences"].append(block["seq"])
        else:
            if not sections or not sections[-1].get("synthetic"):
                sections.append({"id":f"section-{block['seq']}","heading_seq":None,"title":"未命名需求","level":2,"block_sequences":[],"parent_id":None,"synthetic":True})
            sections[-1]["block_sequences"].append(block["seq"])
    return sections, context

def suggest_modules(blocks: list[dict]) -> list[dict]:
    sections, _ = build_sections(blocks)
    if any(block["block_type"] == "heading" for block in blocks):
        by_seq={block["seq"]:block for block in blocks}; result=[]
        for section in sections:
            if section["level"] == 1 or section["level"] > 3: continue
            selected=[by_seq[seq] for seq in section["block_sequences"]]
            body=[block for block in selected if block["block_type"] in {"paragraph","list","table","code","image"}]
            if not body: continue
            result.append({"name":section["title"][:255], "description":" ".join(block["content"].strip() for block in body if block["content"].strip())[:1000], "source_block_ids":[], "source_seqs":[block["seq"] for block in selected], "split_method":"heading", "status":"rule_boundary"})
        if result: return result
        # Backward-compatible fallback for documents whose only headings are H1:
        # they become modules only when they contain their own business body.
        by_seq={block["seq"]:block for block in blocks}; result=[]
        for section in sections:
            selected=[by_seq[seq] for seq in section["block_sequences"]]
            body=[block for block in selected if block["block_type"] in {"paragraph","list","table","code","image"}]
            if section["level"] == 1 and body:
                result.append({"name":section["title"][:255],"description":" ".join(block["content"].strip() for block in body if block["content"].strip())[:1000],"source_block_ids":[],"source_seqs":[block["seq"] for block in selected],"split_method":"heading"})
        if result: return result
    if not blocks: return []
    boundaries=[index for index, block in enumerate(blocks) if re.match(r"^(?:\d+(?:\.\d+)*|REQ[-_A-Z0-9]+)[、.\s-]+", block["content"].strip(), re.I)]
    if boundaries:
        result=[]
        for offset, start in enumerate(boundaries):
            selected=blocks[start:boundaries[offset + 1] if offset + 1 < len(boundaries) else len(blocks)]
            result.append({"name":selected[0]["content"][:255], "description":" ".join(block["content"] for block in selected[1:] if block["content"])[:1000], "source_block_ids":[], "source_seqs":[block["seq"] for block in selected], "split_method":"rule"})
        return result
    return [{"name":"需求模块 1","description":"","source_block_ids":[],"source_seqs":[block["seq"] for block in blocks], "split_method":"rule"}]


def ai_module_candidates(payload: object, blocks: list[dict]) -> list[dict]:
    """Validate structured AI output against only the supplied document blocks."""
    if not isinstance(payload, dict) or not isinstance(payload.get("modules"), list):
        raise ValueError("AI module payload must contain modules")
    known = {block["seq"] for block in blocks}
    result=[]
    for item in payload["modules"]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError("AI module name is invalid")
        seqs=item.get("source_block_sequences")
        if not isinstance(seqs, list) or not seqs or any(isinstance(seq, bool) or not isinstance(seq, int) or seq not in known for seq in seqs):
            raise ValueError("AI module references invalid source blocks")
        confidence=item.get("confidence")
        if confidence is not None and (not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
            raise ValueError("AI confidence is invalid")
        result.append({"name":item["name"].strip()[:255], "description":str(item.get("description") or "")[:1000], "source_seqs":list(dict.fromkeys(seqs)), "split_method":"ai", "status":"ai", "confidence":confidence})
    return result

def validate_module_candidates(candidates: list[dict], blocks: list[dict]) -> tuple[list[dict], dict]:
    """Server-side admission control. Invalid candidates never invalidate valid AI work."""
    known={block["seq"] for block in blocks}; claimed={}; valid=[]; invalid=[]
    for candidate in candidates:
        seqs=list(dict.fromkeys(candidate.get("source_seqs") or []))
        bad=[seq for seq in seqs if seq not in known]
        overlaps=[seq for seq in seqs if seq in claimed]
        if not seqs or bad or overlaps:
            invalid.append({"name":candidate.get("name", "未命名模块"),"reason":"empty_source" if not seqs else "invalid_seq" if bad else "duplicate_source","source_seqs":seqs})
            continue
        valid.append({**candidate,"source_seqs":seqs})
        for seq in seqs: claimed[seq]=candidate.get("name", "")
    context=[block["seq"] for block in blocks if block.get("block_type")=="heading" and int((block.get("structured_content") or {}).get("level", 6)) == 1]
    business={block["seq"] for block in blocks if block.get("block_type") in {"paragraph","list","table","code","image"}}
    covered=set(claimed)
    return valid, {"covered_blocks":sorted(covered),"uncovered_blocks":sorted(business-covered),"duplicated_blocks":sorted({seq for item in invalid if item["reason"]=="duplicate_source" for seq in item["source_seqs"] if seq in claimed}),"invalid_blocks":sorted({seq for item in invalid if item["reason"]=="invalid_seq" for seq in item["source_seqs"] if seq not in known}),"empty_modules":[item["name"] for item in invalid if item["reason"]=="empty_source"],"context_blocks":context,"invalid_modules":invalid,"module_status":{item["name"]:item.get("status", item.get("split_method", "ai")) for item in valid}}


def module_split_response_schema() -> dict:
    return {
        "type": "object",
        "required": ["modules"],
        "properties": {
            "modules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "source_block_sequences"],
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "source_block_sequences": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "integer"}},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
        },
    }
