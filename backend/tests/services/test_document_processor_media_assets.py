import base64
import zipfile
from uuid import uuid4

import pytest

from app.services.document_processor import DocumentProcessor
from app.models.knowledge_base import DocumentType


def test_replace_embedded_media_data_uris_saves_assets(tmp_path):
    processor = DocumentProcessor(upload_dir=str(tmp_path / "documents"))
    kb_id = uuid4()
    document_id = uuid4()
    image_content = b"image-bytes"
    data_uri = "data:image/png;base64," + base64.b64encode(image_content).decode(
        "ascii"
    )

    text, assets = processor.replace_embedded_media_data_uris(
        f"before ![sample]({data_uri}) after",
        kb_id=kb_id,
        document_id=document_id,
    )

    assert data_uri not in text
    assert f"/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/media/" in text
    assert len(assets) == 1
    assert assets[0]["content_type"] == "image/png"
    assert assets[0]["size"] == len(image_content)
    assert (
        processor.get_media_asset_path(
            kb_id, document_id, assets[0]["filename"]
        ).read_bytes()
        == image_content
    )


@pytest.mark.asyncio
async def test_extract_text_resourceizes_markdown_data_uri_when_context_is_provided(
    tmp_path,
):
    processor = DocumentProcessor(upload_dir=str(tmp_path / "documents"))
    kb_id = uuid4()
    document_id = uuid4()
    image_content = b"image-bytes"
    data_uri = "data:image/png;base64," + base64.b64encode(image_content).decode(
        "ascii"
    )
    markdown_path = processor.get_storage_path(kb_id, "sample.md")

    with open(markdown_path, "w", encoding="utf-8") as file:
        file.write(f"# Title\n\n![sample]({data_uri})")

    text, metadata = await processor.extract_text(
        markdown_path,
        DocumentType.MD.value,
        kb_id=kb_id,
        document_id=document_id,
    )

    assert data_uri not in text
    assert metadata["media_assets"][0]["content_type"] == "image/png"
    assert metadata["media_assets"][0]["size"] == len(image_content)


@pytest.mark.asyncio
async def test_extract_text_resourceizes_docx_embedded_image(tmp_path):
    processor = DocumentProcessor(upload_dir=str(tmp_path / "documents"))
    kb_id = uuid4()
    document_id = uuid4()
    image_content = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1Pe"
        "AAAADUlEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
    )
    docx_path = processor.get_storage_path(kb_id, "sample.docx")
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    document_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>"""
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    <w:p><w:r><w:t>Before image</w:t></w:r></w:p>
    <w:p><w:r><w:drawing><wp:inline><wp:docPr id="1" name="Picture 1" descr="red pixel"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="sample.png" descr="red pixel"/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rId1"/></pic:blipFill><pic:spPr/></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>
    <w:p><w:r><w:t>After image</w:t></w:r></w:p>
  </w:body>
</w:document>"""

    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("word/media/image1.png", image_content)

    text, metadata = await processor.extract_text(
        docx_path,
        DocumentType.DOCX.value,
        kb_id=kb_id,
        document_id=document_id,
    )

    assert "data:image/png;base64" not in text
    assert f"/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/media/" in text
    assert metadata["media_assets"][0]["content_type"] == "image/png"
