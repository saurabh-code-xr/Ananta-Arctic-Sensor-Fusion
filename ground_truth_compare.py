"""
Ground-truth comparison -- the module that turns a simulated testbed run
into a measured validation result.

Given (a) a log of the system's own estimated position over time and
(b) an independent ground-truth position log (a facility survey, total
station track, or known waypoint sequence), this computes REAL position
error at each timestep and reports whether confidence degradation
preceded a significant error crossing -- the "early warning lead time"
metric used in analyze_norcat_testbed.py's simulated run, now computed
against measured error instead of a drift model.

This module is deliberately independent of fuse_sensors / compute_confidence:
it is a post-hoc comparison layer that answers "did HIGH/MEDIUM/LOW track
with reality?", not a part of the fusion pipeline itself. That separation
matters -- it means the validation isn't circular (the engine never sees
the ground truth, and this module never influences the engine's output).

Minimum you need from NORCAT to use this:
  1. An estimated-position log: (t, x, y) from whatever nav stack produced
     position estimates during the run (yours or theirs).
  2. A ground-truth log: (t, x, y) from a survey/total-station/known
     waypoint track for the same run, same time base.
Both load with the same load_position_log() -- it's a plain (t_s, x_m, y_m)
CSV with a header row.
"""

import bisect
import csv


def load_position_log(csv_path: str, time_col="t_s", x_col="x_m", y_col="y_m") -> list:
    """Load a simple (t, x, y) position log, sorted by time."""
    out = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append((float(row[time_col]), float(row[x_col]), float(row[y_col])))
    out.sort(key=lambda r: r[0])
    return out


def _interpolate(series: list, t: float, max_gap_s: float):
    """Linear-interpolate (x, y) at time t from a sorted (t, x, y) series.
    Returns None if t falls outside the series, or the nearest bracket
    exceeds max_gap_s -- a real data gap should not be papered over with
    a fabricated interpolated position."""
    if not series:
        return None
    times = [r[0] for r in series]
    i = bisect.bisect_left(times, t)
    if i == 0:
        t0 = series[0]
        return (t0[1], t0[2]) if abs(t0[0] - t) <= max_gap_s else None
    if i >= len(series):
        t1 = series[-1]
        return (t1[1], t1[2]) if abs(t1[0] - t) <= max_gap_s else None
    t0, x0, y0 = series[i - 1]
    t1, x1, y1 = series[i]
    if (t1 - t0) > max_gap_s:
        return None
    if t1 == t0:
        return (x0, y0)
    frac = (t - t0) / (t1 - t0)
    return (x0 + frac * (x1 - x0), y0 + frac * (y1 - y0))


def compute_error_series(estimated: list, ground_truth: list, max_gap_s: float = 2.0) -> list:
    """Returns [{"t_s","error_m"}, ...] at each estimated-position timestamp,
    skipping points where ground truth has no sample within max_gap_s."""
    out = []
    for t, ex, ey in estimated:
        gt = _interpolate(ground_truth, t, max_gap_s)
        if gt is None:
            continue
        gx, gy = gt
        err = ((ex - gx) ** 2 + (ey - gy) ** 2) ** 0.5
        out.append({"t_s": t, "error_m": round(err, 3)})
    return out


def early_warning_summary(confidence_trace: list, error_series: list, error_threshold_m: float = 1.0) -> dict:
    """
    confidence_trace: [{"t_s","level"}, ...] from compute_confidence() over time
    error_series:      [{"t_s","error_m"}, ...] from compute_error_series()

    Finds the first point where measured error exceeds error_threshold_m
    AND confidence has moved off HIGH, and reports the lead time between
    that point and the run's final (most severe) measured error.
    """
    conf_sorted = sorted(confidence_trace, key=lambda r: r["t_s"])
    conf_times = [r["t_s"] for r in conf_sorted]

    def level_at(t):
        if not conf_sorted:
            return None
        i = bisect.bisect_right(conf_times, t) - 1
        i = max(0, min(i, len(conf_sorted) - 1))
        return conf_sorted[i]["level"]

    warning = next(
        (pt for pt in error_series if pt["error_m"] > error_threshold_m and level_at(pt["t_s"]) != "HIGH"),
        None,
    )

    if warning is None or not error_series:
        return {"warning_found": False}

    final = error_series[-1]
    lead_s = final["t_s"] - warning["t_s"]
    return {
        "warning_found": True,
        "warning_t_s": warning["t_s"],
        "warning_error_m": warning["error_m"],
        "final_t_s": final["t_s"],
        "final_error_m": final["error_m"],
        "lead_time_s": round(lead_s, 1),
        "lead_time_min": round(lead_s / 60, 1),
    }
