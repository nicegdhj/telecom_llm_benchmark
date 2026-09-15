#!/usr/bin/env python3
import argparse
import json
import logging
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mini_demo.http_client import ChatClient, ChatResult
from mini_demo.task_logic import (
    SUPPORTED_TASKS,
    EvalSample,
    build_judge_prompt,
    extract_first_option,
    load_task,
    normalize_latex,
    parse_judge_score,
    score_exam_choice,
    summarize_choice_results,
    summarize_exam_results,
    summarize_weighted_results,
)


ProgressCallback = Callable[[int, int, int, int], None]


@dataclass(frozen=True)
class ModelSettings:
    api_key: str
    base_url: str
    model: str


def resolve_infer_models(
    cli_models: Optional[Sequence[str]],
    environ: Mapping[str, str],
) -> List[str]:
    models = list(cli_models or [])
    if not models:
        env_model = environ.get("INFER_MODEL", "").strip()
        if env_model:
            models = [env_model]
    if not models:
        raise ValueError("provide --models or set INFER_MODEL")
    if any(not model.strip() for model in models):
        raise ValueError("model names must not be empty")
    if len(set(models)) != len(models):
        raise ValueError("duplicate model names are not allowed")
    return models


def resolve_infer_settings(
    model: str,
    environ: Mapping[str, str],
) -> ModelSettings:
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", model).strip("_").upper()
    override_api_key = environ.get(f"{prefix}_INFER_API_KEY", "").strip()
    override_base_url = environ.get(f"{prefix}_INFER_BASE_URL", "").strip()
    if override_api_key and override_base_url:
        return ModelSettings(override_api_key, override_base_url, model)

    api_key = environ.get("INFER_API_KEY", "").strip()
    base_url = environ.get("INFER_BASE_URL", "").strip()
    if not api_key or not base_url:
        raise ValueError(f"missing inference configuration for model: {model}")
    return ModelSettings(api_key, base_url, model)


def model_directories(models: Sequence[str]) -> Dict[str, str]:
    directories = {
        model: re.sub(r"[^A-Za-z0-9._-]", "_", model) for model in models
    }
    if any(not directory for directory in directories.values()):
        raise ValueError("model name cannot produce an empty directory")
    if any(directory in (".", "..") for directory in directories.values()):
        raise ValueError("model directory cannot be '.' or '..'")
    if len(set(directories.values())) != len(directories):
        raise ValueError("model directory names collide after sanitization")
    return directories


def evaluation_order(
    models: Sequence[str],
    tasks: Sequence[str],
) -> List[Tuple[str, str]]:
    return [(model, task) for model in models for task in tasks]


