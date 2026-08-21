import json
import re
import string
from pathlib import Path

from datasets import Dataset

from ais_bench.benchmark.datasets.base import BaseDataset
from ais_bench.benchmark.datasets.utils.datasets import get_data_path
from ais_bench.benchmark.registry import LOAD_DATASET, TEXT_POSTPROCESSORS


SUPPORTED_MODES = {"mcq", "json_label", "plain"}


@TEXT_POSTPROCESSORS.register_module("telelogs_postprocess")
def telelogs_postprocess(text):
    candidates = []
    patterns = [
        r"\\boxed\s*\{\s*C?([0-9]+)\s*\}",
        r"(?:答案|answer)\s*[:：]?\s*C?([0-9]+)\b",
        r"(?<![A-Za-z0-9])C([0-9]+)(?![A-Za-z0-9])",
    ]
    for pattern in patterns:
        candidates.extend(re.findall(pattern, str(text), flags=re.IGNORECASE))
    if any(candidate not in {str(index) for index in range(1, 9)} for candidate in candidates):
        return ""
    unique = set(candidates)
    if len(unique) != 1:
        return ""
    return f"C{unique.pop()}"


def _error(path, line_number, message):
    raise ValueError(f"{path}: line {line_number}: {message}")


def _required(record, field, path, line_number):
    if field not in record:
        _error(path, line_number, f"missing required field '{field}'")
    return record[field]


def _normalize_choice_prefix(choice, position):
    return re.sub(
        rf"^\s*{position}[.)、]\s+",
        "",
        str(choice).strip(),
        count=1,
    )


def _adapt_mcq(record, path, line_number):
    question = _required(record, "question", path, line_number)
    choices = _required(record, "choices", path, line_number)
    answer = _required(record, "answer", path, line_number)
    if not isinstance(choices, list) or len(choices) < 2:
        _error(path, line_number, "mcq record must contain at least 2 choices")
    if len(choices) > len(string.ascii_uppercase):
        _error(path, line_number, "mcq record has more than 26 choices")
    if isinstance(answer, bool) or not isinstance(answer, int):
        _error(path, line_number, "mcq answer must be an integer index")
    if not 0 <= answer < len(choices):
        _error(path, line_number, "mcq answer index is out of range")

    option_lines = []
    for index, choice in enumerate(choices):
        letter = string.ascii_uppercase[index]
        text = _normalize_choice_prefix(choice, index + 1)
        option_lines.append(f"{letter}. {text}")
    return {
        "input": f"{str(question).strip()}\n\n" + "\n".join(option_lines),
        "output": string.ascii_uppercase[answer],
    }


def _adapt_record(record, mode, path, line_number):
    question = _required(record, "question", path, line_number)
    if mode == "mcq":
        return _adapt_mcq(record, path, line_number)
    answer = _required(record, "answer", path, line_number)
    if mode == "json_label":
        output = json.dumps(
            {"WORKING GROUP": str(answer).strip()},
            ensure_ascii=False,
        )
    else:
        output = str(answer).strip()
    return {"input": str(question).strip(), "output": output}


@LOAD_DATASET.register_module()
class OTDataset(BaseDataset):

    @staticmethod
    def load(path, mode, **kwargs):
        if mode not in SUPPORTED_MODES:
            raise ValueError(f"unsupported OT dataset mode: {mode}")
        resolved_path = Path(get_data_path(path, local_mode=True))
        records = []
        with resolved_path.open("r", encoding="utf-8-sig") as source:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    _error(resolved_path, line_number, f"invalid JSON: {exc.msg}")
                if not isinstance(record, dict):
                    _error(resolved_path, line_number, "record must be a JSON object")
                records.append(
                    _adapt_record(record, mode, resolved_path, line_number)
                )
        return Dataset.from_list(records)
