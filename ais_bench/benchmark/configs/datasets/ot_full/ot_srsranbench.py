from importlib import import_module


build_ot_dataset = import_module(
    "ais_bench.benchmark.configs.datasets.ot_full._common"
).build_ot_dataset


ot_srsranbench_datasets = build_ot_dataset(
    "ot_srsranbench", "srsranbench", "mcq", "mcq"
)
