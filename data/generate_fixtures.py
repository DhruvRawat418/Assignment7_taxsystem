"""Generate synthetic W-2 training images, never real taxpayer documents.

These are clearly marked mock forms, not forms that can be filed with the IRS.
Expected amounts are test oracles; production extraction never reads them.
"""
from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def font(size):
    for name in ["DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def make_w2(path, *, wages="38,750.25", withheld="3,125.50", ssn="901-12-3456",
            year="2025", other_wages="38,750.25", scale=1):
    image = Image.new("RGB", (1800, 1100), "white")
    draw = ImageDraw.Draw(image)
    def text(x, y, value, size=24):
        draw.text((x, y), value, fill="black", font=font(size))
    text(45, 20, "SYNTHETIC TRAINING DOCUMENT - NOT FOR FILING", 27)
    text(45, 67, "Form W-2  Wage and Tax Statement", 36)
    text(1560, 67, year, 40)
    text(45, 145, "a Employee's social security number", 23)
    text(65, 195, ssn, 32)
    text(45, 275, "b Employer identification number (EIN)", 23)
    text(65, 320, "12-3456789", 32)
    text(45, 410, "c Employer's name and address", 23)
    text(65, 455, "Silver Demo Employer", 30)
    text(65, 500, "100 Example Street", 27)
    text(65, 540, "Ithaca, NY 14850", 27)
    text(45, 650, "e Employee's name", 23)
    text(65, 695, "Alex Sample", 30)
    labels = [
        ("1 Wages, tips, other compensation", wages),
        ("2 Federal income tax withheld", withheld),
        ("3 Social security wages", other_wages),
        ("4 Social security tax withheld", "2,402.52"),
        ("5 Medicare wages and tips", other_wages),
        ("6 Medicare tax withheld", "561.88"),
        ("7 Social security tips", "0.00"),
        ("8 Allocated tips", "0.00"),
        ("9", ""),
        ("10 Dependent care benefits", "0.00"),
        ("11 Nonqualified plans", "0.00"),
        ("12a See instructions for box 12", ""),
    ]
    for idx, (label, amount) in enumerate(labels):
        x, y = 710 + (idx % 2) * 525, 145 + (idx // 2) * 112
        draw.rectangle((x-12, y-9, x+510, y+101), outline="black", width=2)
        text(x, y, label, 24)
        if amount:
            text(x+20, y+48, amount, 34)
    text(710, 835, "13 Statutory employee   Retirement plan", 23)
    text(710, 920, "15 State   Employer's state ID number", 23)
    text(45, 1030, "Copy B - Mock document for SilverFile classroom testing only", 25)
    if scale != 1:
        image = image.resize((round(image.width*scale), round(image.height*scale)))
    image.save(path, quality=94)


def main():
    demo = ROOT / "demo"
    demo.mkdir(exist_ok=True)
    make_w2(demo / "w2_clean.jpg")
    make_w2(demo / "w2_missing_withholding.jpg", withheld="")
    (ROOT / "data/fixtures/expected_w2.json").write_text(json.dumps({
        "w2_clean.jpg": {"tax_year": "2025", "employee_ssn": "901-12-3456",
            "box_1": "38750.25", "box_2": "3125.50"},
        "w2_missing_withholding.jpg": {"expected_status": "needs_review", "missing_box": "2"},
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
