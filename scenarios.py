time_series_scenarios = {
    "gradual_degradation": [
        [
            {"sensor": "A", "detected": True, "quality": 0.92, "latency": 100},
            {"sensor": "B", "detected": True, "quality": 0.90, "latency": 110},
            {"sensor": "C", "detected": True, "quality": 0.89, "latency": 105},
        ],
        [
            {"sensor": "A", "detected": True, "quality": 0.88, "latency": 120},
            {"sensor": "B", "detected": True, "quality": 0.82, "latency": 130},
            {"sensor": "C", "detected": True, "quality": 0.70, "latency": 180},
        ],
        [
            {"sensor": "A", "detected": True, "quality": 0.80, "latency": 150},
            {"sensor": "B", "detected": False, "quality": 0.75, "latency": 200},
            {"sensor": "C", "detected": True, "quality": 0.62, "latency": 250},
        ],
        [
            {"sensor": "A", "detected": True, "quality": 0.65, "latency": 220},
            {"sensor": "B", "detected": False, "quality": 0.55, "latency": 420},
            {"sensor": "C", "detected": True, "quality": 0.50, "latency": 500},
        ],
        [
            {"sensor": "A", "detected": False, "quality": 0.45, "latency": 500},
            {"sensor": "B", "detected": False, "quality": 0.35, "latency": 650},
            {"sensor": "C", "detected": True, "quality": 0.40, "latency": 700},
        ],
    ]
}