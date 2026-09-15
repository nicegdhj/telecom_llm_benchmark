#!/usr/bin/env python3
"""Build an exact-payload-disjoint SFT set for task_107.

The source workbook contains the gold label in ``label_res`` and another
model's result in ``chatglm3-6b_res``.  The current evaluation set is removed
by normalized payload before sampling.
"""

import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from scripts.review_task_107_labels import match_rules


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "mydata/task_107/binary_deduplicated_lora_result.xlsx"
TEST = ROOT / "mydata/task_107/binary_chatglm3_lora_result.xlsx"
REVIEW = (
    ROOT
    / "outputs/lora-ckpt1200_aggregated_reports_20260730_150710"
    / "task_107_suite/sp_0729_qwen-3-6-27b-lora-ckpt1200"
    / "task_107_label_review.xlsx"
)
OUT_DIR = ROOT / "mydata/task_107/train"
SEED = 107
TARGET_PER_LABEL = 20000

YES_CATEGORY_ORDER = (
    "login_plaintext",
    "scanner_user_agent",
    "connect_tunnel",
    "admin_api_probe",
    "dynamic_script_path",
    "strong_attack_rule",
    "other_yes",
)

LOGIN_PLAINTEXT_PATTERN = re.compile(
    r"^\s*(?:get|post|put|patch)\s+[^\r\n]*login[^\r\n]*?"
    r"[\s\S]{0,4000}?(?:[?&\s])password\s*=\s*"
    r"(?![0-9a-f]{32}(?:[&\s]|$))"
    r"(?![0-9a-f]{40}(?:[&\s]|$))"
    r"(?![0-9a-f]{64}(?:[&\s]|$))"
    r"[^&\s]{1,128}",
    re.IGNORECASE,
)
SCANNER_PATTERN = re.compile(
    r"user-agent\s*:[^\r\n]*"
    r"(?:sqlmap|nikto|nmap|masscan|acunetix|nessus|zgrab|"
    r"gobuster|dirbuster|wpscan)",
    re.IGNORECASE,
)
CONNECT_PATTERN = re.compile(r"^\s*connect\s+", re.IGNORECASE)
ADMIN_API_PATTERN = re.compile(
    r"^\s*\w+\s+/[^\s]*"
    r"(?:admin|actuator|druid|console|manager|nacos|swagger|"
    r"cgi-bin|webadmin|oprocmgr|api/)",
    re.IGNORECASE,
)
DYNAMIC_SCRIPT_PATTERN = re.compile(
    r"^\s*\w+\s+/\S*\.(?:php\d*|phtml|jsp|jspx|asp|aspx|cgi)"
    r"(?:[?/\s]|$)",
    re.IGNORECASE,
)

SYSTEM_PROMPT = (
    "Act as a cybersecurity analyst who is skilled in identifying and assessing "
    "potential threats in textual data.\n"
    "Please analyze the following request payload to determine if it represents "
    "a web attack.\n"
    "Here is the given payload of the request:\n"
    "{}\n"
    "Respond only with 'Yes' if it is a web attack, or 'No' if it is not."
)


def normalize_payload(value):
    text = "" if pd.isna(value) else str(value)
    text = text.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    text = text.strip()
    return "\n".join(line.rstrip() for line in text.split("\n"))


def normalize_label(value):
    text = "" if pd.isna(value) else str(value).strip().lower()
    if text.startswith("yes"):
        return "Yes"
    if text.startswith("no"):
        return "No"
    return "INVALID"


def family_key(payload):
    """Coarse audit key: method + path without query parameters."""
    first = payload.lower().splitlines()[0] if payload else ""
    match = re.match(r"\s*(\w+)\s+(\S+)", first)
    if not match:
        return first[:120]
    return f"{match.group(1)} {match.group(2).split('?')[0]}"


def stable_key(payload):
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def classify_yes_case(payload: str) -> str:
    """Classify a Yes payload using the documented exclusive priority."""
    if LOGIN_PLAINTEXT_PATTERN.search(payload):
        return "login_plaintext"
    if SCANNER_PATTERN.search(payload):
        return "scanner_user_agent"
    if CONNECT_PATTERN.search(payload):
        return "connect_tunnel"
    if ADMIN_API_PATTERN.search(payload):
        return "admin_api_probe"
    if DYNAMIC_SCRIPT_PATTERN.search(payload):
        return "dynamic_script_path"
    if any(rule.strength == "strong" for rule, _ in match_rules(payload)):
        return "strong_attack_rule"
    return "other_yes"