def resolve_judge_settings(
    tasks: Sequence[str],
    environ: Mapping[str, str],
) -> Optional[ModelSettings]:
    needs_judge = bool(
        {"tele_exam_gen_0_shot_str", "exam_gen_0_shot"}.intersection(tasks)
    )
    if not needs_judge:
        return None
    values = {
        "api_key": environ.get("JUDGE_API_KEY", "").strip(),
        "base_url": environ.get("JUDGE_BASE_URL", "").strip(),
        "model": environ.get("JUDGE_MODEL", "").strip(),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        names = ", ".join(f"JUDGE_{name.upper()}" for name in missing)
        raise ValueError(f"missing fixed Judge configuration: {names}")
    return ModelSettings(**values)


def summarize_performance(details: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    successful = [detail for detail in details if detail.get("status") == "success"]
    summary = {"successful_samples": len(successful)}
    for metric in ("ttft_seconds", "tokens_per_second", "chars_per_second"):
        values = sorted(
            float(detail["performance"][metric])
            for detail in successful
            if detail.get("performance")
            and detail["performance"].get(metric) is not None
        )
        summary[metric] = {
            "mean": _round_metric(sum(values) / len(values)) if values else None,
            "p50": _round_metric(_percentile(values, 0.50)) if values else None,
            "p95": _round_metric(_percentile(values, 0.95)) if values else None,
        }
    return summary


def _percentile(values: Sequence[float], fraction: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _round_metric(value: float) -> float:
    return round(value, 4)


def public_run_config(
    infer_settings: ModelSettings,
    judge_settings: ModelSettings,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        **options,
        "infer_url": infer_settings.base_url,
        "infer_model": infer_settings.model,
        "judge_url": judge_settings.base_url,
        "judge_model": judge_settings.model,
    }


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
            temp_path = Path(file.name)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def infer_samples(
    samples: Sequence[EvalSample],
    client: Any,
    concurrency: int,
    max_tokens: int,
    progress: Optional[ProgressCallback] = None,
) -> List[Dict[str, Any]]:
    rows: List[Optional[Dict[str, Any]]] = [None] * len(samples)
    success = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(client.complete_stream, sample.prompt, max_tokens): index
            for index, sample in enumerate(samples)
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            index = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = ChatResult(
                    status="failed",
                    content="",
                    attempts=0,
                    error=f"{type(exc).__name__}: {exc}"[:1000],
                )
            rows[index] = _inference_row(samples[index], result)
            if result.status == "success":
                success += 1
            else:
                failed += 1
            if progress:
                progress(completed, len(samples), success, failed)
    return [row for row in rows if row is not None]


def evaluate_rows(
    task_name: str,
    rows: Sequence[Dict[str, Any]],
    judge_client: Optional[Any],
    judge_concurrency: int,
    judge_max_tokens: int,
    progress: Optional[ProgressCallback] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    details = [dict(row) for row in rows]
    if task_name in ("opseval_gen_0_shot", "tele_exam_gen_0_shot"):
        is_opseval = task_name == "opseval_gen_0_shot"
        options = "ABCDEFG" if is_opseval else "ABCD"
        truth_mapping = {"正确": "A", "错误": "B"} if is_opseval else None
        for detail in details:
            if detail.get("status") != "success":
                detail.update(
                    processed_answer="",
                    correct=False,
                    got_score=None,
                    skipped=True,
                )
                continue
            processed = extract_first_option(
                detail.get("prediction", ""),
                options,
                truth_mapping,
            )
            correct = processed == str(detail.get("answer", "")).strip()
            detail.update(
                processed_answer=processed,
                correct=correct,
                got_score=1.0 if correct else 0.0,
                skipped=False,
            )
        metrics = summarize_choice_results(details)
        metrics["performance"] = summarize_performance(details)
        return metrics, details

    if task_name == "tele_exam_gen_0_shot_str":
        pending = []
        for index, detail in enumerate(details):
            if detail.get("status") != "success":
                detail.update(got_score=None, correct=False, skipped=True)
            else:
                pending.append(index)
        _judge_pending(
            details,
            pending,
            judge_client,
            judge_concurrency,
            judge_max_tokens,
            progress,
        )
        metrics = summarize_weighted_results(details)
        metrics["performance"] = summarize_performance(details)
        return metrics, details

    if task_name == "exam_gen_0_shot":
        pending = []
        for index, detail in enumerate(details):
            detail["skipped"] = False
            detail["correct"] = False
            if detail.get("status") != "success":
                detail.update(got_score=None, skipped=True)
                continue
            question_type = detail.get("question_type")
            prediction = str(detail.get("prediction", ""))
            answer = str(detail.get("answer", ""))
            max_score = float(detail.get("max_score", 1.0))
            if question_type == "multiple_choice":
                ratio = score_exam_choice(prediction, answer)
                detail["processed_answer"] = _exam_processed_answer(
                    prediction,
                    answer,
                )
                detail["correct"] = ratio == 1.0
                detail["got_score"] = max_score * ratio
            elif question_type == "fill_blank" and _fill_blank_matches(
                prediction,
                answer,
            ):
                detail["correct"] = True
                detail["got_score"] = max_score
            elif question_type in ("fill_blank", "subjective"):
                pending.append(index)
            else:
                detail.update(got_score=None, skipped=True)
        _judge_pending(
            details,
            pending,
            judge_client,
            judge_concurrency,
            judge_max_tokens,
            progress,
        )
        metrics = summarize_exam_results(details)
        metrics["performance"] = summarize_performance(details)
        return metrics, details

    raise ValueError(f"unsupported task: {task_name}")


def _inference_row(sample: EvalSample, result: ChatResult) -> Dict[str, Any]:
    return {
        **asdict(sample),
        "status": result.status,
        "attempts": result.attempts,
        "prediction": result.content,
        "raw_response": result.response,
        "reasoning_content": result.reasoning_content,
        "finish_reason": result.finish_reason,
        "performance": result.performance,
        "error": result.error,
    }


def _judge_pending(
    details: List[Dict[str, Any]],
    indices: Sequence[int],
    judge_client: Optional[Any],
    concurrency: int,
    max_tokens: int,
    progress: Optional[ProgressCallback],
) -> None:
    if not indices:
        return
    if judge_client is None:
        raise ValueError("judge model is required for this task")
    success = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {}
        for index in indices:
            detail = details[index]
            prompt = build_judge_prompt(
                prediction=str(detail.get("prediction", "")),
                reference=str(detail.get("answer", "")),
                max_score=float(detail.get("max_score", 1.0)),
            )
            detail["judge_prompt"] = prompt
            futures[executor.submit(judge_client.complete, prompt, max_tokens)] = index
        for completed, future in enumerate(as_completed(futures), start=1):
            index = futures[future]
            detail = details[index]
            try:
                result = future.result()
            except Exception as exc:
                result = ChatResult(
                    status="failed",
                    content="",
                    attempts=0,
                    error=f"{type(exc).__name__}: {exc}"[:1000],
                )
            detail["judge_status"] = result.status
            detail["judge_attempts"] = result.attempts
            detail["judge_output"] = result.content
            detail["judge_raw_response"] = result.response
            detail["judge_error"] = result.error
            score = None
            if result.status == "success":
                score = parse_judge_score(
                    result.content,
                    float(detail.get("max_score", 1.0)),
                )
            if score is None:
                detail.update(got_score=None, correct=False, skipped=True)
                failed += 1
            else:
                detail["got_score"] = score
                detail["correct"] = score >= float(detail.get("max_score", 1.0))
                detail["skipped"] = False
                success += 1
            if progress:
                progress(completed, len(indices), success, failed)


def _fill_blank_matches(prediction: str, answer: str) -> bool:
    prediction_clean = prediction.strip()
    answer_clean = answer.strip()
    return (
        prediction_clean == answer_clean
        or prediction_clean.replace(" ", "") == answer_clean.replace(" ", "")
        or normalize_latex(prediction_clean) == normalize_latex(answer_clean)
    )


def _exam_processed_answer(prediction: str, answer: str) -> str:
    from mini_demo.task_logic import extract_exam_choices

    return extract_exam_choices(prediction, len(answer.strip()))


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standalone concurrent evaluator for four benchmark tasks."
    )
    parser.add_argument("--models", nargs="+")
    parser.add_argument(
        "--tasks",
        nargs="+",
        choices=SUPPORTED_TASKS,
        default=list(SUPPORTED_TASKS),
    )
    parser.add_argument("--concurrency", type=_positive_int, default=6)
    parser.add_argument("--judge-concurrency", type=_positive_int)
    parser.add_argument("--max-tokens", type=_positive_int, default=2048)
    parser.add_argument("--judge-max-tokens", type=_positive_int, default=8192)
    parser.add_argument("--timeout", type=_positive_int, default=120)
    parser.add_argument("--limit", type=_positive_int)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "outputs",
    )
    return parser.parse_args(argv)


def _configure_logger(run_dir: Path) -> logging.Logger:
    logger = logging.getLogger("mini_eval")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger


def run(argv: Optional[Sequence[str]] = None) -> Path:
    args = _parse_args(argv)
    models = resolve_infer_models(args.models, os.environ)
    directories = model_directories(models)
    infer_settings = {
        model: resolve_infer_settings(model, os.environ) for model in models
    }
    judge_settings = resolve_judge_settings(args.tasks, os.environ)
    judge_concurrency = args.judge_concurrency or args.concurrency
    output_root = args.output_dir.expanduser().resolve()
    task_id = datetime.now().strftime("mini_eval_%Y%m%d_%H%M%S_%f")
    run_dir = output_root / task_id
    run_dir.mkdir(parents=True, exist_ok=False)
    logger = _configure_logger(run_dir)

    safe_config = {
        "task_id": task_id,
        "tasks": args.tasks,
        "models": models,
        "model_directories": directories,
        "infer_urls": {
            model: settings.base_url for model, settings in infer_settings.items()
        },
        "judge_url": judge_settings.base_url if judge_settings else None,
        "judge_model": judge_settings.model if judge_settings else None,
        "concurrency": args.concurrency,
        "judge_concurrency": judge_concurrency,
        "max_tokens": args.max_tokens,
        "judge_max_tokens": args.judge_max_tokens,
        "timeout": args.timeout,
        "limit": args.limit,
        "started_at": datetime.now().astimezone().isoformat(),
    }
    atomic_write_json(run_dir / "run_config.json", safe_config)
    judge_client = None
    if judge_settings:
        judge_client = ChatClient(
            api_key=judge_settings.api_key,
            base_url=judge_settings.base_url,
            model=judge_settings.model,
            timeout=args.timeout,
        )
    repo_root = Path(__file__).resolve().parents[1]
    summary = {"task_id": task_id, "models": {}}

    for model_index, model in enumerate(models, start=1):
        logger.info("model=%s started %d/%d", model, model_index, len(models))
        model_dir = run_dir / directories[model]
        model_dir.mkdir()
        settings = infer_settings[model]
        infer_client = ChatClient(
            api_key=settings.api_key,
            base_url=settings.base_url,
            model=model,
            timeout=args.timeout,
        )
        model_summary = {"model": model, "tasks": {}}
        for task_name in args.tasks:
            started_at = datetime.now().astimezone().isoformat()
            samples = load_task(task_name, repo_root, args.limit)
            logger.info("model=%s task=%s loaded=%d", model, task_name, len(samples))

            def inference_progress(completed, total, success, failed):
                logger.info(
                    "model=%s task=%s %d/%d success=%d failed=%d",
                    model,
                    task_name,
                    completed,
                    total,
                    success,
                    failed,
                )

            rows = infer_samples(
                samples,
                infer_client,
                args.concurrency,
                args.max_tokens,
                inference_progress,
            )

            def judge_progress(completed, total, success, failed):
                logger.info(
                    "model=%s task=%s[judge] %d/%d success=%d failed=%d",
                    model,
                    task_name,
                    completed,
                    total,
                    success,
                    failed,
                )

            metrics, details = evaluate_rows(
                task_name,
                rows,
                judge_client,
                judge_concurrency,
                args.judge_max_tokens,
                judge_progress,
            )
            task_payload = {
                "model": model,
                "task": task_name,
                "started_at": started_at,
                "finished_at": datetime.now().astimezone().isoformat(),
                "metrics": metrics,
                "samples": details,
            }
            atomic_write_json(model_dir / f"{task_name}.json", task_payload)
            model_summary["tasks"][task_name] = metrics
            logger.info(
                "model=%s task=%s completed metrics=%s",
                model,
                task_name,
                json.dumps(metrics, ensure_ascii=False),
            )
        atomic_write_json(model_dir / "summary.json", model_summary)
        summary["models"][model] = model_summary["tasks"]
        logger.info("model=%s completed %d/%d", model, model_index, len(models))

    summary["finished_at"] = datetime.now().astimezone().isoformat()
    atomic_write_json(run_dir / "summary.json", summary)
    logger.info("all tasks completed output=%s", run_dir)
    return run_dir


def main() -> int:
    try:
        run()
        return 0
    except Exception as exc:
        print(f"mini_eval failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
