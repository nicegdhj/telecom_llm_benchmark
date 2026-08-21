MCQ_PROMPT = (
    "{input}\n\nSelect the correct answer and output only one option letter "
    "from A to E.\nAnswer:"
)
TELEMATH_PROMPT = (
    "{input}\nPlease reason step by step, and put your final answer "
    "within \\boxed{}."
)


def _infer_cfg(prompt):
    return dict(
        prompt_template=dict(
            type=(
                "ais_bench.benchmark.openicl.icl_prompt_template."
                "icl_prompt_template.PromptTemplate"
            ),
            template=prompt,
        ),
        retriever=dict(
            type=(
                "ais_bench.benchmark.openicl.icl_retriever."
                "icl_zero_retriever.ZeroRetriever"
            )
        ),
        inferencer=dict(
            type=(
                "ais_bench.benchmark.openicl.icl_inferencer."
                "icl_gen_inferencer.GenInferencer"
            )
        ),
    )


def build_ot_dataset(abbr, directory, mode, evaluator):
    if evaluator == "mcq":
        infer_cfg = _infer_cfg(MCQ_PROMPT)
        eval_cfg = dict(
            evaluator=dict(
                type=(
                    "ais_bench.benchmark.openicl.icl_evaluator."
                    "icl_hf_evaluator.AccEvaluator"
                )
            ),
            pred_postprocessor=dict(
                type=(
                    "ais_bench.benchmark.utils.postprocess."
                    "text_postprocessors.first_option_postprocess"
                ),
                options="ABCDE",
            ),
        )
    elif evaluator == "json_label":
        infer_cfg = _infer_cfg("{input}")
        eval_cfg = dict(
            evaluator=dict(
                type=(
                    "ais_bench.benchmark.openicl.icl_evaluator."
                    "json_field_evaluator.JsonFieldEvaluator"
                ),
                field_config={
                    "WORKING GROUP": {"match_type": "exact", "weight": 1.0},
                },
                default_match_type="exact",
                return_details=True,
                strict_mode=True,
            )
        )
    elif evaluator == "telelogs":
        infer_cfg = _infer_cfg("{input}")
        eval_cfg = dict(
            evaluator=dict(
                type=(
                    "ais_bench.benchmark.openicl.icl_evaluator."
                    "icl_hf_evaluator.AccEvaluator"
                )
            ),
            pred_postprocessor=dict(
                type=(
                    "ais_bench.benchmark.datasets.ot_full."
                    "telelogs_postprocess"
                )
            ),
        )
    elif evaluator == "math":
        infer_cfg = _infer_cfg(TELEMATH_PROMPT)
        eval_cfg = dict(
            evaluator=dict(
                type=(
                    "ais_bench.benchmark.openicl.icl_evaluator."
                    "math_evaluator.MATHEvaluator"
                )
            )
        )
    else:
        raise ValueError(f"unsupported OT evaluator: {evaluator}")

    return [
        dict(
            type="ais_bench.benchmark.datasets.ot_full.OTDataset",
            abbr=abbr,
            path=f"data/ot-full/{directory}/test-00000-of-00001.jsonl",
            mode=mode,
            reader_cfg=dict(input_columns=["input"], output_column="output"),
            infer_cfg=infer_cfg,
            eval_cfg=eval_cfg,
        )
    ]
