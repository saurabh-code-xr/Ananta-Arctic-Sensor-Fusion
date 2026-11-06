"""
Field report generator.

Takes a run's JSON output (the {"meta", "results", "early_warning"} shape
produced by analyze_norcat_testbed.py, or any future real-data run with
the same shape) and produces a one-page markdown summary plus a PNG chart
-- something to hand to facility staff on site, or drop directly into the
IDEaS TRL evidence appendix, with no live session required to regenerate
it. Runs fully offline (matplotlib only; degrades to markdown-only if
matplotlib isn't installed).

Usage:
    python generate_field_report.py path/to/run.json
"""

import json
import os
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False

LEVEL_COLOR = {"HIGH": "#2e7d32", "MEDIUM": "#f9a825", "LOW": "#c62828"}
LEVEL_Y = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}


def load_run(json_path: str) -> dict:
    with open(json_path) as f:
        return json.load(f)


def make_chart(run: dict, out_png: str) -> bool:
    if not HAVE_MPL:
        print("matplotlib not available -- skipping chart, markdown-only report.")
        return False

    results = run["results"]
    t = [r["t_s"] for r in results]
    err = [r.get("fused_position_error_m") for r in results]
    levels = [r["confidence"]["level"] for r in results]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [1, 2]}
    )

    y = [LEVEL_Y[l] for l in levels]
    colors = [LEVEL_COLOR[l] for l in levels]
    ax1.scatter(t, y, c=colors, s=8, marker="s")
    ax1.set_yticks([0, 1, 2])
    ax1.set_yticklabels(["LOW", "MEDIUM", "HIGH"])
    ax1.set_ylabel("Confidence")
    ax1.set_title(run.get("meta", {}).get("title", "Ananta Meridian -- Confidence vs. Position Error"))

    if any(e is not None for e in err):
        ax2.plot(t, err, color="#1565c0", linewidth=1.5)
        ax2.set_ylabel("Position error (m)")
    ax2.set_xlabel("Time (s)")

    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    return True


def make_markdown(run: dict, chart_filename: str, chart_written: bool, out_md: str):
    results = run["results"]
    levels = [r["confidence"]["level"] for r in results]
    total = len(levels)
    high = levels.count("HIGH")
    medium = levels.count("MEDIUM")
    low = levels.count("LOW")
    meta = run.get("meta", {})

    lines = [
        "# Ananta Meridian -- Field Run Report",
        "",
        f"**Status:** {meta.get('status', 'unspecified')}",
        f"**Engine:** {meta.get('engine', 'data_fusion fusion_engine / confidence_engine / reliability_memory')}",
        "",
        "## Confidence Summary",
        f"- Total time steps: {total}",
    ]
    if total:
        lines += [
            f"- HIGH: {high} ({high/total*100:.0f}%)",
            f"- MEDIUM: {medium} ({medium/total*100:.0f}%)",
            f"- LOW: {low} ({low/total*100:.0f}%)",
        ]
    lines.append("")

    ew = run.get("early_warning")
    if ew and ew.get("warning_found"):
        lines += [
            "## Early-Warning Result",
            f"- Confidence degraded off HIGH at t={ew['warning_t_s']:.0f}s "
            f"(measured error {ew['warning_error_m']:.2f}m)",
            f"- Final measured error: {ew['final_error_m']:.2f}m at t={ew['final_t_s']:.0f}s",
            f"- Lead time: **{ew['lead_time_min']:.1f} minutes**",
            "",
        ]

    if chart_written:
        lines += ["## Chart", f"![confidence vs error]({chart_filename})", ""]

    with open(out_md, "w") as f:
        f.write("\n".join(lines))


def generate(json_path: str, out_dir: str = None):
    out_dir = out_dir or os.path.dirname(os.path.abspath(json_path))
    run = load_run(json_path)
    base = os.path.splitext(os.path.basename(json_path))[0]
    png_name = f"{base}_report.png"
    png_path = os.path.join(out_dir, png_name)
    md_path = os.path.join(out_dir, f"{base}_report.md")

    chart_written = make_chart(run, png_path)
    make_markdown(run, png_name, chart_written, md_path)
    print(f"Report written:\n  {md_path}" + (f"\n  {png_path}" if chart_written else ""))
    return md_path, (png_path if chart_written else None)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_field_report.py path/to/run.json")
        sys.exit(1)
    generate(sys.argv[1])
