"""Run explicitly authorised image+OCR provider checks against labelled receipts.

Unlike compare_receipt_models.py this script sends receipt images to Gemini and
uses the configured category provider. It never saves financial transactions.
"""
import argparse
import io
import json
import re
import sys
from pathlib import Path
from time import perf_counter

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.receipt_ocr import extract_receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("images", type=Path)
    parser.add_argument("cases", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--rotate-first", action="store_true")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())["cases"]
    variants = [(case, 0) for case in cases]
    if args.rotate_first:
        variants.append((cases[0], 90))
    records = []
    normalize = lambda text: re.sub(r"[^A-Z0-9]", "", text.upper())
    for case, angle in variants:
        content = (args.images / case["file"]).read_bytes()
        if angle:
            with Image.open(io.BytesIO(content)) as image:
                encoded = io.BytesIO()
                image.rotate(angle, expand=True).save(encoded, "JPEG", quality=95)
                content = encoded.getvalue()
        started = perf_counter()
        result = extract_receipt(content)
        checks = {"merchant": normalize(result["merchant"]) in [normalize(x) for x in
            [case["merchant"], *case.get("merchant_aliases", [])]],
            "date": result["transactionDate"] == case["date"],
            "total": result["totalAmount"] == case["total"]}
        if case.get("itemCount") is not None:
            checks["itemCount"] = len(result["items"]) == case["itemCount"]
        if case.get("productContains"):
            checks["product"] = any(case["productContains"].casefold() in x["description"].casefold()
                                    for x in result["items"])
        record = {"file": case["file"], "rotation": angle, "checks": checks,
                  "seconds": round(perf_counter() - started, 3), "result": result}
        records.append(record)
        args.output.write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(json.dumps({"file": case["file"], "rotation": angle, "checks": checks,
            "status": result["verificationStatus"], "warnings": result["reviewWarnings"],
            "items": len(result["items"])}), flush=True)
    if not all(all(r["checks"].values()) for r in records):
        raise SystemExit("Receipt field validation failed; inspect the saved report")


if __name__ == "__main__":
    main()
