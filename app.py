from scenarios import time_series_scenarios
from fusion_engine import fuse_sensors
from confidence_engine import compute_confidence
from reliability_memory import update_reliability_history

print("\nDEGRADED SENSING TIME-SERIES DEMO — V3 RELIABILITY-AWARE FUSION\n")

scenario_name = "gradual_degradation"
scenario_steps = time_series_scenarios[scenario_name]

confidence_history = []
reliability_history = {}

for i, sensor_data in enumerate(scenario_steps, start=1):
    print(f"\n===== TIME STEP {i} =====")

    print("\n--- SENSOR INPUTS ---")
    print(sensor_data)

    fusion = fuse_sensors(sensor_data, reliability_history=reliability_history)

    print("\n--- FUSION RESULT ---")
    print("Fused detection:", fusion["fused_detection"])
    print("Raw weighted detection score:", fusion["raw_weighted_detection_score"])
    print("Disagreement penalty:", fusion["disagreement_penalty"])
    print("Final weighted detection score:", fusion["weighted_detection_score"])
    print("Detected count:", fusion["detected_count"])
    print("Average quality:", fusion["avg_quality"])
    print("Average latency:", fusion["avg_latency"])
    print("Disagreement:", fusion["disagreement"])

    print("\nPer-sensor weights:")
    for sensor_name, details in fusion["per_sensor_weights"].items():
        print(f"- {sensor_name}: {details}")

    confidence = compute_confidence(fusion, sensor_data)
    confidence_history.append(confidence["level"])

    print("\n--- CONFIDENCE ASSESSMENT ---")
    print("Level:", confidence["level"])
    print("Weighted score:", confidence["weighted_score"])

    print("\nReasons:")
    for reason in confidence["reasons"]:
        print("-", reason)

    print("\nRecommended Actions:")
    for action in confidence["actions"]:
        print("-", action)

    reliability_history = update_reliability_history(reliability_history, sensor_data)

print("\n===== CONFIDENCE HISTORY =====")
for idx, level in enumerate(confidence_history, start=1):
    print(f"Time {idx}: {level}")

if "LOW" in confidence_history:
    first_low = confidence_history.index("LOW") + 1
    print(f"\n⚠ Confidence collapse detected at Time Step {first_low}")
else:
    print("\nNo confidence collapse detected.")

print("\n===== RELIABILITY HISTORY =====")
for sensor_name, samples in reliability_history.items():
    rounded_samples = [round(x, 3) for x in samples]
    print(f"{sensor_name}: {rounded_samples}")