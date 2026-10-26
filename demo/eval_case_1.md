# Demo 1: clean W-2 extraction

This is Xinrui's extraction fixture, not a complete taxpayer scenario. The team
must add filing status, birth date, other intake answers, and the complete return
workflow before using it as the assignment's full eval_case_1.

1. Activate the environment and install the locked dependencies (README).
2. Run `python extract_documents.py demo/w2_clean.jpg --output outputs/clean.json`.
3. Expected: exit code 0; `status=extracted`; printed year 2025; synthetic SSN
   901-12-3456; box 1 `38750.25`; box 2 `3125.50`.
4. Open the JSON and inspect either amount's `source`: it identifies the image
   hash, printed box, raw text, coordinates, confidence, and time.
5. `python -m examples.parallel_extraction` demonstrates aggregation of both
   supplied W-2 images without overwriting either extraction.

Only fake classroom data are used. The images say NOT FOR FILING.
