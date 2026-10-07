# Phone receipt extraction diagnosis and implementation plan

Date: 3 October 2026. Status: implemented; local backend restarted and healthy.
Scope: receipt capture, OCR correction, parsing and receipt review only.
Backend and mobile application code were changed after implementation approval.
No financial transaction was saved during this investigation or validation.

## Correct reading of the supplied receipt

The upright image visibly supports these fields. This is a manual transcription,
The final local automatic pipeline also returns the critical fields below.

## Implementation and validation results

- Enabled document orientation classification and preserved normalized image
  coordinates for image verification. Added consistent date parsing, printed
  payment/rounding reconciliation, safer merchant selection, table headers,
  wrapped item descriptions and unpriced modifiers. Unknown or conflicting
  critical fields remain blank with review warnings.
- Added manual crop/rotate before scanning and a zoomable receipt viewer with
  original/prepared image selection during review. Missing dates no longer
  silently become today's date. Missing categories require manual selection.
- Real local PaddleOCR inference recovered merchant, date, RM24.50 and two
  priced items in all four quarter-turn orientations and the diagnostic crop.
  A final production extraction pipeline check on the original image passed
  with Google verification and classification calls explicitly disabled.
- Focused backend checks: 67 tests passed plus 13 subtests. Mobile: 39 tests
  passed, TypeScript passed, Android app Kotlin compilation passed. Scoped
  tracked-file whitespace checks passed.
- Five previously labelled public scans: dates 5/5, totals 5/5, merchants 4/5.
  One merchant retained OCR character errors; no sample-specific alias was
  introduced. Replaying their actual OCR rows through the final parser preserved
  every date/total and recovered two wrapped products in receipt_41.jpg.
- Local Docker backend restarted; /health and /ready returned status ok with
  OCR and embeddings ready. This is local deployment evidence, not an
  authenticated phone scan or remote deployment verification.
- No Android device was connected. New native image-manipulation controls need
  a rebuilt APK; no new APK was installed or device UI tested in this run.
- Initial automatic approval review rejected transmitting the private receipt
  to Google without explicit transfer approval. After the user explicitly
  requested the Gemini test, a live verification call was completed using
  gemini-3.5-flash-lite. Merchant, date, RM24.50, Food and both priced items
  remained correct. Verification was partial: 52/56 source rows were verified;
  conflicting provider decisions for IDs 15, 43, 46 and 47 were rejected.
  The order/date row remained unverified, so the date review warning was retained.
  Total runtime was 19.867 seconds, including 12.436 seconds of local OCR.
  This single run demonstrates successful provider integration, not guaranteed
  complete verification. Evidence: gemini-live-results.jsonl (private, local).
- Manual crop removes background/extra receipts. Automatic perspective
  unwarping and automatic single-document cropping are not implemented here.

Evidence is retained locally under evaluation-results/receipt-phone-2026-10-03/;
private image/text artifacts must not be published as regression fixtures.

| Field | Expected value |
|---|---|
| Preferred merchant display | McDonald's Likas Bay KK (#394) |
| Printed legal merchant | Gerbang Alaf Restaurants Sdn Bhd |
| Purchase date | 2026-10-03 |
| Final payment | RM24.50 |
| Suggested category | Food |
| Priced row 1 | Nasi Lemak+2AGReg, RM17.88 |
| Priced row 2 | Taro Pie, RM5.24 |
| Subtotal | RM23.12 |
| Service tax | RM1.39 |
| Total including tax before rounding | RM24.51 |
| Rounding adjustment | -RM0.01 |

The main meal includes unpriced modifier rows for M Coke, NO Ice and No Add-On.
They must not become invented additional charges. The printed item shorthand
should be preserved rather than expanded into an unsupported product name.

Payment check: 17.88 + 5.24 + 1.39 - 0.01 = 24.50. The receipt also prints
Visa 24.50 and the terminal payment amount RM24.50.

## Reproduction evidence

The attachment is 1545 x 1159 pixels. EXIF orientation is 0; the sideways text
is in the actual pixels. The running Docker container uses the current receipt
code, PP-OCRv5_mobile_det and en_PP-OCRv5_mobile_rec. The diagnostic script
called real run_paddle_ocr and parse_receipt inside that container.

| Input | Reconstructed rows | Parsed merchant | Parsed date | Parsed total | Priced items |
|---|---:|---|---|---|---:|
| Original attachment | 5 | Scrambled unrelated text | 2026-10-03 | 17.88 | 0 |
| Rotated 90 degrees counterclockwise | 52 | Gerbang Alaf Restaurants Sdn Bhd | 2033-03-10 | 24.51 | 0 |
| Rotated and cropped to the main receipt | 52 | Gerbang Alaf Restaurants Sdn Bhd | 2026-10-03 | 24.51 | 0 |

