import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from src.alerts import escalation

ALERT = {
    "event_id": "TH-ESC001",
    "risk_score": 88.0,
    "severity": "CRITICAL",
    "title": "High thermal activity in Odisha",
    "latitude": 21.52,
    "longitude": 85.11,
}


class EscalationTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(config, "ALERT_ESCALATION_PATH",
                                    Path(self._tmp.name) / "alert_escalations.json")
        patcher.start()
        self.addCleanup(patcher.stop)


class TestAcknowledgementClock(EscalationTestCase):
    def test_dispatch_starts_the_clock(self):
        entry = escalation.record_dispatch(ALERT, "9812345678")
        self.assertEqual(entry["state"], escalation.AWAITING)
        self.assertEqual(len(escalation.pending()), 1)
        self.assertEqual(escalation.due(after_minutes=0)[0]["event_id"], "TH-ESC001")
        self.assertEqual(escalation.due(after_minutes=15), [])

    def test_acknowledging_removes_it_from_the_queue(self):
        escalation.record_dispatch(ALERT, "9812345678")
        entry = escalation.acknowledge("TH-ESC001", by="analyst-2")
        self.assertEqual(entry["state"], escalation.ACKNOWLEDGED)
        self.assertEqual(entry["acknowledged_by"], "analyst-2")
        self.assertEqual(escalation.pending(), [])
        self.assertEqual(escalation.due(after_minutes=0), [])

    def test_acknowledging_an_unknown_event_returns_none(self):
        self.assertIsNone(escalation.acknowledge("TH-NOPE"))

    def test_redispatch_restarts_rather_than_queueing_twice(self):
        escalation.record_dispatch(ALERT, "9812345678")
        escalation.record_dispatch(ALERT, "9812345678")
        self.assertEqual(len(escalation.load()), 1)
        self.assertEqual(len(escalation.pending()), 1)


class TestVoiceEscalation(EscalationTestCase):
    def test_call_is_simulated_without_credentials(self):
        escalation.record_dispatch(ALERT, "9812345678")
        with mock.patch.object(config, "TWILIO_ACCOUNT_SID", ""), \
             mock.patch.object(config, "TWILIO_AUTH_TOKEN", ""):
            result = escalation.place_call(escalation.due(0)[0])
        self.assertEqual(result["status"], "simulated")
        self.assertEqual(result["recipient"], "+919812345678")

    def test_a_called_alert_never_dials_twice(self):
        escalation.record_dispatch(ALERT, "9812345678")
        escalation.place_call(escalation.due(0)[0])
        self.assertEqual(escalation.pending(), [])
        self.assertEqual(escalation.escalate_due(after_minutes=0), [])

    def test_escalate_due_calls_every_overdue_alert_once(self):
        escalation.record_dispatch(ALERT, "9812345678")
        escalation.record_dispatch({**ALERT, "event_id": "TH-ESC002"}, "9812345678")
        results = escalation.escalate_due(after_minutes=0)
        self.assertEqual(len(results), 2)
        self.assertEqual({r["status"] for r in results}, {"simulated"})
        self.assertEqual(escalation.escalate_due(after_minutes=0), [])

    def test_a_failed_call_stays_in_the_queue_for_a_retry(self):
        escalation.record_dispatch(ALERT, "9812345678")
        with mock.patch.object(config, "TWILIO_ACCOUNT_SID", "AC123"), \
             mock.patch.object(config, "TWILIO_AUTH_TOKEN", "tok"), \
             mock.patch.object(config, "TWILIO_VOICE_FROM_NUMBER", "+15550001111"), \
             mock.patch("src.alerts.escalation.requests.post", side_effect=Exception("network down")):
            result = escalation.place_call(escalation.due(0)[0])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(escalation.pending()), 1)

    def test_script_says_it_is_unverified_and_names_the_event(self):
        entry = escalation.record_dispatch(ALERT, "9812345678")
        script = escalation.call_script(entry)
        self.assertIn("TH-ESC001", script)
        self.assertIn("not a confirmed fire", script)

    def test_twiml_strips_markup_from_the_script(self):
        xml = escalation._twiml('Alert <script>alert("x")</script> & more')
        self.assertNotIn("<script>", xml)
        self.assertNotIn("&", xml.replace("&amp;", ""))
        self.assertTrue(xml.startswith("<Response>"))


if __name__ == "__main__":
    unittest.main()
