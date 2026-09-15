"""Normalize task_105 categories in the source XLSX and rebuild JSONL datasets."""

from __future__ import annotations

import argparse
import re
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from scripts.prepare_task_105_106 import _read_xlsx
except ModuleNotFoundError:  # Running this file directly from the scripts directory.
    from prepare_task_105_106 import _read_xlsx


NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"m": NAMESPACE}
CATEGORY = "装维主动领单"
PATTERN = re.compile(r"转我|领单|派我")


def _shared_strings(root: ET.Element) -> list[str]:
    return [
        "".join(t.text or "" for t in item.iterfind(".//m:t", NS))
        for item in root.findall("m:si", NS)
    ]


def normalize_xlsx(path: Path) -> int:
    """Update C cells whose B-cell input matches PATTERN, preserving workbook entries."""
    with zipfile.ZipFile(path, "r") as source:
        shared_root = ET.fromstring(source.read("xl/sharedStrings.xml"))
        shared = _shared_strings(shared_root)
        if CATEGORY not in shared:
            shared.append(CATEGORY)
            si = ET.SubElement(shared_root, f"{{{NAMESPACE}}}si")
            t = ET.SubElement(si, f"{{{NAMESPACE}}}t")
            t.text = CATEGORY
        category_index = shared.index(CATEGORY)

        sheet_root = ET.fromstring(source.read("xl/worksheets/sheet1.xml"))
        changed = 0
        for row in sheet_root.findall(".//m:sheetData/m:row", NS):
            cells = {}
            for cell in row.findall("m:c", NS):
                column = "".join(ch for ch in cell.attrib["r"] if ch.isalpha())
                cells[column] = cell
            b_cell = cells.get("B")
            if b_cell is None:
                continue
            value = b_cell.find("m:v", NS)
            if value is None or b_cell.attrib.get("t") != "s":
                continue
            if not PATTERN.search(shared[int(value.text or "0")]):
                continue
            c_cell = cells.get("C")
            if c_cell is None:
                continue
            c_cell.attrib["t"] = "s"
            c_value = c_cell.find("m:v", NS)
            if c_value is None:
                c_value = ET.SubElement(c_cell, f"{{{NAMESPACE}}}v")
            c_value.text = str(category_index)
            changed += 1

        ET.register_namespace("", NAMESPACE)
        shared_xml = ET.tostring(shared_root, encoding="utf-8", xml_declaration=True)
        sheet_xml = ET.tostring(sheet_root, encoding="utf-8", xml_declaration=True)

        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".xlsx", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with zipfile.ZipFile(tmp_path, "w") as target:
                for item in source.infolist():
                    data = shared_xml if item.filename == "xl/sharedStrings.xml" else sheet_xml if item.filename == "xl/worksheets/sheet1.xml" else source.read(item)
                    target.writestr(item, data)
            tmp_path.replace(path)
        finally:
            tmp_path.unlink(missing_ok=True)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/custom_task"))
    args = parser.parse_args()
    changed = normalize_xlsx(args.xlsx)
    rows = _read_xlsx(args.xlsx)
    try:
        from scripts.prepare_task_105_106 import _write_jsonl, build_task_records
    except ModuleNotFoundError:
        from prepare_task_105_106 import _write_jsonl, build_task_records

    task_105, task_106 = build_task_records(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.output_dir / "task_105.jsonl", task_105)
    _write_jsonl(args.output_dir / "task_106.jsonl", task_106)
    print(f"updated_rows={changed} rows={len(rows)} task_105_turns={len(task_105)} task_106_turns={len(task_106)}")


if __name__ == "__main__":
    main()
