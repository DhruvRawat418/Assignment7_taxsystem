"""Standalone CLI for Xinrui's Document Extraction component."""
import argparse
import json
from pathlib import Path

from src.document_extraction import extract_w2
from src.document_extraction.ocr import RapidOCREngine


def main():
    parser = argparse.ArgumentParser(description="Transcribe synthetic W-2 images locally.")
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, help="Write JSON; otherwise print it.")
    args = parser.parse_args()
    engine = RapidOCREngine()
    results = [extract_w2(path, f"W2#{index}", engine=engine)
               for index, path in enumerate(args.images, 1)]
    text = json.dumps([r.model_dump(mode="json") for r in results], indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0 if all(r.ready for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
