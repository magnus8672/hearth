"""Opt-in, synthetic-only benchmark on an installed decision socket. Never reads farm data."""

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

import httpx
from hearth.route_decisions import intent_request

from tests.fixtures.decision_cases import CASES


def summarize(rows):
    labels = sorted({r["label"] for r in rows})
    matrix = Counter((r["label"], r["choice"]) for r in rows)
    f1 = []
    for label in labels:
        tp = matrix[label, label]
        predicted = sum(n for (truth, pred), n in matrix.items() if pred == label)
        actual = sum(n for (truth, pred), n in matrix.items() if truth == label)
        f1.append(2 * tp / (actual + predicted) if actual + predicted else 0)
    media = [r for r in rows if r["accepted"] == "image.generate"]
    accepted = [r for r in rows if r["accepted"]]
    latency = sorted(r["wall_ms"] for r in rows)
    return {
        "count": len(rows),
        "macro_f1_raw": sum(f1) / len(f1),
        "accepted_coverage": len(accepted) / len(rows),
        "accepted_accuracy": sum(r["accepted"] == r["label"] for r in accepted) / len(accepted)
        if accepted
        else None,
        "media_predictions": len(media),
        "media_precision": sum(r["label"] == "image.generate" for r in media) / len(media) if media else None,
        "p50_ms": latency[len(latency) // 2],
        "p95_ms": latency[math.ceil(0.95 * len(latency)) - 1],
        "confusion_matrix": {
            label: {pred: matrix[label, pred] for pred in labels + ["error"]} for label in labels
        },
        "calibration": [
            {
                "bin": f"{i / 10:.1f}-{(i + 1) / 10:.1f}",
                "count": len(bucket),
                "accuracy": sum(r["choice"] == r["label"] for r in bucket) / len(bucket) if bucket else None,
            }
            for i in range(10)
            for bucket in [
                [
                    r
                    for r in rows
                    if i / 10 <= (r["confidence"] or 0) < (i + 1) / 10 or i == 9 and r["confidence"] == 1
                ]
            ]
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    with httpx.Client(transport=httpx.HTTPTransport(uds=args.socket), timeout=30, trust_env=False) as client:
        info = client.get("http://decision/v1/info").json()
        for case in CASES:
            data = intent_request(case["text"])
            started = time.monotonic()
            response = client.post("http://decision/v1/evaluate", json=data.model_dump(mode="json"))
            elapsed = (time.monotonic() - started) * 1000
            a = response.json()["answers"][0] if response.status_code == 200 else {}
            choice = a.get("choice", "error")
            confidence = a.get("answer_confidence")
            rows.append(
                case
                | {
                    "choice": choice,
                    "confidence": confidence,
                    "accepted": choice
                    if choice not in {"uncertain", "error"} and confidence is not None and confidence >= 0.85
                    else None,
                    "wall_ms": elapsed,
                    "status": response.status_code,
                }
            )
            if len(rows) % 30 == 0:
                print("Evaluated", len(rows), flush=True)
    report = {
        "fixture_sha256": hashlib.sha256(json.dumps(CASES, sort_keys=True).encode()).hexdigest(),
        "threshold": 0.85,
        "model": info,
        "splits": {
            split: summarize([r for r in rows if r["split"] == split]) for split in ["tune", "held_out"]
        },
        "cases": rows,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["splits"], indent=2))


if __name__ == "__main__":
    main()