def _clean_selection_rows(rows, forbidden_payloads):
    normalized = []
    labels_by_payload = {}
    for source_row in rows:
        payload = normalize_payload(source_row.get("payload_norm", ""))
        gold = normalize_label(source_row.get("gold", ""))
        if not payload or gold not in {"Yes", "No"} or payload in forbidden_payloads:
            continue
        labels_by_payload.setdefault(payload, set()).add(gold)
        row = dict(source_row)
        row["payload_norm"] = payload
        row["gold"] = gold
        row["other_wrong"] = bool(row.get("other_wrong", False))
        normalized.append(row)

    conflicts = {
        payload for payload, labels in labels_by_payload.items() if len(labels) > 1
    }
    unique = {}
    for row in normalized:
        payload = row["payload_norm"]
        if payload not in conflicts and payload not in unique:
            unique[payload] = row
    return unique


def _take_seeded(rows, count, rng):
    if count < 0 or len(rows) < count:
        raise RuntimeError(f"Not enough candidates: need {count}, got {len(rows)}")
    ordered = sorted(rows, key=lambda row: stable_key(row["payload_norm"]))
    rng.shuffle(ordered)
    return ordered[:count]


def select_training_rows(
    candidates,
    existing_rows,
    forbidden_payloads,
    target_per_label,
    seed,
):
    """Select a balanced set while preserving existing rows and target coverage."""
    forbidden = {normalize_payload(payload) for payload in forbidden_payloads if payload}
    candidate_map = _clean_selection_rows(candidates, forbidden)
    existing_map = _clean_selection_rows(existing_rows, forbidden)
    retained = [
        candidate_map[payload]
        for payload in existing_map
        if payload in candidate_map
    ]
    retained.sort(key=lambda row: stable_key(row["payload_norm"]))

    retained_counts = Counter(row["gold"] for row in retained)
    for label in ("Yes", "No"):
        if retained_counts[label] > target_per_label:
            raise RuntimeError(
                f"Existing {label} rows exceed target: "
                f"{retained_counts[label]} > {target_per_label}"
            )

    rng = random.Random(seed)
    selected = list(retained)
    used = {row["payload_norm"] for row in retained}

    remaining_yes = [
        row
        for payload, row in candidate_map.items()
        if payload not in used and row["gold"] == "Yes"
    ]
    targeted_yes = [
        row for row in remaining_yes if classify_yes_case(row["payload_norm"]) != "other_yes"
    ]
    yes_capacity = target_per_label - retained_counts["Yes"]
    if len(targeted_yes) > yes_capacity:
        raise RuntimeError(
            f"Targeted Yes rows exceed available capacity: "
            f"{len(targeted_yes)} > {yes_capacity}"
        )
    targeted_yes.sort(
        key=lambda row: (
            YES_CATEGORY_ORDER.index(classify_yes_case(row["payload_norm"])),
            stable_key(row["payload_norm"]),
        )
    )
    selected.extend(targeted_yes)
    used.update(row["payload_norm"] for row in targeted_yes)

    yes_fill_count = target_per_label - retained_counts["Yes"] - len(targeted_yes)
    yes_fill_pool = [
        row
        for row in remaining_yes
        if row["payload_norm"] not in used
        and classify_yes_case(row["payload_norm"]) == "other_yes"
    ]
    yes_hard = [row for row in yes_fill_pool if row["other_wrong"]]
    yes_normal = [row for row in yes_fill_pool if not row["other_wrong"]]
    yes_hard_take = min(len(yes_hard), yes_fill_count)
    yes_fill = _take_seeded(yes_hard, yes_hard_take, rng)
    yes_fill.extend(
        _take_seeded(yes_normal, yes_fill_count - yes_hard_take, rng)
    )
    selected.extend(yes_fill)
    used.update(row["payload_norm"] for row in yes_fill)

    no_fill_count = target_per_label - retained_counts["No"]
    no_pool = [
        row
        for payload, row in candidate_map.items()
        if payload not in used and row["gold"] == "No"
    ]
    no_hard = [row for row in no_pool if row["other_wrong"]]
    no_normal = [row for row in no_pool if not row["other_wrong"]]
    no_hard_take = min(len(no_hard), no_fill_count)
    no_fill = _take_seeded(no_hard, no_hard_take, rng)
    no_fill.extend(_take_seeded(no_normal, no_fill_count - no_hard_take, rng))
    selected.extend(no_fill)

    rng.shuffle(selected)
    final_categories = Counter(
        classify_yes_case(row["payload_norm"])
        for row in selected
        if row["gold"] == "Yes"
    )
    added_payloads = {
        row["payload_norm"] for row in selected
    } - {row["payload_norm"] for row in retained}
    added_categories = Counter(
        classify_yes_case(row["payload_norm"])
        for row in selected
        if row["gold"] == "Yes" and row["payload_norm"] in added_payloads
    )
    report = {
        "preserved_existing": {
            label: retained_counts[label] for label in ("Yes", "No")
        },
        "added": {
            label: target_per_label - retained_counts[label]
            for label in ("Yes", "No")
        },
        "yes_category_final": {
            category: final_categories[category] for category in YES_CATEGORY_ORDER
        },
        "yes_category_added": {
            category: added_categories[category] for category in YES_CATEGORY_ORDER
        },
    }
    return selected, report


