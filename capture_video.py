#!/usr/bin/env python3
"""Reads input.csv and records one video per row via qscript.CaptureVideo_Magento."""
import argparse
import csv
import sys

import qscript


def main():
    parser = argparse.ArgumentParser(description="CSV-driven browser video recorder")
    parser.add_argument("csv_file", nargs="?", default="input.csv", help="input CSV (default: input.csv)")
    parser.add_argument("--video-dir", default="./video", help="output folder (default: ./video)")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    args = parser.parse_args()

    # The main script may override the global at startup.
    qscript.PATH_TO_VIDEO_FOLDER = args.video_dir
    qscript.HEADLESS = not args.headed

    failed = 0
    with open(args.csv_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";", quotechar='"')
        for i, row in enumerate(reader, start=1):
            name = row.get("Company Name", "") or ""
            print(f"[{i}] Processing: {name}")
            path = qscript.CaptureVideo_Magento(
                row.get("URL", "") or "",
                name,
                row.get("Language", "") or "",
                row.get("Country", "") or "",
                row.get("Postcode", "") or "",
                row.get("City", "") or "",
                row.get("Street", "") or "",
                row.get("HouseNo", "") or "",
            )
            if path:
                print(f"[{i}] Saved: {path}")
            else:
                failed += 1
                print(f"[{i}] FAILED: {name}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
