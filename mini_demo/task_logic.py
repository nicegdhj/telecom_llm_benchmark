import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


SUPPORTED_TASKS = (
    "opseval_gen_0_shot",
    "tele_exam_gen_0_shot",
    "tele_exam_gen_0_shot_str",
    "exam_gen_0_shot",
)

OPSEVAL_SUBSETS = (
    "5G_Communication",
    "Mobile_Communication_Network",
    "Wired_NetWork",
)

TELE_SUBJECTIVE_SUBSETS = (
    "传输与接入（无线）",
    "互联网技术",
    "设备环境",
)

EXAM_PAPERS = (
    "exam_858_2022",
    "exam_858_2023",
    "exam_858_2024",
    "exam_801-2022",
    "exam_801-2023",
    "exam_801-2024",
    "exam_804_2022",
    "exam_804_2023",
    "exam_804_2024",
)

EXAM_PROMPT_SUFFIXES = {
    "multiple_choice": (
        "\n\n【作答要求】请直接给出本题的正确选项字母。若有多个空，请按顺序给出对应字母（如 A 或 CD）。"
        "不要输出任何解释、标点或其他内容。"
    ),
    "fill_blank": (
        "\n\n【作答要求】请直接给出填空处的最终答案，"
        "不要包含解题过程或其他解释内容。"
    ),
    "subjective": "\n\n【作答要求】请给出详细的解答过程和最终结论。",
}

logger = logging.getLogger("mini_eval.task_logic")

JUDGE_PROMPT_TEMPLATE = r"""You are an objective and intelligent evaluator. Your task is to score the student's answer against the correct reference answer.
The maximum score you can give is {max_score}.

Evaluation Criteria:
1. Math & Engineering Equivalence: If the answer involves formulas or equations, focus on mathematical equivalence. Ignore different algebraic arrangements (e.g., `t^2/2` vs `1/2 t^2`), extraneous assignments (e.g., `y(t) = `), and purely typographical or LaTeX syntax differences (e.g., `\frac` vs `\dfrac`, missing brackets, spaces).
2. Semantic Text Equivalence: If the answer is natural language, evaluate based on core meaning and semantic similarity rather than exact string matching. Do not penalize for synonyms, paraphrasing, or varying levels of detail as long as the core concept is correct (e.g., "山" and "山川" should be considered semantically equivalent if they refer to the same core entity).
3. Minor Errors: Ignore differences in punctuation, capitalization, and minor typos that do not alter the fundamental meaning or correctness.
4. Partial Credit: If the student's answer is partially correct or captures only part of a complex reference answer, award a proportional score based on {max_score}. If the answer is fundamentally wrong or contradictory, score 0.

Correct Answer:
{reference}

Student's Answer:
{prediction}

Please output the score only as a number at the end of your response."""


@dataclass
class EvalSample:
    sample_id: str
    task: str
    subdivision: str
    question_type: str
    question: str
    prompt: str
    answer: str
    max_score: float = 1.0


def load_task(
    task_name: str,
    root: Path,
    limit: Optional[int] = None,
) -> List[EvalSample]:
    loaders = {
        "opseval_gen_0_shot": _load_opseval,
        "tele_exam_gen_0_shot": _load_tele_choice,
        "tele_exam_gen_0_shot_str": _load_tele_subjective,
        "exam_gen_0_shot": _load_exam,
    }
    if task_name not in loaders:
        raise ValueError(f"unsupported task: {task_name}")
    samples = loaders[task_name](Path(root))
    if not samples:
        raise ValueError(f"no samples loaded for task: {task_name}")
    if limit is not None:
        return samples[:limit]
    return samples


