"""
Ananta Meridian — LLM Operator Layer
=====================================
Converts structured fusion engine outputs into plain-language operator
guidance using the Anthropic API (Claude).

This is the interpretability/decision-support layer of the Ananta Meridian
architecture. It sits above the confidence engine and translates machine-level
confidence states into operator-ready situational summaries.

Usage
-----
    from llm_operator_layer import generate_operator_guidance

    result = generate_operator_guidance(
        fusion_result=fusion,
        sensor_data=sensors,
        mission_context="Arctic maritime patrol"
    )
    print(result["operator_summary"])

Design principles
-----------------
- Policy-aware: framed for CAF / DND decision-support context
- No speculation: output is grounded only in fusion engine evidence
- Graceful degradation: falls back to rule-based summary if API unavailable
- Auditable: all inputs and outputs are structured dicts; nothing is opaque
- Stateless: each call is independent; no session state

Environment
-----------
Set ANTHROPIC_API_KEY in your environment or in a .env file.
See .env.example for the template.
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Load .env if present (no-op if python-dotenv not installed or .env absent)
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)   # override=True: .env wins over existing env vars
except ImportError:
    pass

# Import Anthropic at module level so tests can mock it cleanly.
# _ANTHROPIC_AVAILABLE tracks whether the package is installed.
try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _anthropic = None           # type: ignore[assignment]
    _ANTHROPIC_AVAILABLE = False

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
_MODEL = "claude-sonnet-4-5"   # Claude Sonnet — cost-efficient for operator guidance

_SYSTEM_PROMPT = """You are an operational decision-support assistant embedded \
in a Canadian Armed Forces (CAF) degraded-sensor fusion system. Your role is \
to translate machine-generated sensor fusion confidence assessments into \
concise, policy-appropriate operator guidance.

Rules you must follow:
1. Base all analysis ONLY on the sensor data and fusion result provided. \
   Do not speculate beyond the evidence.
2. Use plain, direct language suitable for an operational commander. \
   No jargon, no hedging phrases like "it seems" or "perhaps".
3. Respect CAF operational context: outputs may influence patrol, \
   interception, or standby decisions. Be accurate and conservative.
4. Flag escalation only when confidence is LOW or when sensors show \
   active disagreement or spoofing indicators.
5. Keep operator_summary to 2-3 sentences maximum.
6. Always respond with valid JSON matching the schema provided.
"""

_USER_TEMPLATE = """Fusion engine output and raw sensor data are provided below. \
Generate operator guidance in JSON.

FUSION RESULT:
{fusion_json}

RAW SENSOR DATA:
{sensor_json}

MISSION CONTEXT: {mission_context}

