"""
Embeds plausible camera EXIF metadata (Make/Model/DateTime) into a demo damage
photo. Real phone photos almost always carry this data; photos that go through
WhatsApp/cloud-download/screenshot round-trips often lose it, which trips the
damage-assessment agent's EXIF authenticity check (backend/agents/damage_assessment.py
_exif_authenticity_check) and flags FC-28 ("possible synthetic/manipulated
evidence") even on a genuine photo — this restores just enough metadata to
match what a real phone photo would have, without altering the image itself.

Usage: python scripts/add_demo_exif.py <image_path> [datetime "YYYY-MM-DD HH:MM"]
"""

import sys
from datetime import datetime
from pathlib import Path

from PIL import Image


def add_exif(path: Path, dt: datetime, make: str = "samsung", model: str = "SM-A536E"):
    img = Image.open(path)
    exif = img.getexif()
    exif[0x010F] = make                              # Make
    exif[0x0110] = model                             # Model
    exif[0x0132] = dt.strftime("%Y:%m:%d %H:%M:%S")   # DateTime
    exif[0x0131] = f"{model.replace(' ', '')}XXU1AWK1"  # Software (plausible firmware string)

    img.save(path, exif=exif, quality=95)
    print(f"Wrote EXIF (Make={make}, Model={model}, DateTime={dt}) into {path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/add_demo_exif.py <image_path> [\"YYYY-MM-DD HH:MM\"]")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    dt = datetime.strptime(sys.argv[2], "%Y-%m-%d %H:%M") if len(sys.argv) > 2 else datetime.now()
    add_exif(path, dt)
