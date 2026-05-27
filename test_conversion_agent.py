import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agente_conversion
from api.events import _read_payload


class FakeHandler:
    def __init__(self, body: str, content_type: str = "text/plain;charset=UTF-8"):
        self.headers = {"content-length": str(len(body.encode("utf-8"))), "content-type": content_type}
        self.rfile = io.BytesIO(body.encode("utf-8"))


class ConversionAgentTests(unittest.TestCase):
    def test_sendbeacon_text_plain_json_is_parsed(self):
        payload = _read_payload(FakeHandler('{"event_type":"page_view","slug":"abc"}'))
        self.assertEqual(payload["event_type"], "page_view")
        self.assertEqual(payload["slug"], "abc")

    def test_high_traffic_low_capture_recommendation(self):
        metric = agente_conversion.enrich_metrics({
            "slug": "landing-test",
            "keyword": "landing test",
            "category": "controladores-midi",
            "page_views": 100,
            "cta_clicks": 10,
            "form_submits": 0,
            "leads": 0,
            "unsubscribes": 0,
            "emails_sent": 0,
            "emails_failed": 0,
            "email_clicks": 0,
            "sales_count": 0,
            "revenue": 0.0,
        }, 30)
        with tempfile.TemporaryDirectory() as tmp:
            feedback = Path(tmp) / "content_feedback.jsonl"
            with patch.object(agente_conversion, "CONTENT_FEEDBACK_PATH", feedback):
                rows = agente_conversion.build_recommendations([metric], min_views=50, limit=10)
        signals = {row["signal"] for row in rows}
        self.assertIn("high_traffic_low_capture", signals)

    def test_feedback_deduplicates_by_current_period(self):
        metric = agente_conversion.enrich_metrics({
            "slug": "landing-test",
            "keyword": "landing test",
            "category": "controladores-midi",
            "page_views": 100,
            "cta_clicks": 10,
            "form_submits": 0,
            "leads": 0,
            "unsubscribes": 0,
            "emails_sent": 0,
            "emails_failed": 0,
            "email_clicks": 0,
            "sales_count": 0,
            "revenue": 0.0,
        }, 30)
        with tempfile.TemporaryDirectory() as tmp:
            feedback = Path(tmp) / "content_feedback.jsonl"
            feedback.write_text(
                '{"source":"conversion","slug":"landing-test","signal":"high_traffic_low_capture","period":"'
                + agente_conversion.feedback_period()
                + '"}\n',
                encoding="utf-8",
            )
            with patch.object(agente_conversion, "CONTENT_FEEDBACK_PATH", feedback):
                rows = agente_conversion.build_recommendations([metric], min_views=50, limit=10)
        self.assertNotIn("high_traffic_low_capture", {row["signal"] for row in rows})


if __name__ == "__main__":
    unittest.main()