def build_report(
    selected,
    selection_report,
    test_payloads,
    review_payloads,
    error_families,
    baseline_existing_hashes,
    source_stats,
):
    """Build the auditable summary for a selected training set."""
    selected_payloads = {row["payload_norm"] for row in selected}
    selected_hashes = {stable_key(payload) for payload in selected_payloads}
    label_counts = Counter(row["gold"] for row in selected)
    wrong_counts = Counter(bool(row.get("other_wrong", False)) for row in selected)
    report = {
        "seed": SEED,
        "target_per_label": TARGET_PER_LABEL,
        "train_size": len(selected),
        "train_label_counts": {
            label: label_counts[label] for label in ("Yes", "No")
        },
        "train_unique_payloads": len(selected_payloads),
        "train_other_model_wrong_counts": {
            "false": wrong_counts[False],
            "true": wrong_counts[True],
        },
        "selection": selection_report,
        "baseline_existing_count": len(baseline_existing_hashes),
        "baseline_existing_preserved": len(
            selected_hashes & set(baseline_existing_hashes)
        ),
        "baseline_existing_payload_hashes": sorted(baseline_existing_hashes),
        "exact_overlap_with_full_test": len(selected_payloads & test_payloads),
        "exact_overlap_with_label_review": len(selected_payloads & review_payloads),
        "error_family_overlap_selected": sum(
            family_key(payload) in error_families for payload in selected_payloads
        ),
    }
    report.update(source_stats)
    return report