An earlier independent original-only run also returned five rows, a scrambled
merchant, RM17.88 and zero items. The screenshot's exact HONOR 200 result was
not reproduced by the current parser, but HONOR 200 was present in the original
OCR output. This confirms the watermark is included in the OCR input, while
the exact prior selection remains unproven.

The first variant includes model initialization, so timings are unsuitable for
claiming a preprocessing speed improvement. These are function-level container
tests, not an authenticated HTTP replay, Android device test or Oracle test.

The current source uses original image + indexed OCR rows -> Gemini correction
JSON -> integrity merge -> parser. Earlier text-only cleanup is now legacy code.
The Gemini retry on this private attachment was rejected by automatic approval
review because external transfer had not been explicitly approved. All executed
receipt inference in this investigation remained local to PaddleOCR. Gemini
timeout, output and recovery for this attachment are therefore untested.

Existing backend log events show recent 4096 x 3072 receipt requests producing
four/five rows with partial/verified vision status. They lack correlation to the
attachment, so they do not prove those requests used this exact receipt. The
attachment may also differ from the phone's original resolution or compression.

## Confirmed causes and remaining uncertainty

1. **Orientation and row grouping.** get_ocr_engine disables document
   orientation, document unwarping and text-line orientation. _prepare_ocr_image
   decodes/resizes without detecting receipt orientation or selecting the
   receipt region. _reconstruct_rows groups by image y-coordinate assuming
   upright text. Sideways text becomes a handful of huge merged rows. Rotation
   restored 52 rows without changing the OCR models.
2. **Background contamination.** OCR sees the camera watermark and other text
   outside the receipt. Merchant selection has no receipt-region provenance.
   A model-specific HONOR blacklist would not solve the general problem.
3. **Item boundary.** _TOTALS_BOUNDARY matches bare total anywhere. The table
   heading QTY ITEM TOTAL, partially merged with the preceding date row in both
   upright variants, triggers the boundary before any products. The real OCR
   rows contain both priced items, but the parser returns an empty item list.
4. **Payable amount.** _payable_line accepts Eat-In Total (incl Tax) 24.51 but
   does not reconcile the following rounding adjustment or approved payment
   amount. Visa is excluded and bare AMOUNT is not a payable label. Correctly
   recognised numbers therefore still yield the wrong transaction amount.
5. **Date regex.** _DATE searches the first numeric match and permits mixed
   separators. The upright OCR string includes CS0 #33-03/10/2026. The parser
   consumes 33-03/10 as year 2033, month 03, day 10, ignoring the complete
   purchase date. A direct synthetic parser probe reproduced 2033-03-10.
6. **Merchant role.** _merchant considers only the first eight reconstructed
   rows. The branch name is row ten; the legal entity is chosen earlier. That
   entity is printed and valid, but the current rule cannot prefer the useful
   branch display or distinguish watermark, order heading, address and company.
7. **Review/version uncertainty.** Current review.tsx displays reviewWarnings
   and starts with the extracted date, including an empty value. The screenshot
   does not visibly show that warning UI. It could use an older client or lack
   warning metadata; its exact client/server versions are not established.
   The displayed 2026-10-03 happens to match the receipt, but does not prove OCR
   detected it rather than a prior client supplying today's date.

OCR confidence concerns recognised characters; it does not establish that an
amount is the final payable amount, that a heading is the merchant, or that all
receipt rows were recovered. Similarly, verifying every supplied source ID
does not establish complete document extraction when only five rows were supplied.

## Stage 1: general image preparation

Files: app/receipt_ocr.py, app/config.py, .env.example and applicable Compose
configuration. Keep the existing mobile OCR models while evaluating preparation.

- Normalize EXIF exactly once, including quarter turns and mirrored images.
  Avoid double rotation between Pillow and OpenCV decoding.
- Enable/test PaddleOCR's document orientation classifier, which covers
  0/90/180/270 degrees. Its text-line orientation module covers 0/180 degrees
  and is not a replacement for sideways document correction.
- Preserve coordinates through transforms; reconstruct rows only after text
  orientation is normalized. Keep individual source polygons for diagnostics
  and field provenance rather than prematurely discarding layout information.
- Add receipt-region selection with a user-adjustable crop/rotation fallback.
  When multiple receipts appear, ask the user to select one instead of combining
  their text. Never use the fixed experiment crop coordinates in production.
- Resize the selected receipt, preserving readable text and the current upload
  and pixel limits. A default size increase would not fix sideways grouping.
- Benchmark perspective correction/unwarping separately on curved receipts.
  It remains optional until accuracy, memory and CPU latency are measured on
  the target deployment. This experiment did not test automatic orientation.

## Stage 2: repair parser semantics

File: app/receipt_ocr.py. Implement reusable row roles rather than vendor-specific
receipt branches. Retain candidate source IDs, labels and geometry.

- **Dates:** evaluate complete date candidates; require consistent separators,
  prefer explicit four-digit dates and date-labelled contexts, and reject
  fragments of order/reference identifiers. Apply the app's Malaysia date
  policy; unresolved or future-only candidates require review. Never silently
  replace an unreadable date with today's date.
