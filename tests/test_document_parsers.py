import tempfile
import unittest
import zipfile
from pathlib import Path

from ingestion.documents import DocxParser, PyMuPDFParser, parse_document


class FakePage:
    def __init__(self, body: str, *, image_xref: int | None = None) -> None:
        self.body = body
        self.image_xref = image_xref

    def get_text(self, kind: str) -> list[tuple[object, ...]]:
        self_kind = kind
        if self_kind != "blocks":
            raise AssertionError(f"unexpected text kind: {kind}")
        return [
            (0, 0, 100, 10, "课程讲义", 0, 0),
            (0, 40, 500, 100, self.body, 1, 0),
            (0, 700, 100, 710, "第 1 页", 2, 0),
        ]

    def get_images(self, *, full: bool) -> list[tuple[int, ...]]:
        self_full = full
        if not self_full or self.image_xref is None:
            return []
        return [(self.image_xref,)]


class FakePdfDocument:
    def __init__(self) -> None:
        self.pages = [
            FakePage("第一章正文", image_xref=7),
            FakePage("第二章正文", image_xref=7),
            FakePage("第三章正文"),
        ]

    def __iter__(self):
        return iter(self.pages)

    def extract_image(self, xref: int) -> dict[str, object]:
        self.assert_xref = xref
        return {"image": b"image-bytes", "ext": "png"}

    def close(self) -> None:
        self.closed = True


class DocumentParserTests(unittest.TestCase):
    def test_pdf_parser_removes_repeated_edges_and_extracts_images(self) -> None:
        document = FakePdfDocument()
        parser = PyMuPDFParser(open_document=lambda _: document)

        result = parser.parse(Path("manual.pdf"))

        self.assertEqual([block.text for block in result.blocks], [
            "第一章正文",
            "第二章正文",
            "第三章正文",
        ])
        self.assertEqual([block.page for block in result.blocks], [1, 2, 3])
        self.assertEqual(len(result.images), 1)
        self.assertEqual(result.images[0].data, b"image-bytes")
        self.assertEqual(result.images[0].page, 1)
        self.assertTrue(document.closed)

    def test_docx_parser_keeps_heading_paragraph_table_and_images(self) -> None:
        document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>配置说明</w:t></w:r></w:p>
            <w:p><w:r><w:t>安装 Redis 并启动服务。</w:t></w:r></w:p>
            <w:tbl>
              <w:tr><w:tc><w:p><w:r><w:t>字段</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>含义</w:t></w:r></w:p></w:tc></w:tr>
              <w:tr><w:tc><w:p><w:r><w:t>status</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>状态</w:t></w:r></w:p></w:tc></w:tr>
            </w:tbl>
          </w:body>
        </w:document>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", document_xml)
                archive.writestr("word/media/image1.png", b"png-data")

            result = DocxParser().parse(path)

        self.assertEqual(result.blocks[0].heading, "配置说明")
        self.assertEqual(result.blocks[0].text, "安装 Redis 并启动服务。")
        self.assertIn("| 字段 | 含义 |", result.blocks[1].text)
        self.assertEqual(result.blocks[1].extra["block_type"], "table")
        self.assertEqual(result.images[0].extension, "png")

    def test_parse_document_dispatches_and_rejects_unknown_extension(self) -> None:
        parser = object()
        with self.assertRaisesRegex(ValueError, "unsupported document type"):
            parse_document(Path("notes.txt"), pdf_parser=parser, docx_parser=parser)


if __name__ == "__main__":
    unittest.main()
