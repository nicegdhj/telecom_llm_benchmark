import argparse
import copy
import fnmatch
import importlib.util
import threading
import math
import os
import os.path as osp
import statistics
import sys
import time
from collections import Counter
from functools import lru_cache
from inspect import signature
from pathlib import Path
from typing import List
import mmap
import orjson
from collections import defaultdict

import mmengine
from mmengine.config import Config, ConfigDict
from mmengine.utils import mkdir_or_exist

from ais_bench.benchmark.registry import (
    ICL_EVALUATORS,
    MODELS,
    TASKS,
    TEXT_POSTPROCESSORS,
)
from ais_bench.benchmark.tasks.base import BaseTask, extract_role_pred
from ais_bench.benchmark.utils.core.abbr import (
    dataset_abbr_from_cfg,
    get_infer_output_path,
    task_abbr_from_cfg,
)
from ais_bench.benchmark.utils.core.types import check_type
from ais_bench.benchmark.utils.config import build_dataset_from_cfg
from ais_bench.benchmark.tasks.base import TaskStateManager
from ais_bench.benchmark.utils.logging import AISLogger
from ais_bench.benchmark.utils.logging.error_codes import TEVAL_CODES
from ais_bench.benchmark.utils.logging.exceptions import ParameterValueError
from ais_bench.benchmark.openicl.icl_evaluator.icl_base_evaluator import BaseEvaluator

# Type mapping for default values using hash table (dict) driven approach
TYPE_DEFAULT_MAP = {
    list: [],
    dict: {},
    str: "",
    int: 0,
    float: 0,
}


@lru_cache(maxsize=32)
def _evaluator_requires_llm_judge(evaluator_type: str) -> bool:
    """检查评测器是否需要 LLM 打分模型。

    两级检测：
      1. 类型名直接包含 LLMJudgeEvaluator（如直接使用）
      2. 扫描评测器源码是否引用了 LLMJudgeEvaluator（如 ExamDynamicEvaluator 等包装器）

    任何未来新增的评测器只要在其源码中引用了 LLMJudgeEvaluator，都会被自动检测到。
    """
    # 第一级：类型名直接匹配
    if "LLMJudgeEvaluator" in evaluator_type:
        return True

    # 第二级：解析模块路径，扫描源码
    try:
        module_name = evaluator_type.rsplit(".", 1)[0]
        spec = importlib.util.find_spec(module_name)
        if spec and spec.origin and spec.origin.endswith(".py"):
            source = Path(spec.origin).read_text(encoding="utf-8")
            if "LLMJudgeEvaluator" in source:
                return True
    except Exception:
        pass

    return False