def main():
    source = pd.read_excel(SOURCE)
    test = pd.read_excel(TEST)
    review = pd.read_excel(REVIEW, sheet_name="全部错误_规则分析")

    source["payload_norm"] = source["payload"].map(normalize_payload)
    source["gold"] = source["label_res"].map(normalize_label)
    source["other_pred"] = source["chatglm3-6b_res"].map(normalize_label)
    test_payloads = set(test["payload"].map(normalize_payload)) - {""}
    review["payload_norm"] = review["payload"].map(normalize_payload)
    review["gold"] = review["标记"].map(normalize_label)
    review_payloads = set(review["payload_norm"]) - {""}
    error_families = {
        family_key(payload)
        for payload in review.loc[review["gold"] == "Yes", "payload_norm"]
        if payload
    }
    forbidden_payloads = test_payloads | review_payloads

    # Remove invalid records and any source payload appearing in the test set.
    candidates = source[
        source["payload_norm"].ne("")
        & source["gold"].isin(["Yes", "No"])
        & ~source["payload_norm"].isin(forbidden_payloads)
    ].copy()

    # Source is already unique, but keep this guard so the output remains safe
    # if the workbook is replaced later.
    candidates = candidates.drop_duplicates("payload_norm", keep="first")
    conflict_counts = source.groupby("payload_norm")["gold"].nunique()
    conflict_payloads = set(conflict_counts[conflict_counts > 1].index)
    candidates = candidates[~candidates["payload_norm"].isin(conflict_payloads)].copy()

    candidates["other_wrong"] = candidates["gold"] != candidates["other_pred"]
    candidates["family"] = candidates["payload_norm"].map(family_key)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    train_path = OUT_DIR / "task_107_lora_train.jsonl"
    report_path = OUT_DIR / "build_report.json"
    previous_report = {}
    if report_path.is_file():
        previous_report = json.loads(report_path.read_text(encoding="utf-8"))
    baseline_hashes = set(previous_report.get("baseline_existing_payload_hashes", []))

    existing_rows = []
    if train_path.is_file():
        with train_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                record = json.loads(line)
                messages = record.get("messages", [])
                if len(messages) != 3:
                    raise ValueError(
                        f"Existing training row {line_number} must contain 3 messages"
                    )
                payload = normalize_payload(messages[1].get("content", ""))
                gold = normalize_label(messages[2].get("content", ""))
                if baseline_hashes and stable_key(payload) not in baseline_hashes:
                    continue
                existing_rows.append({"payload_norm": payload, "gold": gold})

    if not baseline_hashes:
        baseline_hashes = {
            stable_key(row["payload_norm"])
            for row in existing_rows
            if row["payload_norm"]
        }

    candidate_rows = candidates.to_dict("records")
    selected, selection_report = select_training_rows(
        candidates=candidate_rows,
        existing_rows=existing_rows,
        forbidden_payloads=forbidden_payloads,
        target_per_label=TARGET_PER_LABEL,
        seed=SEED,
    )

    records = []
    for row in selected:
        records.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": row["payload_norm"]},
                    {"role": "assistant", "content": row["gold"]},
                ]
            }
        )

    train_temporary = train_path.with_name(f".{train_path.name}.tmp")
    with train_temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    train_temporary.replace(train_path)

    # LLaMA-Factory dataset registration. The dataset directory in the
    # deployment YAML should contain both this file and dataset_info.json.
    dataset_info = {
        "task_107_lora_train": {
            "file_name": "task_107_lora_train.jsonl",
            "formatting": "sharegpt",
            "columns": {"messages": "messages"},
            "tags": {
                "role_tag": "role",
                "content_tag": "content",
                "user_tag": "user",
                "assistant_tag": "assistant",
                "system_tag": "system",
            },
        }
    }
    dataset_info_path = OUT_DIR / "dataset_info.json"
    dataset_info_temporary = dataset_info_path.with_name(
        f".{dataset_info_path.name}.tmp"
    )
    dataset_info_temporary.write_text(
        json.dumps(dataset_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    dataset_info_temporary.replace(dataset_info_path)

    prompt_path = OUT_DIR / "system_prompt.txt"
    prompt_temporary = prompt_path.with_name(f".{prompt_path.name}.tmp")
    prompt_temporary.write_text(SYSTEM_PROMPT + "\n", encoding="utf-8")
    prompt_temporary.replace(prompt_path)

    available_categories = Counter(
        classify_yes_case(payload)
        for payload in candidates.loc[candidates["gold"] == "Yes", "payload_norm"]
    )
    source_stats = {
        "source": str(SOURCE),
        "test": str(TEST),
        "label_review": str(REVIEW),
        "source_rows": len(source),
        "source_unique_payloads": int(source["payload_norm"].nunique()),
        "test_unique_payloads": len(test_payloads),
        "label_review_unique_payloads": len(review_payloads),
        "candidate_rows_after_exact_test_exclusion": len(candidates),
        "candidate_label_counts": {
            label: int((candidates["gold"] == label).sum())
            for label in ("Yes", "No")
        },
        "yes_category_available": {
            category: available_categories[category]
            for category in YES_CATEGORY_ORDER
        },
        "candidate_family_overlap_with_test": int(
            candidates["family"].isin({family_key(p) for p in test_payloads if p}).sum()
        ),
        "candidate_family_overlap_with_errors": int(
            candidates["family"].isin(error_families).sum()
        ),
        "note": (
            "Exact payload overlap with both the full test set and label review "
            "is prohibited. Method+path family overlap is reported as intended "
            "same-type coverage and is not exact leakage."
        ),
    }
    report = build_report(
        selected=selected,
        selection_report=selection_report,
        test_payloads=test_payloads,
        review_payloads=review_payloads,
        error_families=error_families,
        baseline_existing_hashes=baseline_hashes,
        source_stats=source_stats,
    )
    targeted_categories = YES_CATEGORY_ORDER[:-1]
    report["all_available_targeted_yes_selected"] = all(
        selection_report["yes_category_final"][category]
        == available_categories[category]
        for category in targeted_categories
    )
    report_temporary = report_path.with_name(f".{report_path.name}.tmp")
    report_temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_temporary.replace(report_path)
    console_report = dict(report)
    console_report["baseline_existing_payload_hashes"] = (
        f"{len(baseline_hashes)} hashes stored in build_report.json"
    )
    print(json.dumps(console_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
