import csv
import json
import os.path as osp
from os import environ
import random

from datasets import Dataset, DatasetDict

from ais_bench.benchmark.registry import LOAD_DATASET
from ais_bench.benchmark.datasets.utils.datasets import get_data_path
from ais_bench.benchmark.utils.logging.logger import AISLogger

# pyrefly: ignore [missing-import]
from .base import BaseDataset

logger = AISLogger()


@LOAD_DATASET.register_module()
class CEvalDataset(BaseDataset):

    @staticmethod
    def load(path: str, name: str, local_mode: bool = True):
        path = get_data_path(path, local_mode=local_mode)
        logger.debug(f"Loading C-Eval dataset '{name}' from: {path}")
        dataset = {}
        for split in ['dev', 'val', 'test']:
            filename = osp.join(path, split, f'{name}_{split}.csv')
            with open(filename, encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)
                for row in reader:
                    item = dict(zip(header, row))
                    item.setdefault('explanation', '')
                    item.setdefault('answer', '')
                    dataset.setdefault(split, []).append(item)
        if 'test' in dataset and len(dataset['test']) > 0:
            # 设置固定种子保证每次结果一致
            random.seed(42) 
            # 这里的 shuffle 是原地操作
            random.shuffle(dataset['test'])
            # 抽取 10%
            sample_size = max(1, len(dataset['test']) // 10)
            dataset['test'] = dataset['test'][:sample_size]
            logger.info(f"C-Eval '{name}' test split sampled to {len(dataset['test'])} items.")
        logger.debug(f"C-Eval '{name}' loaded: dev={len(dataset.get('dev', []))}, val={len(dataset.get('val', []))}, test={len(dataset.get('test', []))}")
        dataset = DatasetDict(
            {i: Dataset.from_list(dataset[i])
                for i in dataset})
        return dataset