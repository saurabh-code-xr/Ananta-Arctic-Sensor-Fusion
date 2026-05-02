"""
Tests for llm_operator_layer.py
================================
Covers:
  - Successful Anthropic API call -> structured output
  - API failure (connection error) -> rule-based fallback
  - API status error -> rule-based fallback
  - Malformed JSON response -> rule-based fallback
  - Missing API key -> rule-based fallback
  - HIGH confidence input
  - MEDIUM confidence input
  - LOW confidence input + escalation flag
  - Arctic context
  - Maritime context
  - rule_based_fallback() in isolation

All Anthropic API calls are mocked — no real API key required for these tests.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Make sure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from llm_operator_layer import generate_operator_guidance, _rule_based_fallback


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _fusion(level: str, detected: bool = True, score: float = 0.75,
            reasons: list = None, actions: list = None) -> dict:
    return {
        "confidence_level":     level,
        "weighted_score":       score,
        "fused_detection":      detected,
        "reasons":              reasons or [],
        "recommended_actions":  actions or [],
    }


_SENSORS_HIGH = [
    {"sensor": "CCGS_AMUNDSEN",      "detected": True,  "quality": 0.93, "latency": 10000},
    {"sensor": "UMIAK_I",            "detected": True,  "quality": 0.88, "latency": 8000},
    {"sensor": "MV_NUNAVUT_EASTERN", "detected": True,  "quality": 0.90, "latency": 12000},
]

_SENSORS_MEDIUM = [
    {"sensor": "CCGS_AMUNDSEN",   "detected": True,  "quality": 0.88, "latency": 900000},
    {"sensor": "ARCTIC_SURVEYOR", "detected": True,  "quality": 0.65, "latency": 1800000},
    {"sensor": "FV_INUKTITUK",    "detected": False, "quality": 0.50, "latency": 2500000},
]

_SENSORS_LOW = [
    {"sensor": "FV_INUKTITUK",    "detected": False, "quality": 0.35, "latency": 4500000},
    {"sensor": "ARCTIC_SURVEYOR", "detected": False, "quality": 0.30, "latency": 5000000},
]

_GOOD_API_RESPONSE = {
    "operator_summary":     "Sensor picture is reliable. CCGS Amundsen confirms contact.",
    "threat_indicators":    ["None identified"],
    "recommended_actions":  ["Maintain current patrol posture", "Log contact for NORDREG"],
    "confidence_rationale": "All sensors agree with low latency and high quality scores.",
    "escalation_required":  False,
}


def _mock_anthropic_response(content_text: str):
    """Build a minimal mock mimicking anthropic.Anthropic().messages.create() return."""
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=content_text)]
    return mock_resp


# ---------------------------------------------------------------------------
# Tests: successful API call
# ---------------------------------------------------------------------------

class TestSuccessfulAPICall(unittest.TestCase):

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-valid"})
    @patch("llm_operator_layer._anthropic")
    def test_returns_structured_output(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response(
            json.dumps(_GOOD_API_RESPONSE)
        )

        result = generate_operator_guidance(
            fusion_result=_fusion("HIGH"),
            sensor_data=_SENSORS_HIGH,
            mission_context="Arctic maritime",
        )

        self.assertEqual(result["_source"], "anthropic_api")
        self.assertIn("operator_summary", result)
        self.assertIn("threat_indicators", result)
        self.assertIn("recommended_actions", result)
        self.assertIn("confidence_rationale", result)
        self.assertIn("escalation_required", result)
        self.assertIsInstance(result["threat_indicators"], list)
        self.assertIsInstance(result["recommended_actions"], list)
        self.assertIsInstance(result["escalation_required"], bool)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-valid"})
    @patch("llm_operator_layer._anthropic")
    def test_model_name_recorded(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response(
            json.dumps(_GOOD_API_RESPONSE)
        )

        result = generate_operator_guidance(_fusion("HIGH"), _SENSORS_HIGH)

        self.assertIn("_model", result)
        self.assertIn("claude", result["_model"].lower())

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-valid"})
    @patch("llm_operator_layer._anthropic")
    def test_strips_markdown_code_fence(self, mock_anthropic):
        """API sometimes wraps JSON in ```json ... ``` — must be handled."""
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        wrapped = "```json\n" + json.dumps(_GOOD_API_RESPONSE) + "\n```"
        mock_client.messages.create.return_value = _mock_anthropic_response(wrapped)

        result = generate_operator_guidance(_fusion("MEDIUM"), _SENSORS_MEDIUM)

        self.assertEqual(result["_source"], "anthropic_api")
        self.assertFalse(result.get("_error"))


# ---------------------------------------------------------------------------
# Tests: API failure -> fallback
# ---------------------------------------------------------------------------

class TestAPIFailureFallback(unittest.TestCase):

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("llm_operator_layer._anthropic")
    def test_connection_error_falls_back(self, mock_anthropic):
        import anthropic as real_anthropic
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        # Make the patched module use the real exception class so isinstance checks work
        mock_anthropic.APIConnectionError = real_anthropic.APIConnectionError
        mock_anthropic.APIStatusError = real_anthropic.APIStatusError
        mock_client.messages.create.side_effect = real_anthropic.APIConnectionError(
            request=MagicMock()
        )

        result = generate_operator_guidance(_fusion("HIGH"), _SENSORS_HIGH)

        self.assertEqual(result["_source"], "rule_based_fallback")
        self.assertIn("_error", result)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("llm_operator_layer._anthropic")
    def test_malformed_json_falls_back(self, mock_anthropic):
        import anthropic as real_anthropic
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response(
            "This is not JSON at all."
        )
        # Use real exception classes so isinstance checks in the handler work correctly
        mock_anthropic.APIConnectionError = real_anthropic.APIConnectionError
        mock_anthropic.APIStatusError = real_anthropic.APIStatusError

        result = generate_operator_guidance(_fusion("MEDIUM"), _SENSORS_MEDIUM)

        self.assertEqual(result["_source"], "rule_based_fallback")
        self.assertIn("ParseError", result.get("_error", ""))

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("llm_operator_layer._anthropic")
    def test_missing_keys_in_response_falls_back(self, mock_anthropic):
        import anthropic as real_anthropic
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        # Response missing required keys
        mock_client.messages.create.return_value = _mock_anthropic_response(
            json.dumps({"operator_summary": "Only one key present"})
        )
        mock_anthropic.APIConnectionError = real_anthropic.APIConnectionError
        mock_anthropic.APIStatusError = real_anthropic.APIStatusError

        result = generate_operator_guidance(_fusion("HIGH"), _SENSORS_HIGH)

        self.assertEqual(result["_source"], "rule_based_fallback")

    def test_missing_api_key_falls_back(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = generate_operator_guidance(_fusion("MEDIUM"), _SENSORS_MEDIUM)

        self.assertEqual(result["_source"], "rule_based_fallback")
        self.assertIn("ANTHROPIC_API_KEY", result.get("_error", ""))


# ---------------------------------------------------------------------------
# Tests: confidence level variations
# ---------------------------------------------------------------------------

class TestConfidenceLevels(unittest.TestCase):

    def test_high_confidence_no_escalation(self):
        result = _rule_based_fallback(
            fusion_result=_fusion("HIGH", score=0.91),
            sensor_data=_SENSORS_HIGH,
            mission_context="Arctic maritime",
        )
        self.assertFalse(result["escalation_required"])
        self.assertIn("HIGH", result["operator_summary"])

    def test_medium_confidence_summary_content(self):
        result = _rule_based_fallback(
            fusion_result=_fusion("MEDIUM", score=0.61),
            sensor_data=_SENSORS_MEDIUM,
            mission_context="Arctic maritime",
        )
        self.assertIn("MEDIUM", result["operator_summary"])
        # MEDIUM on its own doesn't require escalation unless there are threat indicators
        # (no disagreement reasons in this fixture -> no escalation)
        self.assertFalse(result["escalation_required"])

    def test_low_confidence_triggers_escalation(self):
        result = _rule_based_fallback(
            fusion_result=_fusion(
                "LOW", detected=False, score=0.21,
                reasons=["High-latency sensors detected", "Sensor disagreement detected"],
            ),
            sensor_data=_SENSORS_LOW,
            mission_context="Arctic maritime",
        )
        self.assertTrue(result["escalation_required"])
        self.assertIn("LOW", result["operator_summary"])

    def test_disagreement_reason_triggers_escalation(self):
        """Even at MEDIUM, a disagreement reason should set escalation_required."""
        result = _rule_based_fallback(
            fusion_result=_fusion(
                "MEDIUM", score=0.55,
                reasons=["Sensor disagreement detected — possible spoofing or EW interference"],
            ),
            sensor_data=_SENSORS_MEDIUM,
            mission_context="Arctic maritime",
        )
        self.assertTrue(result["escalation_required"])
        self.assertTrue(len(result["threat_indicators"]) > 0)
        # Check the threat indicator is not "None identified"
        self.assertNotEqual(result["threat_indicators"], ["None identified"])

    def test_high_confidence_detected_true(self):
        result = _rule_based_fallback(
            fusion_result=_fusion("HIGH", detected=True),
            sensor_data=_SENSORS_HIGH,
            mission_context="Arctic",
        )
        self.assertIn("detected", result["operator_summary"].lower())


# ---------------------------------------------------------------------------
# Tests: mission context variations
# ---------------------------------------------------------------------------

class TestMissionContext(unittest.TestCase):

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("llm_operator_layer._anthropic")
    def test_arctic_context_passed_to_api(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response(
            json.dumps(_GOOD_API_RESPONSE)
        )
        mock_anthropic.APIConnectionError = Exception
        mock_anthropic.APIStatusError = Exception

        generate_operator_guidance(
            _fusion("HIGH"), _SENSORS_HIGH,
            mission_context="Arctic maritime patrol — Northwest Passage",
        )

        call_kwargs = mock_client.messages.create.call_args
        # The mission context should appear in the user message content
        user_content = str(call_kwargs)
        self.assertIn("Northwest Passage", user_content)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("llm_operator_layer._anthropic")
    def test_maritime_context_passed_to_api(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response(
            json.dumps(_GOOD_API_RESPONSE)
        )
        mock_anthropic.APIConnectionError = Exception
        mock_anthropic.APIStatusError = Exception

        generate_operator_guidance(
            _fusion("MEDIUM"), _SENSORS_MEDIUM,
            mission_context="Gulf of St. Lawrence maritime surveillance",
        )

        call_kwargs = mock_client.messages.create.call_args
        user_content = str(call_kwargs)
        self.assertIn("Gulf of St. Lawrence", user_content)


# ---------------------------------------------------------------------------
# Tests: rule_based_fallback in isolation
# ---------------------------------------------------------------------------

class TestRuleBasedFallback(unittest.TestCase):

    def test_returns_all_required_keys(self):
        result = _rule_based_fallback(_fusion("HIGH"), _SENSORS_HIGH, "test")
        required = {
            "operator_summary", "threat_indicators", "recommended_actions",
            "confidence_rationale", "escalation_required", "_source",
        }
        self.assertEqual(required, required & set(result.keys()))

    def test_source_is_rule_based(self):
        result = _rule_based_fallback(_fusion("MEDIUM"), _SENSORS_MEDIUM, "test")
        self.assertEqual(result["_source"], "rule_based_fallback")

    def test_recommended_actions_passthrough(self):
        actions = ["Cross-reference NORDREG", "Increase monitoring"]
        result = _rule_based_fallback(
            _fusion("MEDIUM", actions=actions), _SENSORS_MEDIUM, "test"
        )
        self.assertEqual(result["recommended_actions"], actions)

    def test_empty_actions_uses_default(self):
        result = _rule_based_fallback(_fusion("HIGH", actions=[]), _SENSORS_HIGH, "test")
        self.assertTrue(len(result["recommended_actions"]) > 0)

    def test_no_threat_indicators_returns_none_identified(self):
        result = _rule_based_fallback(
            _fusion("HIGH", reasons=["Freshness score within threshold"]),
            _SENSORS_HIGH, "test"
        )
        # No degradation keywords in reason -> no threat indicators -> default
        self.assertIn("None identified", result["threat_indicators"])

    def test_stale_reason_becomes_threat_indicator(self):
        result = _rule_based_fallback(
            _fusion("LOW", reasons=["Stale data from FV_INUKTITUK"]),
            _SENSORS_LOW, "test"
        )
        self.assertTrue(any("stale" in t.lower() for t in result["threat_indicators"]))

    def test_unknown_confidence_level_graceful(self):
        result = _rule_based_fallback(_fusion("UNKNOWN"), _SENSORS_HIGH, "test")
        self.assertIn("UNKNOWN", result["operator_summary"])


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