@TASKS.register_module()
class OpenICLEvalTask(BaseTask):
    """OpenICL Evaluation Task.

    This task is used to evaluate the metric between predictions and
    references.
    """

    name_prefix = "OpenICLEval"
    log_subdir = "logs/eval"
    output_subdir = "results"

    def __init__(self, cfg: ConfigDict):
        super().__init__(cfg)
        self.num_gpus = max(
            c.get("eval_cfg", {}).get("num_gpus", 0)
            for c in sum([self.dataset_cfgs], [])
        )
        self.dump_details = (
            cfg.get("eval", {})
            .get("runner", {})
            .get("task", {})
            .get("dump_details", False)
        )
        self.cal_extract_rate = (
            cfg.get("eval", {})
            .get("runner", {})
            .get("task", {})
            .get("cal_extract_rate", False)
        )
        self.logger.debug(
            f"Dump details: {self.dump_details}, calculate extract rate: {self.cal_extract_rate}"
        )

    def get_command(self, cfg_path, template):
        sys.path.append(os.getcwd())
        script_path = __file__
        python = sys.executable
        command = f"{python} {script_path} {cfg_path}"
        return template.format(task_cmd=command)

    def run(self):
        for dataset_cfg in self.dataset_cfgs:
            self.dataset_cfg = dataset_cfg
            # Load Dataset
            self.eval_cfg = self.dataset_cfg.get("eval_cfg")
            self.logger.debug(f"Eval config: {self.eval_cfg}")
            self.output_column = dataset_cfg["reader_cfg"]["output_column"]

            # overwrite postprocessor if the model has specified one
            ds_abbr = dataset_abbr_from_cfg(self.dataset_cfg)
            model_postprocessors = self.model_cfg.get("pred_postprocessor", {})
            self.logger.debug(f"Model postprocessors: {model_postprocessors}")
            for pattern in model_postprocessors.keys():
                if fnmatch.fnmatch(ds_abbr, pattern):
                    self.eval_cfg["pred_postprocessor"] = model_postprocessors[pattern]
                    break

            out_path = get_infer_output_path(
                self.model_cfg, self.dataset_cfg, osp.join(self.work_dir, "results")
            )
            self.logger.debug(f"Output path: {out_path}")
            if osp.exists(out_path):
                self.logger.warning(
                    f"Output file {out_path} already exists and will be overwritten."
                )
            self._score()

    def _score(self):
        num_return_sequences = getattr(self.model_cfg, "generation_kwargs", {}).get(
            "num_return_sequences", 1
        )
        k = self.dataset_cfg.get("k", num_return_sequences)
        n = self.dataset_cfg.get("n", num_return_sequences)

        check_type(k, int)
        check_type(n, int)
        if k <= 0 or n <= 0 or k > n:
            raise ParameterValueError(
                TEVAL_CODES.N_K_ILLEGAL,
                f"k and n must be greater than 0 and k <= n, but got k: {k}, n: {n}",
            )

        self.dataset_cfg.update({"k": k, "n": n})

        test_set = build_dataset_from_cfg(self.dataset_cfg).test
        # Postprocess dataset if necessary
        if "dataset_postprocessor" in self.eval_cfg:
            self.logger.debug(
                f"Dataset postprocessor: {self.eval_cfg['dataset_postprocessor']}"
            )
            proc = self.eval_cfg["dataset_postprocessor"]["type"]
            if isinstance(proc, str):
                proc = TEXT_POSTPROCESSORS.get(proc)

            def postprocess(sample):
                s = sample[self.output_column]
                sample[self.output_column] = proc(s)
                return sample

            test_set = test_set.map(postprocess)

        # Load predictions
        filename = get_infer_output_path(
            self.model_cfg,
            self.dataset_cfg,
            osp.join(self.work_dir, "predictions"),
            "jsonl",
        )

        self.logger.debug(f"Prediction filename: {filename}")
        # in case the prediction is partial
        root, ext = osp.splitext(filename)
        partial_filename = root + "_0" + ext

        # Get sc_size if use Self-Consistency
        sc_size = self.eval_cfg.get("sc_size")
        if not osp.exists(osp.realpath(filename)) and not osp.exists(
            osp.realpath(partial_filename)
        ):
            result = {"error": "No predictions found."}
        else:
            if osp.exists(osp.realpath(filename)):
                preds = []
                with open(filename, "rb") as f:
                    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                    for line in iter(mm.readline, b""):
                        preds.append(orjson.loads(line))
            else:
                filename = partial_filename
                preds = []
                i = 1
                while osp.exists(osp.realpath(filename)):
                    sub_preds = mmengine.load(filename)
                    preds.extend([sub_preds[str(i)] for i in range(len(sub_preds))])
                    filename = root + f"_{i}" + ext
                    i += 1
            # Fail case will not include in jsonl results, mock it values to avoid error
            total_ids = set(range(len(test_set) // num_return_sequences))
            prediction_ids = {key: 0 for key in total_ids}
            for pred in preds:
                current_id = pred.get("id")
                if (
                    current_id not in prediction_ids
                ):  # num-prompts change cause predictions num more than references, ignore it
                    continue
                prediction_ids[current_id] += 1

            failed_data_ids = {
                key: num_return_sequences - value
                for key, value in prediction_ids.items()
                if value < num_return_sequences
            }
            if failed_data_ids:
                fail_count = sum(failed_data_ids.values())
                self.logger.warning(
                    f"Total {fail_count} data are not in the predictions. These data may failed in inference stage."
                )
                for failed_data_id in failed_data_ids.keys():
                    mock_fail_data = {}
                    for key, value in preds[0].items():
                        # Use hash table lookup for type mapping
                        value_type = type(value)
                        mock_fail_data[key] = TYPE_DEFAULT_MAP.get(value_type)
                    mock_fail_data["id"] = failed_data_id
                    preds.extend([mock_fail_data] * failed_data_ids[failed_data_id])

            # 预测去重
            # 如果 predictions 数量超过 references，按 id 过滤只保留每个 id 的首条
            if len(preds) > len(test_set):
                expect_ids = {index: num_return_sequences for index in total_ids}
                fill_preds = []
                for pred in preds:
                    current_id = pred.get("id")

                    # 超出的重复条目被丢弃
                    if current_id not in expect_ids or expect_ids[current_id] == 0:
                        continue
                    expect_ids[current_id] -= 1
                    fill_preds.append(pred)
                self.logger.warning(
                    f"Found {len(preds)} predictions, but {len(test_set)} references. Drop extra predictions."
                )
                preds = fill_preds
            preds.sort(key=lambda x: x.get("id", 0))
            pred_dicts = copy.deepcopy(preds)
            preds = {k: [pred.get(k) for pred in preds] for k in preds[0]}

            pred_strs = preds.pop("prediction", None)
            pred_list_flag = pred_strs is not None and isinstance(pred_strs[0], list)

            if "pred_postprocessor" in self.model_cfg:
                self.logger.debug(
                    f"Model pred postprocessor: {self.model_cfg['pred_postprocessor']}"
                )
                self.logger.info(
                    "----------------Model pred postprocessor------------------------"
                )
                self.logger.info(
                    f"Model pred postprocessor: {self.model_cfg['pred_postprocessor']}"
                )
                kwargs = copy.deepcopy(self.model_cfg["pred_postprocessor"])
                proc = kwargs.pop("type")
                if isinstance(proc, str):
                    proc = TEXT_POSTPROCESSORS.get(proc)
                if pred_list_flag:
                    pred_strs = [
                        [proc(s, **kwargs) for s in preds] for preds in pred_strs
                    ]
                else:
                    pred_strs = [proc(s, **kwargs) for s in pred_strs]
                self.logger.info("=== DEBUG: After model-level postprocessor ===")
                for i in range(min(3, len(pred_strs))):
                    proc_pred = pred_strs[i]
                    ref = (
                        test_set[self.output_column][i]
                        if self.output_column and i < len(test_set[self.output_column])
                        else "N/A"
                    )
                    self.logger.info(
                        f"[Sample {i}] Processed Pred: {repr(proc_pred)} | Ref: {repr(ref)}"
                    )
            # Postprocess predictions if necessary
            if "pred_postprocessor" in self.eval_cfg:
                self.logger.debug(
                    f"Eval pred postprocessor: {self.eval_cfg['pred_postprocessor']}"
                )
                self.logger.info(
                    "----------------Eval pred postprocessor------------------------"
                )
                self.logger.info(
                    f"Eval pred postprocessor: {self.eval_cfg['pred_postprocessor']}"
                )
                kwargs = self.eval_cfg["pred_postprocessor"]
                proc = kwargs.pop("type")
                if isinstance(proc, str):
                    proc = TEXT_POSTPROCESSORS.get(proc)
                if pred_list_flag:
                    pred_strs = [
                        [proc(s, **kwargs) for s in preds] for preds in pred_strs
                    ]
                else:
                    pred_strs = [proc(s, **kwargs) for s in pred_strs]
                self.logger.info(
                    "=== DEBUG: After eval-level postprocessor (FINAL PREDICTIONS) ==="
                )
                for i in range(min(3, len(pred_strs))):
                    final_pred = pred_strs[i]
                    ref = (
                        test_set[self.output_column][i]
                        if self.output_column and i < len(test_set[self.output_column])
                        else "N/A"
                    )
                    match = final_pred == ref
                    self.logger.info(
                        f"[Sample {i}] Final Pred: {repr(final_pred)} | Ref: {repr(ref)} | Match: {match}"
                    )
            model_pred_strs = []
            if "model_postprocessor" in self.eval_cfg:
                self.logger.debug(
                    f"Model postprocessor: {self.eval_cfg['model_postprocessor']}"
                )
                references = (
                    test_set[self.output_column] if self.output_column else None
                )
                model_pred_dicts = copy.deepcopy(pred_dicts)
                for i, pred_dict in enumerate(model_pred_dicts):
                    pred_dict["reference"] = [references[i]]
                self.logger.info("Start postprocessing model predictions...")
                kwargs = self.eval_cfg["model_postprocessor"]
                proc = kwargs.pop("type")
                if isinstance(proc, str):
                    proc = TEXT_POSTPROCESSORS.get(proc)
                if pred_list_flag:
                    model_pred_strs = [
                        [
                            proc(model_pred_dict, **kwargs)
                            for model_pred_dict in model_pred_dicts
                        ]
                    ]
                else:
                    model_pred_strs = proc(model_pred_dicts, **kwargs)
                self.logger.info(
                    "=== DEBUG: After model_postprocessor (for reference only) ==="
                )
                refs = (
                    test_set[self.output_column]
                    if self.output_column
                    else ["N/A"] * len(model_pred_strs)
                )
                for i in range(min(2, len(model_pred_strs))):
                    mp_pred = model_pred_strs[i]
                    if isinstance(mp_pred, list) and len(mp_pred) > 0:
                        mp_pred = mp_pred[0]
                    ref = refs[i] if i < len(refs) else "N/A"
                    self.logger.info(
                        f"[Sample {i}] ModelPost Pred: {repr(mp_pred)} | Ref: {repr(ref)}"
                    )
            # Get majority voting predictions if use self-consistency
            if sc_size is not None:
                pred_strs = [Counter(s).most_common(1)[0][0] for s in pred_strs]

            # TODO Configure eval in a more elegant way
            if "returns_tool_calls" in self.model_cfg.keys():
                self.eval_cfg["evaluator"].update(
                    {"is_fc_model": self.model_cfg.get("returns_tool_calls")}
                )
            if _evaluator_requires_llm_judge(self.eval_cfg["evaluator"]["type"]):
                if not os.environ.get("SCORE_MODEL_NAME"):
                    raise ValueError(
                        f"{self.eval_cfg['evaluator']['type'].split('.')[-1]} "
                        "未配置打分模型：请设置 SCORE_MODEL_NAME 等环境变量。"
                    )
            icl_evaluator: BaseEvaluator = ICL_EVALUATORS.build(
                self.eval_cfg["evaluator"]
            )
            # need results dir to save other files
            out_path = get_infer_output_path(
                self.model_cfg, self.dataset_cfg, osp.join(self.work_dir, "results")
            )
            results_dir = osp.dirname(out_path)
            icl_evaluator._out_dir = results_dir
            if not osp.exists(results_dir):
                mmengine.mkdir_or_exist(results_dir)

            preds["predictions"] = pred_strs
            preds["references"] = (
                test_set[self.output_column] if self.output_column else None
            )
            preds["test_set"] = test_set
            if "origin_prompt" not in preds:
                try:
                    preds["origin_prompt"] = [None for _ in range(len(pred_strs))]
                except TypeError:
                    preds["origin_prompt"] = None
            preds = {k: preds[k] for k in signature(icl_evaluator.score).parameters}
            result = icl_evaluator.evaluate(k, n, copy.deepcopy(test_set), **preds)

            # Get model postprocess result
            model_details = None
            model_result = None
            if "model_postprocessor" in self.eval_cfg:
                model_preds = copy.deepcopy(preds)
                model_preds["predictions"] = model_pred_strs
                model_result = icl_evaluator.score(**model_preds)
                for key in model_result:
                    if key == "details":
                        model_details = model_result[key]
                        continue
                    new_key = "model_postprocess_" + key
                    result[new_key] = model_result[key]

            else:
                details = result.get("details", None)
                try:
                    if details is not None:
                        result["details"] = self.format_details(
                            pred_strs,
                            model_pred_strs,
                            test_set[self.output_column],
                            details,
                            model_details,
                            pred_dicts,
                        )
                        result["type"] = result["details"].pop("type", None)
                        if self.cal_extract_rate:
                            result["extract_rate"] = self.extract_rate(result)
                        if "PPL" in str(self.dataset_cfg.infer_cfg.inferencer.type):
                            result["correct_bpb"], result["incorrect_bpb"] = (
                                self.calculate_bpb(pred_dicts)
                            )
                except Exception as e:
                    self.logger.warning(
                        f"Skip dumping details due to format_details error: {e}."
                    )

        if "error" in result:
            self.logger.warning(
                f"Task {task_abbr_from_cfg(self.cfg)}: {result['error']}"
            )
            return
        elif model_result is None:
            result_wo_details = {i: result[i] for i in result if i != "details"}
            self.logger.info(
                f"Task {task_abbr_from_cfg(self.cfg)}: {result_wo_details}"
            )
        else:
            result_wo_details = {i: result[i] for i in result if i != "details"}
            model_result_wo_details = {
                i: model_result[i] for i in model_result if i != "details"
            }
            self.logger.info(
                f"Task {task_abbr_from_cfg(self.cfg)}: {result_wo_details}"
            )
            self.logger.info(
                "Model Postprocess Task: "
                + f"{task_abbr_from_cfg(self.cfg)}:{model_result_wo_details}"
            )

        # Save result
        out_path = get_infer_output_path(
            self.model_cfg, self.dataset_cfg, osp.join(self.work_dir, "results")
        )
        mkdir_or_exist(osp.split(out_path)[0])
        self.logger.debug(f"Save result to {out_path}")

        # Scheme A: Extract details to a JSONL file
        _details = result.pop("details", None)
        if _details is not None:
            details_out_path = out_path.replace(".json", "_details.jsonl")
            import json

            with open(details_out_path, "w", encoding="utf-8") as f:
                if isinstance(_details, dict):
                    # because format_details returns a dict with string keys 'type', '0', '1', ...
                    _details_list = [
                        _details[str(i)]
                        for i in range(len(pred_dicts))
                        if str(i) in _details
                    ]
                elif isinstance(_details, list):
                    _details_list = _details
                else:
                    _details_list = []

                written_ids = set()
                for i, d in enumerate(_details_list):
                    pred_dict = pred_dicts[i] if i < len(pred_dicts) else {}
                    item_id = pred_dict.get("id", i)

                    if item_id in written_ids:
                        continue
                    written_ids.add(item_id)

                    # Merge gold from evaluator details into prediction dict if not already present
                    gold_val = None
                    for _gold_key in ("gold", "references", "possible_answer", "answer"):
                        _v = d.get(_gold_key)
                        # unwrap single-element list produced by multi-shot grouping
                        if isinstance(_v, list) and len(_v) == 1:
                            _v = _v[0]
                        if _v is not None:
                            gold_val = _v
                            break
                    if gold_val is not None and "gold" not in pred_dict:
                        pred_dict = dict(pred_dict)  # shallow copy to avoid mutating shared ref
                        pred_dict["gold"] = gold_val

                    out_record = {
                        "prediction": pred_dict,
                        "eval_res": d.get("eval_res", d.get("correct", False)),
                        "eval_details": d.get("eval_details", None),
                    }

                    # Ensure lists are unwrapped if they contain single elements, due to Evaluator inner logic handling multiple shots
                    if (
                        isinstance(out_record["eval_res"], list)
                        and len(out_record["eval_res"]) > 0
                    ):
                        out_record["eval_res"] = out_record["eval_res"][0]
                    if (
                        isinstance(out_record["eval_details"], list)
                        and len(out_record["eval_details"]) > 0
                    ):
                        out_record["eval_details"] = out_record["eval_details"][0]

                    f.write(json.dumps(out_record, ensure_ascii=False) + "\n")
            self.logger.debug(f"Save details to {details_out_path}")

        mmengine.dump(result, out_path, ensure_ascii=False, indent=4)

    def extract_rate(self, results):
        """This function is designed for calculating the extraction rate.

        Args:
            results (dict): The result dict, include the information
        """
        details = results["details"]
        details_list = list(details.values())
        invalid_extractions = []
        for item in details_list:
            try:
                invalid_extractions.extend([item] if not item["predictions"] else [])
            except KeyError as e:
                self.logger.warning(f"Skip {e} due to: {item}")
                raise KeyError
        success_rate = 100 - len(invalid_extractions) / len(details) * 100
        return success_rate

    def format_details(
        self,
        predictions,
        model_pred_strs,
        references,
        details,
        model_details,
        pred_dicts,
    ):
        """This function is responsible for formatting prediction details.

        Args:
            predictions (list): The prediction list.
            references (list): The reference list.
            details (list): Contains the 'pred' 'answer' and 'correct' for each
                sample. Such as `[{'pred': '光荣和ωforce',
                'answers': ['光荣和ω-force', '光荣和ωforce'], 'correct': True}]`
            pred_dicts (list): Contains a list of samples with the original
                prompts. Such as
                `[{'origin_prompt': '根据文章回答问题。你的答案应该尽可能3》…………',
                'prediction': ' 光荣和ω-force\n', 'gold': ['光荣和ω-force']}]`

        Returns:
            list: The formatted prediction details.
        """
        results = {}
        for i in range(len(predictions)):
            ppl_flag = False
            result = {}
            origin_prediction = copy.deepcopy(pred_dicts[i])
            origin_prediction.pop("in-context examples", None)
            origin_prediction.pop("prediction", None)
            keys = copy.deepcopy(list(origin_prediction.keys()))
            for key in keys:
                if key.startswith("label:"):
                    ppl_flag = True
                    origin_prediction[key].pop("testing input", None)
                    new_key = key.replace("label: ", "")
                    origin_prediction[new_key] = origin_prediction.pop(key)
            if ppl_flag:
                self.logger.debug(f"PPL type prediction")
                results["type"] = "PPL"
                result["origin_prediction"] = origin_prediction
                result["predictions"] = str(predictions[i])
                result["references"] = str(references[i])
                result["correct"] = str(predictions[i]) == str(references[i])
            elif details is not None and model_details is not None:
                if model_pred_strs == []:
                    raise ParameterValueError(
                        TEVAL_CODES.UNKNOWN_ERROR,
                        f"Model details is not None, but model_pred_strs is empty",
                    )
                self.logger.debug(f"GEN type prediction")
                results["type"] = "GEN"
                result["prompt"] = origin_prediction.get("origin_prompt", "")
                result["origin_prediction"] = pred_dicts[i].get("prediction", "")
                result["predictions"] = details[i].get("pred", str(predictions[i]))
                result["model_extract_predictions"] = model_details[i].get("pred", "")
                result["references"] = details[i].get("answer", str(references[i]))
                if "correct" in details[i]:
                    result["correct"] = details[i]["correct"]
                if "correct" in model_details[i]:
                    result["model_extract_correct"] = model_details[i]["correct"]

                # Unified eval_res and eval_details using model_details
                if "eval_res" in model_details[i]:
                    result["eval_res"] = model_details[i]["eval_res"]
                elif "llm_score" in model_details[i]:
                    result["eval_res"] = str(model_details[i]["llm_score"])
                elif "is_correct" in model_details[i]:
                    result["eval_res"] = model_details[i]["is_correct"]
                elif "correct" in model_details[i]:
                    result["eval_res"] = model_details[i]["correct"]
                else:
                    result["eval_res"] = False

                if "eval_details" in model_details[i]:
                    result["eval_details"] = model_details[i]["eval_details"]
                elif "judge_output" in model_details[i]:
                    result["eval_details"] = {
                        "judge_output": model_details[i]["judge_output"]
                    }
                else:
                    result["eval_details"] = None
            elif details is not None:
                self.logger.debug(f"GEN type prediction")
                results["type"] = "GEN"
                result["prompt"] = origin_prediction.get("origin_prompt", "")
                result["origin_prediction"] = pred_dicts[i].get("prediction", "")
                result["predictions"] = details[i].get("pred", str(predictions[i]))
                result["references"] = details[i].get("answer", str(references[i]))
                if "correct" in details[i]:
                    result["correct"] = details[i]["correct"]

                # Unified eval_res and eval_details
                if "eval_res" in details[i]:
                    result["eval_res"] = details[i]["eval_res"]
                elif "llm_score" in details[i]:
                    result["eval_res"] = str(details[i]["llm_score"])
                elif "is_correct" in details[i]:
                    result["eval_res"] = details[i]["is_correct"]
                elif "correct" in details[i]:
                    result["eval_res"] = details[i]["correct"]
                else:
                    result["eval_res"] = False

                if "eval_details" in details[i]:
                    result["eval_details"] = details[i]["eval_details"]
                elif "judge_output" in details[i]:
                    result["eval_details"] = {
                        "judge_output": details[i]["judge_output"]
                    }
                else:
                    result["eval_details"] = None
            else:
                self.logger.debug(f"GEN type prediction")
                results["type"] = "GEN"
                result["prompt"] = origin_prediction["origin_prompt"]
                result["origin_prediction"] = pred_dicts[i]["prediction"]
                result["predictions"] = str(predictions[i])
                result["references"] = str(references[i])
            results[str(i)] = result
        return results

    def calculate_bpb(self, pred_dicts: List):
        """This function is used to calculate the BPB (Bits Per Byte) for the
        data. The correct BPB is obtained directly from the values in the
        'predictions' file. The incorrect BPB is the average of the remaining
        BPB values for each sample under different labels after subtracting the
        correct BPB. The calculation of BPB (Bits Per Byte) is similar to PPL,
        with the difference that it computes the additional bits needed on
        average, in terms of character length, to encode the true sequence
        based on the predictions. This calculation involves applying a
        weighting factor based on the ratio of words to characters.

        Args:
            pred_dicts (list): Contains a list of samples with each options
                and BPB scores.

        Returns:
            dict: Contains correct and incorrect bpb.
        """
        incorrect_bpb_list = []
        bpb_list = []
        for pred_dict in pred_dicts:
            preds = {
                key: value
                for key, value in pred_dict.items()
                if key.startswith("label: ")
            }
            values = []
            for item in preds.items():
                values.append(item[1])
            bpbs = [value["BPB"] for value in values]
            incorrect_bpb_list.append((sum(bpbs) - min(bpbs)) / (len(bpbs) - 1))
            bpb_list.append(min(bpbs))

        def filters(origins):
            targets = [target for target in origins if not math.isnan(target)]
            return targets

        mean_incorrect = statistics.mean(filters(incorrect_bpb_list))
        mean_correct = statistics.mean(filters(bpb_list))
        return 100 * mean_correct, 100 * mean_incorrect


def parse_args():
    parser = argparse.ArgumentParser(description="Score Calculator")
    parser.add_argument("config", help="Config file path")
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    logger = AISLogger()
    args = parse_args()
    cfg = Config.fromfile(args.config)
    task_state_manager = TaskStateManager(
        tmp_path=os.path.join(cfg["work_dir"], "status_tmp"),
        task_name=task_abbr_from_cfg(cfg),
        is_debug=cfg["cli_args"]["debug"],
    )
    manager_t = threading.Thread(target=task_state_manager.launch, args=())
    manager_t.start()
    task_state_manager.update_task_state(
        {
            "status": "start",
            "task_log_path": os.path.join(
                "logs/eval/", f"{task_abbr_from_cfg(cfg)}.out"
            ),
        }
    )
    start_time = time.perf_counter()
    try:
        evaluator: OpenICLEvalTask = OpenICLEvalTask(cfg)
        evaluator.run()
    except Exception as e:
        task_state_manager.update_task_state({"status": "error"})
        raise e

    end_time = time.perf_counter()
    logger.info(f"Evaluation task time elapsed: {end_time - start_time:.2f}s")
    task_state_manager.update_task_state({"status": "finish"})
    manager_t.join()
