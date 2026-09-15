from importlib import import_module


build_ot_dataset = import_module(
    "ais_bench.benchmark.configs.datasets.ot_full._common"
).build_ot_dataset


ot_3gpp_tsg_datasets = build_ot_dataset(
    "ot_3gpp_tsg", "3gpp_tsg", "json_label", "json_label"
)
