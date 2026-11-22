import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from core.validator import validate_candidate, validate_open_codes, validate_themes
from core import llm
from core.ingest import read_file, make_chunks, source_hash
from docx import Document
from exporters.reports import export_docx, export_markdown, export_excel, export_csv


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.segments = [{
            "document_id": "sample_fgd",
            "segment_id": "sample_fgd_SEG_0001",
            "text": "Internet access is expensive and the connection is unstable."
        }]

    def test_real_quote_is_verified(self):
        result = validate_candidate({
            "document_id": "sample_fgd",
            "segment_id": "sample_fgd_SEG_0001",
            "quote": "Internet access is expensive"
        }, self.segments)
        self.assertTrue(result["verified"])
        self.assertEqual(result["verified_quote"], "Internet access is expensive")

    def test_fake_quote_is_rejected(self):
        result = validate_candidate({
            "document_id": "sample_fgd",
            "segment_id": "sample_fgd_SEG_0001",
            "quote": "A fabricated statement not in the transcript"
        }, self.segments)
        self.assertFalse(result["verified"])
        self.assertIsNone(result["verified_quote"])

    def test_unknown_segment_is_rejected(self):
        result = validate_candidate({
            "segment_id": "sample_fgd_SEG_0099",
            "quote": "Internet access is expensive"
        }, self.segments)
        self.assertFalse(result["verified"])
        self.assertEqual(result["verification_method"], "missing_segment")

    def test_docx_ingestion_and_segment_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tiny_fgd.docx"
            doc = Document()
            doc.add_paragraph("Participant 1: Internet access is expensive.")
            doc.add_paragraph("Participant 2: The connection is unstable.")
            doc.save(path)
            text = read_file(str(path))
            self.assertIn("Internet access is expensive", text)
            self.assertEqual(len(source_hash(text)), 64)
            segments = make_chunks(text, "tiny_fgd", target_chars=50, overlap=5)
            self.assertTrue(segments)
            self.assertTrue(all(x["segment_id"].startswith("tiny_fgd_SEG_") for x in segments))

    def test_code_and_theme_references_are_filtered(self):
        codes = validate_open_codes([
            {"code": "Valid code", "description": "grounded", "segment_ids": ["sample_fgd_SEG_0001", "made_up_segment"]},
            {"code": "Unsupported code", "description": "no link", "segment_ids": ["made_up_segment"]}
        ], self.segments)
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0]["segment_ids"], ["sample_fgd_SEG_0001"])
        themes = validate_themes([
            {"theme": "Supported theme", "description": "", "codes": ["Valid code", "Invented code"]},
            {"theme": "Unsupported theme", "description": "", "codes": ["Invented code"]}
        ], codes)
        self.assertEqual(len(themes), 1)
        self.assertEqual(themes[0]["codes"], ["Valid code"])

    def test_llm_pipeline_with_mocked_local_model(self):
        original = llm._call
        def fake_call(messages):
            prompt = messages[-1]["content"]
            if "OPEN CODES:" in prompt:
                return {"axial_themes": [{"theme": "Connectivity barriers", "description": "Cost and reliability issues", "codes": ["Internet cost"]}]}
            return {
                "open_codes": [{"code": "Internet cost", "description": "Internet access is expensive", "segment_ids": ["sample_fgd_SEG_0001"]}],
                "candidate_quotes": [{"segment_id": "sample_fgd_SEG_0001", "quote": "Internet access is expensive", "code": "Internet cost"}]
            }
        try:
            llm._call = fake_call
            result = llm.analyze_segments(self.segments)
            self.assertEqual(len(result["open_codes"]), 1)
            self.assertEqual(len(result["axial_themes"]), 1)
            validated = validate_candidate(result["candidate_quotes"][0], self.segments)
            self.assertTrue(validated["verified"])
        finally:
            llm._call = original

    def test_report_exports_are_nonempty_and_traceable(self):
        quote = validate_candidate({
            "document_id": "sample_fgd",
            "segment_id": "sample_fgd_SEG_0001",
            "quote": "Internet access is expensive",
            "code": "Internet cost",
            "theme": "Connectivity barriers"
        }, self.segments)
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            metadata = {"organization": "Test NGO", "purpose": "Test evidence export"}
            docs = [{"document_id": "sample_fgd", "filename": "sample_fgd.docx", "characters": 59, "sha256": "test-hash"}]
            codes = [{"code": "Internet cost", "description": "Cost is a stated barrier", "segment_ids": ["sample_fgd_SEG_0001"]}]
            themes = [{"theme": "Connectivity barriers", "description": "Cost and stability", "codes": ["Internet cost"]}]
            export_docx("Test Report", themes, [quote], temp / "report.docx", metadata=metadata, docs=docs, segments=self.segments, codes=codes, analysis_status="complete")
            export_markdown("Test Report", themes, [quote], temp / "report.md", metadata=metadata, docs=docs, segments=self.segments, codes=codes, analysis_status="complete")
            export_excel([{"verified_quote": quote["verified_quote"]}], temp / "report.xlsx", sheets={"Sources": docs, "Open Codes": codes})
            export_csv([{"verified_quote": quote["verified_quote"]}], temp / "report.csv")
            for name in ("report.docx", "report.md", "report.xlsx", "report.csv"):
                self.assertTrue((temp / name).exists(), name)
                self.assertGreater((temp / name).stat().st_size, 10, name)


if __name__ == "__main__":
    unittest.main()
