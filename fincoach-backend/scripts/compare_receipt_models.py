"""Isolated OCR comparison: no provider calls and no service configuration changes.

Run in the backend container with images, cases JSON and an output path. Each
model pair runs in its own process so native model allocations are released.
"""
import argparse
import json
import os
import re
import resource
import subprocess
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODELS = {
    "v5-mobile": ("PP-OCRv5_mobile_det", "en_PP-OCRv5_mobile_rec"),
    "v6-small": ("PP-OCRv6_small_det", "PP-OCRv6_small_rec"),
    "v6-medium": ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("images", type=Path)
    parser.add_argument("cases", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", choices=MODELS)
    args = parser.parse_args()
    if not args.model:
        for name in MODELS:
            subprocess.run([sys.executable, __file__, str(args.images), str(args.cases),
                str(args.output.with_name(args.output.stem + "-" + name + ".json")),
                "--model", name], check=True)
        return
    detector, recognizer = MODELS[args.model]
    os.environ["PADDLE_OCR_DETECTION_MODEL"] = detector
    os.environ["PADDLE_OCR_RECOGNITION_MODEL"] = recognizer
    from app.receipt_ocr import get_ocr_engine, parse_receipt, run_paddle_ocr
    started = perf_counter()
    report = {"model": args.model, "detector": detector, "recognizer": recognizer,
              "cases": [], "providerCalls": 0,
              "labelMethod": "Assistant-transcribed fields; not independently human-validated",
              "inferenceBackend": "Paddle CPU, four threads, MKLDNN disabled"}
    try:
        engine = get_ocr_engine()
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)[:1500]}
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
        return
    report["loadSeconds"] = round(perf_counter() - started, 3)
    for case in json.loads(args.cases.read_text())["cases"]:
        started = perf_counter()
        lines = run_paddle_ocr((args.images / case["file"]).read_bytes(), engine)
        result = parse_receipt(lines)
        record = {"file": case["file"], "seconds": round(perf_counter() - started, 3),
                  "result": result, "rows": [{"text": r.text, "confidence": r.confidence,
                  "boxes": r.boxes} for r in lines]}
        record["checks"] = {"date": result["transactionDate"] == case["date"],
                            "total": result["totalAmount"] == case["total"]}
        normalize = lambda text: re.sub(r"[^A-Z0-9]", "", text.upper())
        record["checks"]["merchant"] = normalize(result["merchant"]) in [normalize(x)
            for x in [case["merchant"], *case.get("merchant_aliases", [])]]
        if case.get("itemCount") is not None:
            record["checks"]["itemCount"] = len(result["items"]) == case["itemCount"]
        if case.get("productContains"):
            record["checks"]["product"] = any(case["productContains"].casefold() in
                x["description"].casefold() for x in result["items"])
        report["cases"].append(record)
        report["peakRssMiB"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"model": args.model, "file": case["file"],
            "seconds": record["seconds"], "checks": record["checks"],
            "merchant": result["merchant"], "items": result["items"]}), flush=True)


if __name__ == "__main__":
    main()
