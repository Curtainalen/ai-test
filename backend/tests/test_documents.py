import base64
import io
import pytest
from docx import Document
from app.errors import AppError
from app.services.documents import ai_module_candidates, build_sections, parse_document, sha256_bytes, suggest_modules, validate_filename, validate_module_candidates

def test_txt_markdown_and_docx_source_locations():
    txt=parse_document("a.txt","第一行\n\n第二行".encode()); md=parse_document("a.md",b"# Login\n- success\n```json\n{}\n```\n| A | B |\n|---|---|\n| 1 | 2 |")
    doc=Document(); doc.add_heading("用户登录",level=1); doc.add_paragraph("输入账号密码"); stream=io.BytesIO(); doc.save(stream); dx=parse_document("a.docx",stream.getvalue())
    assert txt[1]["source_locator"]["line_start"]==3
    assert [b["block_type"] for b in md]==["heading","list","code","table"]
    assert dx[0]["block_type"]=="heading" and dx[0]["source_locator"]["paragraph_index"]==0

def test_filename_hash_and_doc_is_accepted_for_fallback_parsing():
    assert sha256_bytes(b"x")==sha256_bytes(b"x")
    assert validate_filename("legacy.doc")[1] == ".doc"
    with pytest.raises(AppError): validate_filename("../a.txt")

def test_heading_and_rule_module_splitting():
    headings = parse_document("a.md", b"# Login\naccount access\n# Orders\ncreate order")
    result = suggest_modules(headings)
    assert [item["name"] for item in result] == ["Login", "Orders"]
    assert all(item["split_method"] == "heading" for item in result)
    rules = parse_document("a.txt", "1. Login\nlogin detail\n2. Orders\norder detail".encode())
    assert len(suggest_modules(rules)) == 2

def test_ai_module_json_validation_rejects_invalid_sources_for_fallback():
    blocks = parse_document("a.txt", b"login")
    with pytest.raises(ValueError):
        ai_module_candidates({"modules": [{"name": "Login", "source_block_sequences": [99]}]}, blocks)


def test_docx_preserves_body_order_and_keeps_image_payload(tmp_path):
    image_path = tmp_path / "pixel.png"
    image_path.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Jf9cAAAAASUVORK5CYII="))
    doc = Document(); doc.add_paragraph("开头"); doc.add_picture(str(image_path)); table = doc.add_table(rows=1, cols=2); table.cell(0, 0).text = "字段"; table.cell(0, 1).text = "说明"; doc.add_paragraph("结尾")
    stream = io.BytesIO(); doc.save(stream)
    blocks = parse_document("ordered.docx", stream.getvalue())
    assert [item["block_type"] for item in blocks] == ["paragraph", "image", "table", "paragraph"]
    assert blocks[1]["content"] == "![图片](docimg://img_000)"
    assert blocks[1]["structured_content"]["_image_bytes"]

def test_h1_parent_title_is_context_when_h2_sections_have_content():
    blocks = parse_document("a.md", b"# Account\n## Login\nUse credentials\n## Logout\nEnd session")
    sections, context = build_sections(blocks)
    modules = suggest_modules(blocks)
    assert context == [1]
    assert [item["name"] for item in modules] == ["Login", "Logout"]
    assert all(item["source_seqs"] for item in modules)
    assert len(sections) == 3

def test_candidate_validation_preserves_valid_ai_modules_and_reports_bad_ones():
    blocks = parse_document("a.txt", b"login\norders")
    valid, report = validate_module_candidates([
        {"name": "Login", "source_seqs": [1], "split_method": "ai", "status": "ai"},
        {"name": "Duplicate", "source_seqs": [1], "split_method": "ai", "status": "ai"},
        {"name": "Empty", "source_seqs": [], "split_method": "ai", "status": "ai"},
    ], blocks)
    assert [item["name"] for item in valid] == ["Login"]
    assert report["duplicated_blocks"] == [1]
    assert report["empty_modules"] == ["Empty"]
    assert report["uncovered_blocks"] == [2]
