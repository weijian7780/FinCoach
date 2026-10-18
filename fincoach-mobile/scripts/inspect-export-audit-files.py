"""Render the production export HTML with desktop Chrome and inspect real files.

This checks serializer output and desktop PDF pagination, not Android expo-print.
All input files contain only disposable acceptance-test financial records.
"""
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

import fitz

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2] / "output/export-backup-v2-20261010"
CHROME = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
checks = []


def check(name, passed, **details):
    checks.append({"name": name, "passed": bool(passed), **details})
    print(("PASS " if passed else "FAIL ") + name, flush=True)


manifest = json.loads((ROOT / "selection-manifest.json").read_text(encoding="utf-8"))
for mask in range(1, 8):
    rows = list(csv.reader((ROOT / f"selection-{mask}.csv").open(encoding="utf-8-sig", newline="")))
    transaction_rows = [r for r in rows if r and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[0]) and len(r) == 6]
    expected = manifest["expectedTransactionRows"] if mask & 1 else 0
    check(f"CSV {mask}: independently parsed selected transaction count", len(transaction_rows) == expected,
          expected=expected, actual=len(transaction_rows))
    if mask & 1:
        check(f"CSV {mask}: UTF-8, commas, quotes and embedded newline round trip",
              manifest["specialDescription"] in [r[1] for r in transaction_rows])
        check(f"CSV {mask}: dates exclude out-of-range fixtures",
              not any("AUDIT_BEFORE_RANGE" in r or "AUDIT_AFTER_RANGE" in r for r in transaction_rows))

for source in [*(ROOT / f"selection-{mask}.html" for mask in range(1, 8)), ROOT / "large-export.html"]:
    if not source.exists():
        check(f"PDF source exists: {source.name}", False)
        continue
    pdf_path = source.with_suffix(".pdf")
    # A separate local browser profile avoids interacting with personal sessions.
    result = subprocess.run([
        str(CHROME), "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--no-pdf-header-footer", f"--user-data-dir={ROOT / 'chrome-profile'}",
        f"--print-to-pdf={pdf_path}", source.as_uri(),
    ], capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
    check(f"desktop PDF created: {pdf_path.name}", result.returncode == 0 and pdf_path.exists())
    if not pdf_path.exists():
        print(result.stderr.decode(errors="replace")[-1000:])
        continue
    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    (ROOT / f"{source.stem}.pdf.txt").write_text(text, encoding="utf-8")
    html = source.read_text(encoding="utf-8")
    for title in ["Transactions", "Budgets", "Savings Goals"]:
        check(f"PDF {source.stem}: section {title}", (title in text) == (f"<h2>{title}</h2>" in html))
    if source.stem != "large-export":
        mask = int(source.stem.split("-")[-1])
        if mask & 1:
            for needle in ['AUDIT_UNICODE_测试', 'café "quoted", comma', 'second line', 'AUDIT_END_BOUNDARY', '=1+1', '23.45']:
                check(f"PDF {mask}: text survives rendering: {needle}", needle in re.sub(r"\s+", " ", text))
    else:
        expected_ids = set(re.findall(r"AUDIT_BULK_\d{4}", html))
        actual_ids = set(re.findall(r"AUDIT_BULK_\d{4}", text))
        check("large PDF preserves every fetched bulk row across pages", actual_ids == expected_ids,
              expected=len(expected_ids), actual=len(actual_ids), pages=len(doc))
        for index in sorted({0, len(doc) // 2, len(doc) - 1}):
            doc[index].get_pixmap(matrix=fitz.Matrix(1.3, 1.3)).save(ROOT / f"large-page-{index + 1}.png")
    # Geometric checks supplement visual inspection; they do not replace it.
    outside = []
    for index, page in enumerate(doc):
        for word in page.get_text("words"):
            if word[0] < -1 or word[1] < -1 or word[2] > page.rect.width + 1 or word[3] > page.rect.height + 1:
                outside.append({"page": index + 1, "text": word[4]})
    check(f"PDF {source.stem}: extracted words remain within page bounds", not outside, outside=outside[:5], pages=len(doc))
    if source.stem == "selection-7":
        doc[0].get_pixmap(matrix=fitz.Matrix(1.3, 1.3)).save(ROOT / "all-sections-preview.png")
    doc.close()

(ROOT / "file-inspection-results.json").write_text(json.dumps({
    "environment": "Windows desktop Chrome PDF renderer; PyMuPDF text/geometry; Python CSV parser; NOT Android",
    "checks": checks,
}, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"passed": sum(c["passed"] for c in checks), "failed": sum(not c["passed"] for c in checks)}))