Respond with ONLY a JSON object with these exact keys:
{{
  "operator_summary": "<2-3 sentence plain-language situational summary>",
  "threat_indicators": ["<indicator 1>", "..."],
  "recommended_actions": ["<action 1>", "..."],
  "confidence_rationale": "<1-2 sentences explaining why this confidence level was assigned>",
  "escalation_required": <true|false>
}}
"""

# ---------------------------------------------------------------------------
# Fallback (rule-based) output when API is unavailable
# ---------------------------------------------------------------------------

def _rule_based_fallback(fusion_result: dict, sensor_data: list, mission_context: str) -> dict:
    """
    Construct a deterministic operator summary from fusion engine outputs.
    Used when the Anthropic API is unavailable or returns an error.
    This ensures the operator always receives actionable output.
    """
    level = fusion_result.get("confidence_level", "UNKNOWN")
    reasons = fusion_result.get("reasons", [])
    actions = fusion_result.get("recommended_actions", [])
    detected = fusion_result.get("fused_detection", False)
    score = fusion_result.get("weighted_score", 0.0)

    detection_str = "target detected" if detected else "no target detected"

    summary_map = {
        "HIGH":   (f"Fusion confidence is HIGH. {detection_str.capitalize()} with strong sensor agreement "
                   f"(score {score:.2f}). Sensor picture is reliable for decision-making."),
        "MEDIUM": (f"Fusion confidence is MEDIUM. {detection_str.capitalize()} (score {score:.2f}). "
                   f"Some sensors are degraded; treat picture as indicative rather than definitive."),
        "LOW":    (f"Fusion confidence is LOW. {detection_str.capitalize()} (score {score:.2f}). "
                   f"Sensor picture is unreliable. Do not act on detection without corroboration."),
    }

    summary = summary_map.get(level,
        f"Confidence level {level}. {detection_str.capitalize()} (score {score:.2f}).")

    threat_indicators = [r for r in reasons if any(
        kw in r.lower() for kw in ("disagreement", "spoof", "stale", "loss", "degraded", "low quality")
    )]

    escalation = (level == "LOW") or bool(threat_indicators)

    return {
        "operator_summary":     summary,
        "threat_indicators":    threat_indicators or ["None identified"],
        "recommended_actions":  actions if actions else ["Monitor and await updated sensor data"],
        "confidence_rationale": "; ".join(reasons) if reasons else f"Confidence level: {level}",
        "escalation_required":  escalation,
        "_source":              "rule_based_fallback",
    }


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def generate_operator_guidance(
    fusion_result: dict,
    sensor_data: list,
    mission_context: str = "Arctic maritime",
) -> dict:
    """
    Generate operator guidance from fusion engine output using Claude.

    Parameters
    ----------
    fusion_result : dict
        Output from compute_confidence() — must contain at minimum:
          confidence_level, reasons, recommended_actions, weighted_score,
          fused_detection
    sensor_data : list[dict]
        Raw sensor records for the current time step.
    mission_context : str
        Free-text description of the operational context (e.g.
        "Arctic maritime patrol", "Northwest Passage sovereignty monitoring").

    Returns
    -------
    dict with keys:
        operator_summary     : str
        threat_indicators    : list[str]
        recommended_actions  : list[str]
        confidence_rationale : str
        escalation_required  : bool
        _source              : "anthropic_api" | "rule_based_fallback"
        _model               : str  (only when source is anthropic_api)
        _error               : str  (only when fallback was triggered by error)
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set -- using rule-based fallback")
        result = _rule_based_fallback(fusion_result, sensor_data, mission_context)
        result["_error"] = "ANTHROPIC_API_KEY not configured"
        return result

    if not _ANTHROPIC_AVAILABLE or _anthropic is None:
        logger.warning("anthropic package not installed -- using rule-based fallback")
        result = _rule_based_fallback(fusion_result, sensor_data, mission_context)
        result["_error"] = "anthropic package not installed"
        return result

    client = _anthropic.Anthropic(api_key=api_key)

    user_message = _USER_TEMPLATE.format(
        fusion_json=json.dumps(fusion_result, indent=2),
        sensor_json=json.dumps(sensor_data, indent=2),
        mission_context=mission_context,
    )

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},   # cache stable system prompt
                }
            ],
            messages=[
                {"role": "user", "content": user_message}
            ],
        )

        raw_text = response.content[0].text.strip()

        # Strip markdown code fences if the model wraps JSON
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            raw_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        parsed = json.loads(raw_text)

        # Validate required keys
        required = {
            "operator_summary", "threat_indicators",
            "recommended_actions", "confidence_rationale", "escalation_required"
        }
        missing = required - set(parsed.keys())
        if missing:
            raise ValueError(f"API response missing keys: {missing}")

        parsed["_source"] = "anthropic_api"
        parsed["_model"]  = _MODEL
        return parsed

    except _anthropic.APIConnectionError as exc:
        logger.warning("Anthropic API connection error: %s -- using fallback", exc)
        result = _rule_based_fallback(fusion_result, sensor_data, mission_context)
        result["_error"] = f"APIConnectionError: {exc}"
        return result

    except _anthropic.APIStatusError as exc:
        logger.warning("Anthropic API status error %s: %s -- using fallback", exc.status_code, exc.message)
        result = _rule_based_fallback(fusion_result, sensor_data, mission_context)
        result["_error"] = f"APIStatusError {exc.status_code}: {exc.message}"
        return result

    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not parse API response: %s — using fallback", exc)
        result = _rule_based_fallback(fusion_result, sensor_data, mission_context)
        result["_error"] = f"ParseError: {exc}"
        return result

    except Exception as exc:
        logger.warning("Unexpected error calling Anthropic API: %s — using fallback", exc)
        result = _rule_based_fallback(fusion_result, sensor_data, mission_context)
        result["_error"] = f"UnexpectedError: {exc}"
        return result


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Minimal synthetic fusion result to exercise the layer end-to-end
    _DEMO_FUSION = {
        "confidence_level": "MEDIUM",
        "weighted_score": 0.61,
        "fused_detection": True,
        "reasons": [
            "High-latency sensors detected: ARCTIC_SURVEYOR (latency 2118000 ms)",
            "Low-quality sensor: FV_INUKTITUK (quality 0.45)",
        ],
        "recommended_actions": [
            "Cross-reference with NORDREG vessel tracking",
            "Increase monitoring cadence",
        ],
    }

    _DEMO_SENSORS = [
        {"sensor": "CCGS_AMUNDSEN",   "detected": True,  "quality": 0.92, "latency": 12000},
        {"sensor": "UMIAK_I",         "detected": True,  "quality": 0.88, "latency": 950000},
        {"sensor": "ARCTIC_SURVEYOR", "detected": True,  "quality": 0.71, "latency": 2118000},
        {"sensor": "FV_INUKTITUK",    "detected": False, "quality": 0.45, "latency": 3506000},
    ]

    print("=" * 68)
    print("Ananta Meridian — LLM Operator Layer Demo")
    print("=" * 68)

    guidance = generate_operator_guidance(
        fusion_result=_DEMO_FUSION,
        sensor_data=_DEMO_SENSORS,
        mission_context="Arctic maritime patrol — Northwest Passage, August 2024",
    )

    source = guidance.get("_source", "unknown")
    model  = guidance.get("_model", "N/A")
    error  = guidance.get("_error", None)

    print(f"\nSource  : {source}  |  Model: {model}")
    if error:
        print(f"[WARN] Fallback reason: {error}")

    print(f"\nOperator Summary:\n  {guidance['operator_summary']}")
    print(f"\nThreat Indicators:")
    for t in guidance["threat_indicators"]:
        print(f"  - {t}")
    print(f"\nRecommended Actions:")
    for a in guidance["recommended_actions"]:
        print(f"  - {a}")
    print(f"\nConfidence Rationale:\n  {guidance['confidence_rationale']}")
    print(f"\nEscalation Required: {guidance['escalation_required']}")
    print("=" * 68)

    sys.exit(0)
