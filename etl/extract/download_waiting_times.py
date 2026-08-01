from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import urllib.request


DEFAULT_URL = (
    "https://www.opendata.nhs.scot/dataset/997acaa5-afe0-49d9-b333-dcf84584603d/"
    "resource/37ba17b1-c323-492c-87d5-e986aae9ab59/download/"
    "monthly_ae_activity_202605.csv"
)
DEFAULT_OUTPUT = Path("data/raw/nhs_scotland/monthly_ae_activity_waiting_times.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download NHS Scotland A&E activity and waiting-time data."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def download_csv(url: str, output: Path, force: bool = False) -> Path:
    if output.exists() and not force:
        print(f"Raw data already exists: {output.as_posix()}")
        return output

    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "hospital-waiting-time-analytics/1.0"})

    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        if partial.stat().st_size == 0:
            raise ValueError("The downloaded file is empty")
        partial.replace(output)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    print(f"Downloaded raw data to: {output.as_posix()}")
    return output


def main() -> None:
    args = parse_args()
    download_csv(args.url, args.output, args.force)


if __name__ == "__main__":
    main()
