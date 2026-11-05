#!/usr/bin/env python3
"""From measurements.csv files to the \\addplot commands of the latency box plot.

    python3 e2e_pgf.py PATH/TO/measurements.csv [more measurements.csv ...] > plots_e2e.tex

For each CSV, the path (Reaction or Visualization) and the twin are read from
the summary.json next to it. Only successful measured samples are used.
Quartiles use linear interpolation (numpy.percentile default, Excel
PERCENTILE.INC). Whiskers end at the most extreme value within 1.5 IQR of the
box. Values beyond are outliers.

Output order: Visualization at x = 0, Reaction at x = 1, the charging point
station left (red) and the virtual power plant right (blue) of each position.
"""
import csv
import json
import math
import os
import sys

PATHS = {"mqtt-twinmaker": "Visualization", "mqtt": "Reaction"}          # evaluation -> path
TWINS = {"MGridICSA": ("Charging point station", "red", -0.18),          # twin_name -> label, colour, offset
         "VPP": ("Virtual power plant", "blue", 0.18)}
PATH_ORDER = ["Visualization", "Reaction"]


def quantile(v, p):
    """Linear interpolation between closest ranks on sorted values."""
    k = (len(v) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def box(v):
    q1, med, q3 = quantile(v, .25), quantile(v, .5), quantile(v, .75)
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    inside = [x for x in v if lo <= x <= hi]
    return dict(q1=q1, med=med, q3=q3, lw=inside[0], uw=inside[-1],
                out=[x for x in v if x < lo or x > hi])


def read(csv_path):
    summ = json.load(open(os.path.join(os.path.dirname(os.path.abspath(csv_path)), "summary.json")))
    with open(csv_path) as f:
        v = sorted(float(r["roundtrip_ms"]) / 1000 for r in csv.DictReader(f)
                   if r["phase"] == "measured" and r["status"] == "success")
    return PATHS[summ["evaluation"]], summ["twin_name"], v


def main():
    series = {}
    for p in sys.argv[1:]:
        path, twin, v = read(p)
        series[(path, twin)] = v
    for twin, (label, color, offset) in TWINS.items():
        first = True
        for path in PATH_ORDER:
            if (path, twin) not in series:
                continue
            v = series[(path, twin)]
            b = box(v)
            out = " ".join(f"(0,{x:.3f})" for x in b["out"])
            print(f"% {path} / {label}: n={len(v)}")
            print(rf"\addplot[color={color}, fill={color}!25!white, mark=x, mark options={{scale=0.6}},")
            print(f"  boxplot prepared={{draw position={PATH_ORDER.index(path) + offset:g}, box extend=0.28,")
            print(f"    lower whisker={b['lw']:.3f}, lower quartile={b['q1']:.3f}, median={b['med']:.3f},")
            print(f"    upper quartile={b['q3']:.3f}, upper whisker={b['uw']:.3f}}}{'' if first else ', forget plot'}]")
            print(f"  coordinates {{{out}}};")
            if first:
                print(rf"\addlegendentry{{{label}}}")
                first = False


if __name__ == "__main__":
    main()
