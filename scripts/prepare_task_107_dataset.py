"""Build task_107 from the binary classification source workbook."""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"m": NAMESPACE}


def read_source_rows(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as workbook:
        shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
        shared_strings = [
            "".join(t.text or "" for t in item.iterfind(".//m:t", NS))
            for item in shared_root.findall("m:si", NS)
        ]
        sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet.findall(".//m:sheetData/m:row", NS):
            values = {}
            for cell in row.findall("m:c", NS):
                column = "".join(ch for ch in cell.attrib["r"] if ch.isalpha())
                value = cell.find("m:v", NS)
                text = "" if value is None else value.text or ""
                if cell.attrib.get("t") == "s" and text:
                    text = shared_strings[int(text)]
                values[column] = text
            if values.get("A") == "alarm_name":
                continue
            if values.get("B", "").strip():
                rows.append({
                    "input": values["B"],
                    "gold": values.get("E", "").strip(),
                    "online": values.get("F", "").strip(),
                })
    return rows


def deduplicate_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, float | int]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["input"]].append(row)

    conflicts = {
        input_text: group
        for input_text, group in grouped.items()
        if len({row["gold"] for row in group}) > 1
    }
    kept = [group[0] for input_text, group in grouped.items() if input_text not in conflicts]
    online_correct_raw = sum(row["gold"].lower() == row["online"].lower() for row in rows)
    online_correct_kept = sum(row["gold"].lower() == row["online"].lower() for row in kept)
    stats = {
        "raw_rows": len(rows),
        "unique_inputs": len(grouped),
        "duplicate_groups": sum(len(group) > 1 for group in grouped.values()),
        "conflict_groups": len(conflicts),
        "conflict_rows": sum(len(group) for group in conflicts.values()),
        "kept_rows": len(kept),
        "online_accuracy_raw": online_correct_raw / len(rows) * 100 if rows else 0.0,
        "online_accuracy_kept": online_correct_kept / len(kept) * 100 if kept else 0.0,
    }
    return kept, stats


def write_dataset(path: Path, rows: list[dict[str, str]]) -> None:
    path.write_text(
        "".join(
            json.dumps({"input": row["input"], "output": row["gold"]}, ensure_ascii=False) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/custom_task/task_107.jsonl"))
    args = parser.parse_args()
    rows = read_source_rows(args.xlsx)
    kept, stats = deduplicate_rows(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_dataset(args.output, kept)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
