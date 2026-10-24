"""Recreate the supplemental IRS-layout synthetic test image.

Optional authoring dependencies: pypdf, reportlab, and Poppler's pdftoppm.
Download https://www.irs.gov/pub/irs-prior/fw2--2025.pdf separately, then run:
python data/generate_irs_fixture.py /path/to/fw2--2025.pdf

Production extraction needs none of these authoring dependencies. This script
paints synthetic values onto the reference page and rasterizes it; the PDF is
temporary and is not a filing artifact. The checked-in PNG is the test input.
"""
import argparse
import hashlib
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas

EXPECTED_SHA = "6a52ad63693de54220a3326b22c4d0fb34f4c25084366537087312975a55ae96"
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_pdf", type=Path)
    parser.add_argument("--pdftoppm", default="pdftoppm")
    args = parser.parse_args()
    if hashlib.sha256(args.source_pdf.read_bytes()).hexdigest() != EXPECTED_SHA:
        raise ValueError("Reference PDF differs from the tested IRS 2025 source.")
    page = PdfReader(args.source_pdf).pages[2]
    coords = {a.get_object().get("/T"): a.get_object()["/Rect"]
              for a in page["/Annots"] if a.get_object().get("/Subtype") == "/Widget"}
    values = {
        "f2_01[0]": "902-23-4567", "f2_02[0]": "12-3456789",
        "f2_03[0]": "Silver Demo Employer", "f2_05[0]": "Alex",
        "f2_06[0]": "Sample", "f2_08[0]": "200 Test Road, Ithaca NY 14850",
        "f2_09[0]": "51234.67", "f2_10[0]": "4321.09",
        "f2_11[0]": "51234.67", "f2_12[0]": "3176.55",
        "f2_13[0]": "51234.67", "f2_14[0]": "742.90",
        "f2_15[0]": "0.00", "f2_16[0]": "0.00",
        "f2_18[0]": "0.00", "f2_19[0]": "0.00",
    }
    buf = BytesIO()
    canvas = Canvas(buf, pagesize=(612, 792))
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(36, 770, "SYNTHETIC TRAINING DATA - NOT FOR FILING")
    canvas.setFont("Helvetica", 9)
    for name, value in values.items():
        x, y, _, _ = coords[name]
        canvas.drawString(float(x)+3, float(y)+3, value)
    canvas.save()
    page.merge_page(PdfReader(buf).pages[0])
    writer = PdfWriter()
    writer.add_page(page)
    writer.remove_annotations(subtypes="/Widget")
    with tempfile.TemporaryDirectory() as directory:
        pdf_path = Path(directory)/"synthetic-w2.pdf"
        with pdf_path.open("wb") as stream:
            writer.write(stream)
        subprocess.run([args.pdftoppm, "-scale-to", "2600", "-singlefile", "-png",
            str(pdf_path), str(ROOT/"demo/w2_irs_layout")], check=True)


if __name__ == "__main__":
    main()
