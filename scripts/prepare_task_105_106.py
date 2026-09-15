"""Prepare the session-aware task_105 and per-turn task_106 datasets."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


EXTRACTION_COLUMN_LETTERS = tuple("DEFGHIJK")


def _read_xlsx(path: Path) -> list[dict[str, str]]:
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as workbook:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", namespace):
                shared_strings.append("".join(t.text or "" for t in item.iterfind(".//m:t", namespace)))

        sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        rows: list[dict[str, str]] = []
        headers: dict[str, str] = {}
        for row in sheet.findall(".//m:sheetData/m:row", namespace):
            values: dict[str, str] = {}
            for cell in row.findall("m:c", namespace):
                column = "".join(ch for ch in cell.attrib["r"] if ch.isalpha())
                value = cell.find("m:v", namespace)
                text = "" if value is None else value.text or ""
                if cell.attrib.get("t") == "s" and text:
                    text = shared_strings[int(text)]
                values[column] = text.strip()
            if values.get("A") == "会话id":
                headers = values
                continue
            extraction = {
                headers[column]: values.get(column, "")
                for column in EXTRACTION_COLUMN_LETTERS
                if headers.get(column)
            }
            rows.append({
                "session_id": values.get("A", ""),
                "input": values.get("B", ""),
                "业务类别": values.get("C", ""),
                **extraction,
            })
    return rows


def _gold(row: dict[str, str]) -> str:
    information = {
        column: row[column]
        for column in row
        if column not in {"session_id", "input", "业务类别"}
        if row.get(column)
    }
    return json.dumps(
        {"业务类别": row["业务类别"], "信息提取": information},
        ensure_ascii=False,
    )


def _cumulative_gold(row: dict[str, str], information: dict[str, str]) -> str:
    return json.dumps(
        {"业务类别": row["业务类别"], "信息提取": information},
        ensure_ascii=False,
    )


def build_task_records(rows: Iterable[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return gold-history task_105 records and user-only task_106 records."""
    conversations: dict[str, list[dict[str, str]]] = {}

    for row in rows:
        if not row["session_id"] or not row["input"]:
            raise ValueError("会话 ID 和输入不能为空")
        conversations.setdefault(row["session_id"], []).append(row)

    task_105: list[dict[str, str]] = []
    task_106: list[dict[str, str]] = []
    for conversation in conversations.values():
        inputs: list[str] = []
        task_105_messages: list[dict[str, str]] = []
        cumulative_information: dict[str, str] = {}
        turn_count = len(conversation)
        session_id = conversation[0]["session_id"]
        for turn_index, row in enumerate(conversation, start=1):
            inputs.append(f"用户：{row['input']}")
            task_105_messages.append({"role": "HUMAN", "prompt": inputs[-1]})
            for column, value in row.items():
                if column not in {"session_id", "input", "业务类别"} and value:
                    cumulative_information[column] = value
            current_gold = _cumulative_gold(row, cumulative_information)
            task_105.append({
                "session_id": session_id,
                "turn_index": turn_index,
                "turn_count": turn_count,
                "input": list(task_105_messages),
                "output": current_gold,
            })
            task_106.append({
                "input": list(inputs),
                "output": current_gold,
            })
    return task_105, task_106


def _write_jsonl(path: Path, records: Iterable[dict[str, str]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/custom_task"))
    args = parser.parse_args()
    rows = _read_xlsx(args.xlsx)
    task_105, task_106 = build_task_records(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.output_dir / "task_105.jsonl", task_105)
    _write_jsonl(args.output_dir / "task_106.jsonl", task_106)
    print(f"rows={len(rows)} task_105_turns={len(task_105)} task_106_turns={len(task_106)}")


if __name__ == "__main__":
    main()