def extract_first_option(
    text: str,
    options: str,
    truth_mapping: Optional[Dict[str, str]] = None,
) -> str:
    escaped_options = re.escape(options)
    patterns = (
        rf"(?:最终|正确|标准)?答案\s*(?:选|应该选|为|是)?\s*[:：]?\s*[*_`]*[（(]?\s*([{escaped_options}])",
        rf"(?i:answer)\s*(?:is)?\s*[:：]?\s*[*_`]*[（(]?\s*([{escaped_options}])",
        rf"\\boxed\s*\{{\s*(?:\\text\s*\{{)?\s*([{escaped_options}])",
    )
    matches = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text))
    if matches:
        return matches[-1].upper()

    truth_match = re.match(r"^\s*(正\s*确|错\s*误)(?:\s*[。.!！]|$)", text)
    if truth_match and truth_mapping:
        truth_word = re.sub(r"\s+", "", truth_match.group(1))
        mapped_option = truth_mapping.get(truth_word, "")
        if mapped_option in options:
            return mapped_option

    match = re.search(
        rf"(?m)^\s*[*_`]*[（(\[]?\s*([{escaped_options}])\s*[）)\]]?\s*[*_`]*(?:[.、:：]|\s|$)",
        text,
    )
    if match:
        return match.group(1).upper()

    loose_options = "".join(option for option in options if option not in "FG")
    if not loose_options:
        return ""
    match = re.search(rf"[{re.escape(loose_options)}]", text)
    return match.group(0).upper() if match else ""


def extract_exam_choices(text: str, expected_len: int = 1) -> str:
    upper = text.upper()
    chinese_match = re.search(
        r"(?:答案|选项|选择)[是为选：:]*\s*([A-Z][A-Z、,，\s]*)",
        upper,
    )
    if chinese_match:
        letters = re.findall(r"[A-Z]", chinese_match.group(1))
        if letters:
            return "".join(letters[:expected_len])
    english_match = re.search(
        r"ANSWER\s*[:：＝= ]\s*([A-Z][A-Z,\s]*)",
        upper,
    )
    if english_match:
        letters = re.findall(r"[A-Z]", english_match.group(1))
        if letters:
            return "".join(letters[:expected_len])
    groups = re.findall(r"[A-Z]{2,10}", upper)
    candidates = [group for group in groups if len(group) == expected_len]
    if candidates:
        return candidates[-1]
    letters = re.findall(r"[A-Z]", upper)
    return "".join(letters[:expected_len])


def score_exam_choice(prediction: str, reference: str) -> float:
    expected = reference.strip().upper()
    if not expected:
        return 0.0
    extracted = extract_exam_choices(prediction, len(expected))
    if not extracted:
        return 0.0
    matched = sum(
        1 for predicted, expected_letter in zip(extracted, expected)
        if predicted == expected_letter
    )
    return float(matched) / len(expected)


def normalize_latex(text: str) -> str:
    value = text.strip()
    value = re.sub(r"^\$\$(.*)\$\$$", r"\1", value, flags=re.DOTALL)
    value = re.sub(r"^\$(.*)\$$", r"\1", value, flags=re.DOTALL)
    value = re.sub(r"\\[dt]frac\b", r"\\frac", value)
    value = re.sub(r"\\(?:left|right)", "", value)
    value = re.sub(
        r"\\(?:displaystyle|textstyle|scriptstyle|scriptscriptstyle)\b",
        "",
        value,
    )
    value = re.sub(r"\\(?:,|;|:|!|quad|qquad| )", "", value)
    return " ".join(value.split()).strip()


def build_judge_prompt(prediction: str, reference: str, max_score: float) -> str:
    return JUDGE_PROMPT_TEMPLATE.format(
        max_score=max_score,
        reference=reference,
        prediction=prediction,
    )


def parse_judge_score(output: str, max_score: float) -> Optional[float]:
    if not output or not output.strip():
        return None
    clean_output = re.sub(
        r"<think>.*?</think>",
        "",
        output,
        flags=re.DOTALL | re.IGNORECASE,
    )
    score_match = re.search(
        r"[\"']score[\"']\s*:\s*[\"']?([\d.]+)",
        clean_output,
        flags=re.IGNORECASE,
    )
    candidates = []
    if score_match:
        candidates = [score_match.group(1)]
    else:
        candidates = re.findall(r"^\s*([\d.]+)\s*$", clean_output, re.MULTILINE)
        if not candidates:
            candidates = re.findall(r"([\d.]+)", clean_output)
    if not candidates:
        return 0.0
    try:
        score = float(candidates[-1])
    except ValueError:
        return 0.0
    return min(max(score, 0.0), max_score)


