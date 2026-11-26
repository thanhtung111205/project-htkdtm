"""Prepare the private context seed for ``dw.dim_event`` after event review.

The input seed is local-only. Version dates derived from the first review that
mentions a version are kept for traceability but marked needs_review because
they are not verified release dates.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import date
from pathlib import Path


OUTPUT_COLUMNS = (
    "event_type",
    "start_date",
    "end_date",
    "description",
    "platform_name",
    "needs_review",
)

# These are reviewed/corrected records from the 30 seed rows marked
# can_kiem_tra. Duplicates and false positives are documented in
# docs/ra_soat_dim_event.md; only the canonical records are emitted here.
REVIEWED_EVENTS = (
    {
        "event_type": "khuyen_mai",
        "start_date": "2021-10-20",
        "end_date": "2021-11-20",
        "description": "HOCMAI x MoMo: goi hoc mot thang con 10.000 dong",
        "platform_name": "HOCMAI",
        "needs_review": "false",
    },
    {
        "event_type": "khuyen_mai",
        "start_date": "2021-11-01",
        "end_date": "2021-11-30",
        "description": "HOCMAI x ShopeePay: giam 50 phan tram hoc phi",
        "platform_name": "HOCMAI",
        "needs_review": "false",
    },
    {
        "event_type": "cap_nhat",
        "start_date": "2023-10-27",
        "end_date": "",
        "description": "ELSA Speak cong bo tinh nang tu tao hoi thoai voi AI; ngay phat hanh thuc te chua xac minh",
        "platform_name": "ELSA Speak",
        "needs_review": "true",
    },
    {
        "event_type": "khuyen_mai",
        "start_date": "2024-04-16",
        "end_date": "",
        "description": "ELSA dong hanh hoc bong S-Global 2, ho tro toi 65 phan tram hoc phi; thoi han chuong trinh chua xac minh",
        "platform_name": "ELSA Speak",
        "needs_review": "true",
    },
    {
        "event_type": "cap_nhat",
        "start_date": "2025-02-18",
        "end_date": "",
        "description": "ELSA Speak cong bo phien ban AI the he moi; ngay phat hanh thuc te chua xac minh",
        "platform_name": "ELSA Speak",
        "needs_review": "true",
    },
    {
        "event_type": "cap_nhat",
        "start_date": "2025-04-22",
        "end_date": "2025-06-10",
        "description": "Duolingo Chess: thu nghiem beta iOS tu 22/04, cong bo ra mat rong hon 10/06/2025",
        "platform_name": "DUOLINGO",
        "needs_review": "false",
    },
    {
        "event_type": "cap_nhat",
        "start_date": "2025-10-10",
        "end_date": "",
        "description": "Duolingo mo rong khoa hoc tieng Nhat; bai bao noi cap nhat trung voi anime, ngay rollout chua xac minh",
        "platform_name": "DUOLINGO",
        "needs_review": "true",
    },
    {
        "event_type": "khuyen_mai",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "description": "Duolingo cho khoi phuc streak da mat trong chien dich thang 6/2026",
        "platform_name": "DUOLINGO",
        "needs_review": "false",
    },
    {
        "event_type": "mua_thi",
        "start_date": "2025-06-26",
        "end_date": "2025-06-27",
        "description": "Ky thi tot nghiep THPT quoc gia 2025",
        "platform_name": "",
        "needs_review": "false",
    },
    {
        "event_type": "mua_thi",
        "start_date": "2026-06-11",
        "end_date": "2026-06-12",
        "description": "Ky thi tot nghiep THPT quoc gia 2026",
        "platform_name": "",
        "needs_review": "false",
    },
)


def prepare_events(input_path: Path, output_path: Path) -> dict[str, int]:
    """Convert the local source seed into the reviewed loader format."""
    with input_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"event_date", "platform", "event_type", "event_name", "confidence", "note"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Thieu cot trong seed: " + ", ".join(sorted(missing)))
        source_rows = list(reader)

    prepared: list[dict[str, str]] = []
    skipped = Counter()
    for row in source_rows:
        kind = row["event_type"].strip()
        confidence = row["confidence"].strip()
        if kind == "phien_ban_ung_dung":
            observed = date.fromisoformat(row["event_date"].strip()).isoformat()
            prepared.append(
                {
                    "event_type": "cap_nhat",
                    "start_date": observed,
                    "end_date": "",
                    "description": (
                        row["event_name"].strip()
                        + "; ngay thay phien ban dau tien trong review, chua chac la ngay phat hanh"
                    ),
                    "platform_name": row["platform"].strip(),
                    "needs_review": "true",
                }
            )
        elif kind == "ngay_sale_lon" and confidence == "cao":
            event_date = date.fromisoformat(row["event_date"].strip()).isoformat()
            prepared.append(
                {
                    "event_type": "khuyen_mai",
                    "start_date": event_date,
                    "end_date": event_date,
                    "description": row["event_name"].strip() + " (su kien sale thuong mai dien tu chung)",
                    "platform_name": "",
                    "needs_review": "false",
                }
            )
        elif confidence == "can_kiem_tra":
            # Emit only canonical reviewed records below; all raw candidates are
            # individually dispositioned in the audit document.
            skipped["flagged_candidates_replaced_by_reviewed_manifest"] += 1
        elif kind == "mua_vu_khai_giang":
            # Opening day is not an exam period; official exam dates are added below.
            skipped["school_opening_not_exam"] += 1
        else:
            skipped["unsupported_or_unreviewed"] += 1

    prepared.extend(REVIEWED_EVENTS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(prepared)

    return {
        "source_rows": len(source_rows),
        "prepared_rows": len(prepared),
        "needs_review": sum(row["needs_review"] == "true" for row in prepared),
        "ready": sum(row["needs_review"] == "false" for row in prepared),
        **dict(skipped),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Chuan bi seed dim_event da ra soat.")
    root = Path(__file__).resolve().parents[3]
    parser.add_argument(
        "--input",
        type=Path,
        default=root / "data" / "raw" / "context" / "dim_event_seed.csv",
        help="Seed nguon rieng, khong dua len Git",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "data" / "clean" / "dim_event_seed.csv",
        help="CSV da chuan bi cho load_events.py, khong dua len Git",
    )
    args = parser.parse_args()
    counts = prepare_events(args.input, args.output)
    print(f"Da tao {counts['prepared_rows']} su kien tai {args.output}.")
    print(
        f"Can ra soat them: {counts['needs_review']}; co the dung: {counts['ready']}; "
        f"dong nguon: {counts['source_rows']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
