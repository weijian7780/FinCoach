#!/usr/bin/env python3
"""Fetch ~50 diverse Malaysian retail receipts for OCR testing (SROIE, ICDAR 2019).

Streams the dataset from Hugging Face and stops after 50 receipts instead of
downloading all ~1000 -- more resilient on flaky connections, and retries if the
stream drops.

Usage:
    pip install datasets pillow
    python scripts/fetch_test_receipts.py
"""
from __future__ import annotations

import io
import re
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset
from PIL import Image

OUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "receipt_samples"
SAMPLE_SIZE = 50
MAX_PER_MERCHANT = 2
DATASET = "Voxel51/scanned_receipts"

_MY = re.compile(
    r"(?:\bRM\b|SDN\.?\s*BHD|\bMALAYSIA\b|SELANGOR|KUALA LUMPUR|\bJOHOR\b|"
    r"PULAU PINANG|\bMELAKA\b|\+?60\d)",
    re.I,
)
_SG = re.compile(r"(?:PTE\.?\s*LTD|\bSGD\b|S\$|\bSINGAPORE\b|\+?65\d{7})", re.I)


def _is_malaysian(text: str) -> bool:
    return bool(_MY.search(text)) and not _SG.search(text)


def _merchant_key(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 3 and any(c.isalpha() for c in line):
            return re.sub(r"[^A-Z]", "", line.upper())[:12] or "UNKNOWN"
    return "UNKNOWN"


def _find_keys(example: dict) -> tuple[str | None, str | None]:
    img_key = text_key = None
    for k, v in example.items():
        if img_key is None and isinstance(v, Image.Image):
            img_key = k
        elif img_key is None and isinstance(v, dict) and "bytes" in v:
            img_key = k
        if text_key is None and isinstance(v, str) and len(v) > 20:
            text_key = k
    return img_key, text_key


def _to_image(value) -> Image.Image:
    if isinstance(value, Image.Image):
        return value
    return Image.open(io.BytesIO(value["bytes"]))


def _collect(counts: dict, state: dict) -> None:
    dsd = load_dataset(DATASET, streaming=True)
    split = "train" if "train" in dsd else list(dsd)[0]
    scanned = 0
    for example in dsd[split]:
        scanned += 1
        if state["img_key"] is None:
            state["img_key"], state["text_key"] = _find_keys(example)
            print("row keys:", list(example),
                  "| image:", state["img_key"], "| text:", state["text_key"])
            if state["img_key"] is None:
                raise SystemExit("No image field found in dataset rows.")

        # If the country filter matches nothing early, disable it so we still
        # deliver images (the pool is mostly Malaysian anyway).
        if state["text_key"] and scanned > 300 and state["saved"] == 0:
            print("Filter matched nothing in 300 rows; disabling country filter.")
            state["text_key"] = None

        text = str(example.get(state["text_key"], "")) if state["text_key"] else ""
        if state["text_key"] and not _is_malaysian(text):
            continue
        merchant = _merchant_key(text) if text else f"row{scanned}"
        if counts[merchant] >= MAX_PER_MERCHANT:
            continue

        n = state["saved"] + 1
        _to_image(example[state["img_key"]]).convert("RGB").save(
            OUT_DIR / f"receipt_{n:02d}.jpg", quality=92
        )
        counts[merchant] += 1
        state["saved"] = n
        print(f"  saved receipt_{n:02d}.jpg  [{merchant}]")
        if state["saved"] >= SAMPLE_SIZE:
            return


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = defaultdict(int)
    state = {"saved": 0, "img_key": None, "text_key": None}

    for attempt in range(1, 5):
        if state["saved"] >= SAMPLE_SIZE:
            break
        try:
            _collect(counts, state)
        except SystemExit:
            raise
        except Exception as exc:  # network drop -- retry, keeping what we have
            print(f"[attempt {attempt}] stream error, retrying: {exc}")

    print(f"\nSaved {state['saved']} receipts to {OUT_DIR}")


if __name__ == "__main__":
    main()