def summarize_choice_results(details: List[Dict[str, Any]]) -> Dict[str, Any]:
    successful = [detail for detail in details if detail.get("status") == "success"]
    correct = sum(
        1
        for detail in successful
        if str(detail.get("processed_answer", "")).strip()
        == str(detail.get("answer", "")).strip()
    )
    evaluated = len(successful)
    accuracy = round(correct / evaluated * 100, 2) if evaluated else 0.0
    return {
        "accuracy": accuracy,
        "correct": correct,
        "evaluated": evaluated,
        "failed": len(details) - evaluated,
    }


def summarize_weighted_results(details: List[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [
        detail
        for detail in details
        if not detail.get("skipped", False) and detail.get("got_score") is not None
    ]
    got_score = sum(float(detail["got_score"]) for detail in valid)
    max_score = sum(float(detail.get("max_score", 1.0)) for detail in valid)
    percentage = round(got_score / max_score * 100, 2) if max_score else 0.0
    return {
        "score_percentage": percentage,
        "got_score": round(got_score, 4),
        "max_score": round(max_score, 4),
        "evaluated": len(valid),
        "skipped": len(details) - len(valid),
    }


def summarize_exam_results(details: List[Dict[str, Any]]) -> Dict[str, Any]:
    paper_got = defaultdict(float)
    paper_max = defaultdict(float)
    for detail in details:
        if detail.get("skipped", False) or detail.get("got_score") is None:
            continue
        subdivision = str(detail.get("subdivision", "unknown"))
        paper_got[subdivision] += float(detail["got_score"])
        paper_max[subdivision] += float(detail.get("max_score", 1.0))
    papers = {
        name: round(paper_got[name] / paper_max[name] * 100, 2)
        for name in sorted(paper_max)
        if paper_max[name]
    }
    total_got = sum(paper_got.values())
    total_max = sum(paper_max.values())
    overall = round(total_got / total_max * 100, 2) if total_max else 0.0
    return {
        "overall_score_percentage": overall,
        "got_score": round(total_got, 4),
        "max_score": round(total_max, 4),
        "papers": papers,
        "evaluated": sum(1 for detail in details if detail.get("got_score") is not None and not detail.get("skipped", False)),
        "skipped": sum(1 for detail in details if detail.get("got_score") is None or detail.get("skipped", False)),
    }


def _load_opseval(root: Path) -> List[EvalSample]:
    data_dir = root / "data" / "OpsEval"
    if not data_dir.is_dir():
        raise FileNotFoundError(f"OpsEval data directory not found: {data_dir}")
    samples = []
    for subset in OPSEVAL_SUBSETS:
        path = data_dir / f"{subset}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"OpsEval data file not found: {path}")
        with path.open("r", encoding="utf-8") as file:
            for index, line in enumerate(file):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning("skipping invalid JSON line in %s: %s", path, exc)
                    continue
                if not isinstance(item, dict):
                    logger.warning("skipping non-object JSON line in %s", path)
                    continue
                question = str(item.get("question", "")).strip()
                answer = _normalize_option_answer(item.get("answer"))
                if not question or not answer:
                    continue
                prompt = (
                    "Please select the correct answer from the options provided.\n"
                    f"Question:\n{question}\n答案："
                )
                samples.append(
                    EvalSample(
                        sample_id=f"{subset}_{item.get('id', index)}",
                        task="opseval_gen_0_shot",
                        subdivision=subset,
                        question_type="multiple_choice",
                        question=question,
                        prompt=prompt,
                        answer=answer,
                    )
                )
    return samples


def _load_tele_choice(root: Path) -> List[EvalSample]:
    data_dir = root / "data" / "telecom-intermediate-exam" / "2023" / "综合"
    if not data_dir.is_dir():
        raise FileNotFoundError(f"TeleExam data directory not found: {data_dir}")
    samples = []
    for path in sorted(data_dir.glob("*.json")):
        rows = _safe_read_json_list(path)
        for index, item in enumerate(rows):
            question = str(item.get("question", "")).strip()
            preferred = str(item.get("correct answer", "")).strip()
            answer = preferred or str(item.get("answer", "")).strip()
            if not question or not answer:
                continue
            samples.append(
                EvalSample(
                    sample_id=f"{path.stem}_{item.get('id', index)}",
                    task="tele_exam_gen_0_shot",
                    subdivision=path.stem,
                    question_type="multiple_choice",
                    question=question,
                    prompt=(
                        f"{question}\n请选择正确答案（只输出选项字母）：\n答案："
                    ),
                    answer=answer,
                )
            )
    return samples


def _load_tele_subjective(root: Path) -> List[EvalSample]:
    data_dir = root / "data" / "telecom-intermediate-exam"
    if not data_dir.is_dir():
        raise FileNotFoundError(f"TeleExam data directory not found: {data_dir}")
    samples = []
    for year_dir in sorted(path for path in data_dir.iterdir() if path.is_dir()):
        for subset in TELE_SUBJECTIVE_SUBSETS:
            subset_dir = year_dir / subset
            if not subset_dir.is_dir():
                continue
            for path in sorted(subset_dir.glob("*.json")):
                rows = _safe_read_json_list(path)
                for index, item in enumerate(rows):
                    question = str(item.get("question", "")).strip()
                    answer = str(item.get("answer", "")).strip()
                    if not answer:
                        answer = str(item.get("correct answer", "")).strip()
                    if answer == "×":
                        answer = "错误"
                    elif answer == "√":
                        answer = "正确"
                    if not question or not answer:
                        continue
                    samples.append(
                        EvalSample(
                            sample_id=(
                                f"{year_dir.name}_{subset}_{path.stem}_"
                                f"{item.get('id', index)}"
                            ),
                            task="tele_exam_gen_0_shot_str",
                            subdivision=path.stem,
                            question_type="subjective",
                            question=question,
                            prompt=(
                                f"{question}\n请根据题型简洁作答：填空题只写答案，"
                                "选择题只写字母，问答题简要回答。：\n答："
                            ),
                            answer=answer,
                            max_score=_parse_score(item.get("score")),
                        )
                    )
    return samples


def _load_exam(root: Path) -> List[EvalSample]:
    data_dir = root / "data" / "exam"
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Exam data directory not found: {data_dir}")
    samples = []
    paper_paths = [data_dir / f"{paper}.json" for paper in EXAM_PAPERS]
    missing_paths = [path for path in paper_paths if not path.is_file()]
    if missing_paths:
        missing = ", ".join(path.name for path in missing_paths)
        raise FileNotFoundError(f"Exam data files not found: {missing}")
    for path in paper_paths:
        data = _safe_read_json_dict(path)
        if data is None:
            continue
        for question_type in ("multiple_choice", "fill_blank", "subjective"):
            rows = data.get(question_type, [])
            if not isinstance(rows, list):
                continue
            for index, item in enumerate(rows):
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question", "")).strip()
                if not question or item.get("has_image") or item.get("need_plot"):
                    continue
                answer = _normalize_exam_answer(item.get("answer"))
                samples.append(
                    EvalSample(
                        sample_id=f"{path.stem}_{question_type}_{item.get('id', index)}",
                        task="exam_gen_0_shot",
                        subdivision=path.stem,
                        question_type=question_type,
                        question=question,
                        prompt=question + EXAM_PROMPT_SUFFIXES[question_type],
                        answer=answer,
                        max_score=_parse_score(item.get("score")),
                    )
                )
    return samples


def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"expected JSON list: {path}")
    return [item for item in data if isinstance(item, dict)]


def _read_json_dict(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _safe_read_json_list(path: Path) -> List[Dict[str, Any]]:
    try:
        return _read_json_list(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("skipping invalid JSON file %s: %s", path, exc)
        return []


def _safe_read_json_dict(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return _read_json_dict(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("skipping invalid JSON file %s: %s", path, exc)
        return None


def _normalize_option_answer(raw: Any) -> str:
    value = str(raw or "").strip().rstrip(", ")
    match = re.match(r"^([A-Za-z])", value)
    return match.group(1).upper() if match else value.upper()


def _normalize_exam_answer(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, dict):
        try:
            pairs = sorted(raw.items(), key=lambda item: int(item[0]))
        except (TypeError, ValueError):
            pairs = list(raw.items())
        return "".join(str(value).strip() for _, value in pairs)
    return str(raw).strip()


def _parse_score(raw: Any) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"([\d.]+)", str(raw)) if raw is not None else None
    return float(match.group(1)) if match else 1.0