- **Items:** distinguish column headings from monetary summary rows. TOTAL in
  QTY ITEM TOTAL must not stop item extraction. Parse priced product rows up to
  the actual summary section and associate unpriced wrapped/modifier rows with
  their parent item where supported by layout.
- **Totals:** distinguish subtotal, tax, total before rounding, signed rounding,
  approved card charge, cash tender and change. Preserve the negative sign even
  when OCR separates it from the amount. Reconcile candidates in integer cents;
  use the explicitly printed final payment when corroborated. Conflicts require
  review rather than choosing the largest amount or inventing a payable value.
- **Merchant:** inspect the complete header region, not a fixed eight rows.
  Prefer a printed branch/brand display where identifiable, retain a valid legal
  name as fallback, and exclude non-receipt image regions and order headings.
  Do not infer a merchant from a camera brand or a large font alone.
- **Category:** classify only after usable merchant/items have been recovered.
  With insufficient evidence, return no suggestion instead of presenting a
  default category as a detected result.

## Stage 3: preserve Gemini's existing responsibility

File: app/receipt_vision.py and the correction contract tests.

- Keep Gemini responsible for visual text correction and missing readable rows;
  keep final transaction parsing in the backend. Do not switch to direct final
  field generation to hide parser defects.
- Verify against the selected upright receipt image with clearly indexed rows.
  Preserve the original upload and transform mapping for user review.
- Explicitly identify non-receipt watermark/background text. The current empty
  correctedText mechanism can exclude such rows while preserving original text
  and the correction reason; the parser must not consume excluded rows.
- Require readable missing rows to be recovered as separate ordered rows. Test
  whether multiline correctedText needs normalization before semantic parsing.
  Source-ID coverage must not be displayed as proof of complete extraction.
- Preserve bounded requests, fallback metadata and omission/conflict handling.
  Measure timeout/output behaviour after preprocessing before changing the
  current 12-second timeout. A longer deadline is not yet a proven remedy.
- Test the private attachment through Gemini only after explicit approval of
  the image/text transfer. Use public or redacted fixtures for routine runs.

## Stage 4: complete the review flow

Files: fincoach-mobile/src/app/transactions/scan.tsx, transactions/review.tsx,
src/lib/receipt-ocr.ts and src/lib/types.ts as required.

- Add crop and quarter-turn controls before upload; retain the existing visual
  style and keep controls usable on small Android screens.
- Show the original receipt in an enlargeable viewer for field correction.
- Keep missing dates/amounts visibly empty and show existing reviewWarnings.
  Confirm/repair ambiguous critical fields before saving; do not equate a 200
  response or visually verified source rows with a complete transaction.
- Suppress category suggestion while receipt evidence is insufficient. Continue
  supporting manual correction and receipt rescan.
- Compare the installed APK and its selected backend with the current source;
  a mobile rebuild/device check is necessary for client UI changes. Backend-only
  parser fixes do not intrinsically require an APK rebuild.

## Stage 5: validation and release criteria

Use parser regressions at the real parse_receipt seam plus real-image evaluation.
Do not rely on mocks or a successful response alone.

- Current receipt: expected date 2026-10-03, payment 24.50, Food suggestion when
  evidence supports it, and two priced rows totalling 23.12. Accept both printed
  merchant names as supported evidence while testing preferred branch display.
- Rotate samples through all four quarter turns; cover EXIF rotation, watermark
  outside the document, multiple receipts, excessive background and perspective.
- Vary table headers and their position, mixed/collapsed date rows, legal name
  above branch, wrapped items, modifiers, separated negative rounding, subtotal,
  tax, repeated terminal amount, cash tender/change and conflicting totals.
- Cover Gemini unavailable/timeout, omitted/conflicting decisions, recovered
  rows and multiline corrections. Keep raw OCR and added/corrected provenance.
- Verify no warning is hidden and no unknown date silently becomes today on
  Honor 200 and a small Android viewport. Saving still requires valid fields.
- Run focused receipt tests and mobile checks appropriate to the actual changes.
  Then restart/deploy the approved backend change, verify readiness and perform
  one authenticated phone scan before claiming the device issue is resolved.

## Artifacts and official references

The experiment script and full local OCR results are in
evaluation-results/receipt-phone-2026-10-03/. They include private receipt data;
use redacted equivalents for committed regression fixtures. The crop coordinates
are diagnostic only and must never become a production template.

- PaddleOCR official pipeline modules, orientation classes and configuration:
  https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/OCR.en.md
- Google's image-understanding guidance:
  https://ai.google.dev/gemini-api/docs/image-understanding
- Google's structured-output guidance: valid JSON does not establish semantic
  correctness and application validation remains necessary:
  https://ai.google.dev/gemini-api/docs/structured-output
