#!/usr/bin/env python3
"""Evaluate unordered tool calls at complete-trace level.

Tool Name compares sets of function names. Tool Operation compares sets of
``(function name, normalized arguments)``. Call order, step position and
duplicate calls are ignored for the main metrics.
"""

import argparse
import json
import math
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate trace-level, order-independent tool-call precision/recall/F1."
    )
    parser.add_argument(
        "--reference",
        default="data/auto_plan.gend.test.jsonl",
        help="Reference JSONL containing gen.messages.",
    )
    parser.add_argument(
        "predictions",
        nargs="+",
        help="One or more inference JSONL files produced by infer_trace_steps.py.",
    )
    parser.add_argument(
        "--json-output",
        help="Optional path at which to save all evaluation results as JSON.",
    )
    parser.add_argument(
        "--details-output",
        help="Optional JSONL path for per-trace TP/FP/FN details.",
    )
    return parser.parse_args()


def read_jsonl(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc


def normalize_value(value):
    """Return a stable, JSON-compatible representation."""
    if isinstance(value, dict):
        return {str(key): normalize_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        if value.is_integer():
            return int(value)
    if isinstance(value, str):
        return value.strip()
    return value


def normalize_arguments(arguments):
    """Canonicalize function arguments and report whether JSON parsing succeeded."""
    if arguments is None or arguments == "":
        value = {}
        valid_json = True
    elif isinstance(arguments, str):
        try:
            value = json.loads(arguments)
            valid_json = True
        except json.JSONDecodeError:
            # Keep malformed output distinguishable instead of silently discarding it.
            value = {"__raw_invalid_json__": arguments.strip()}
            valid_json = False
    else:
        value = arguments
        valid_json = isinstance(arguments, (dict, list))
    canonical = json.dumps(
        normalize_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return canonical, valid_json


def extract_calls(message):
    """Extract (name, canonical arguments, arguments-valid) tuples."""
    calls = []
    if not isinstance(message, dict):
        return calls
    for call in message.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        function = call.get("function")
        if not isinstance(function, dict) or not function.get("name"):
            continue
        arguments, valid_json = normalize_arguments(function.get("arguments"))
        calls.append((str(function["name"]), arguments, valid_json))
    # Accept the legacy OpenAI function_call shape as well.
    function = message.get("function_call")
    if isinstance(function, dict) and function.get("name"):
        arguments, valid_json = normalize_arguments(function.get("arguments"))
        calls.append((str(function["name"]), arguments, valid_json))
    return calls


def load_reference(path):
    traces = {}
    for source_index, record in enumerate(read_jsonl(path)):
        gen = record.get("gen")
        if not isinstance(gen, dict) or not isinstance(gen.get("messages"), list):
            raise ValueError(f"Reference record {source_index} has no gen.messages list")
        calls = []
        for message in gen["messages"]:
            if message.get("role") == "assistant":
                calls.extend(extract_calls(message))
        traces[source_index] = calls
    return traces


def load_predictions(path):
    traces = {}
    seen_steps = set()
    row_count = 0
    for row in read_jsonl(path):
        row_count += 1
        if "source_index" not in row or "step_index" not in row:
            raise ValueError(f"{path}: prediction row lacks source_index or step_index")
        source_index = int(row["source_index"])
        step_key = (source_index, int(row["step_index"]))
        if step_key in seen_steps:
            raise ValueError(f"{path}: duplicate prediction step {step_key}")
        seen_steps.add(step_key)
        traces.setdefault(source_index, []).extend(extract_calls(row.get("assistant")))
    return traces, row_count


def safe_ratio(numerator, denominator):
    # If neither side contains an item, the prediction is perfect for that trace.
    return numerator / denominator if denominator else 1.0


def score_sets(reference_sets, prediction_sets):
    details = []
    total_tp = total_fp = total_fn = 0
    macro_precision = macro_recall = macro_f1 = 0.0
    exact = 0

    for source_index in sorted(reference_sets):
        reference = reference_sets[source_index]
        prediction = prediction_sets.get(source_index, set())
        tp_items = reference & prediction
        fp_items = prediction - reference
        fn_items = reference - prediction
        tp, fp, fn = len(tp_items), len(fp_items), len(fn_items)
        precision = safe_ratio(tp, tp + fp)
        recall = safe_ratio(tp, tp + fn)
        if precision + recall:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = 1.0 if not reference and not prediction else 0.0
        total_tp += tp
        total_fp += fp
        total_fn += fn
        macro_precision += precision
        macro_recall += recall
        macro_f1 += f1
        exact += reference == prediction
        details.append(
            {
                "source_index": source_index,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "exact_match": reference == prediction,
                "false_positives": sorted(fp_items),
                "false_negatives": sorted(fn_items),
            }
        )

    count = len(reference_sets)
    micro_precision = safe_ratio(total_tp, total_tp + total_fp)
    micro_recall = safe_ratio(total_tp, total_tp + total_fn)
    if micro_precision + micro_recall:
        micro_f1 = (
            2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        )
    else:
        has_any_item = bool(total_tp + total_fp + total_fn)
        micro_f1 = 0.0 if has_any_item else 1.0
    return {
        "micro": {
            "precision": micro_precision,
            "recall": micro_recall,
            "f1": micro_f1,
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
        },
        "macro": {
            "precision": macro_precision / count if count else 0.0,
            "recall": macro_recall / count if count else 0.0,
            "f1": macro_f1 / count if count else 0.0,
        },
        "trace_exact_match": {
            "count": exact,
            "total": count,
            "rate": exact / count if count else 0.0,
        },
        "details": details,
    }


def trace_sets(calls_by_trace, mode):
    if mode == "name":
        return {
            index: {name for name, _arguments, _valid in calls}
            for index, calls in calls_by_trace.items()
        }
    if mode == "operation":
        return {
            index: {(name, arguments) for name, arguments, _valid in calls}
            for index, calls in calls_by_trace.items()
        }
    raise ValueError(mode)


def format_item(item):
    if isinstance(item, tuple):
        return {"name": item[0], "arguments": json.loads(item[1])}
    return item


def make_json_safe_details(details):
    output = []
    for detail in details:
        item = dict(detail)
        item["false_positives"] = [format_item(value) for value in detail["false_positives"]]
        item["false_negatives"] = [format_item(value) for value in detail["false_negatives"]]
        output.append(item)
    return output


def evaluate(reference_calls, prediction_calls):
    name = score_sets(
        trace_sets(reference_calls, "name"), trace_sets(prediction_calls, "name")
    )
    operation = score_sets(
        trace_sets(reference_calls, "operation"),
        trace_sets(prediction_calls, "operation"),
    )
    invalid_arguments = sum(
        not valid for calls in prediction_calls.values() for _name, _args, valid in calls
    )
    predicted_call_count = sum(len(calls) for calls in prediction_calls.values())
    return {
        "tool_name": {key: value for key, value in name.items() if key != "details"},
        "tool_operation": {
            key: value for key, value in operation.items() if key != "details"
        },
        "prediction_quality": {
            "tool_call_count": predicted_call_count,
            "invalid_argument_json_count": invalid_arguments,
            "invalid_argument_json_rate": (
                invalid_arguments / predicted_call_count if predicted_call_count else 0.0
            ),
        },
        "_details": {
            "tool_name": make_json_safe_details(name["details"]),
            "tool_operation": make_json_safe_details(operation["details"]),
        },
    }


def print_scores(label, result):
    print(f"\n{label}")
    for title, key in (("Tool Name", "tool_name"), ("Tool Operation", "tool_operation")):
        score = result[key]
        micro = score["micro"]
        macro = score["macro"]
        exact = score["trace_exact_match"]
        print(f"  {title}")
        print(
            "    Micro: "
            f"precision={micro['precision']:.4f}  "
            f"recall={micro['recall']:.4f}  f1={micro['f1']:.4f}  "
            f"(TP={micro['tp']}, FP={micro['fp']}, FN={micro['fn']})"
        )
        print(
            "    Macro: "
            f"precision={macro['precision']:.4f}  "
            f"recall={macro['recall']:.4f}  f1={macro['f1']:.4f}"
        )
        print(
            f"    Trace exact match: {exact['count']}/{exact['total']} "
            f"({exact['rate']:.4f})"
        )
    quality = result["prediction_quality"]
    print(
        "  Invalid argument JSON: "
        f"{quality['invalid_argument_json_count']}/{quality['tool_call_count']} "
        f"({quality['invalid_argument_json_rate']:.4f})"
    )


def main():
    args = parse_args()
    reference_calls = load_reference(args.reference)
    all_results = {}
    all_details = []

    for prediction_path in args.predictions:
        prediction_calls, row_count = load_predictions(prediction_path)
        unknown = sorted(set(prediction_calls) - set(reference_calls))
        missing = sorted(set(reference_calls) - set(prediction_calls))
        if unknown:
            raise ValueError(f"{prediction_path}: unknown source_index values: {unknown}")
        if missing:
            print(
                f"Warning: {prediction_path} has no rows for {len(missing)} reference traces; "
                "they are scored as empty predictions.",
                file=sys.stderr,
            )
        result = evaluate(reference_calls, prediction_calls)
        result["file"] = prediction_path
        result["prediction_rows"] = row_count
        details = result.pop("_details")
        all_results[prediction_path] = result
        print_scores(prediction_path, result)
        for source_index in sorted(reference_calls):
            all_details.append(
                {
                    "prediction_file": prediction_path,
                    "source_index": source_index,
                    "tool_name": details["tool_name"][source_index],
                    "tool_operation": details["tool_operation"][source_index],
                }
            )

    if args.json_output:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            json.dump(all_results, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(f"\nSaved summary to {output}")

    if args.details_output:
        output = Path(args.details_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for detail in all_details:
                handle.write(json.dumps(detail, ensure_ascii=False) + "\n")
        print(f"Saved per-trace details to {output}")


if __name__ == "__main__":
    main()
