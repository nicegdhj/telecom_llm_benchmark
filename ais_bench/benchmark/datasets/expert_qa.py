import os
import pandas as pd
from datasets import Dataset, DatasetDict
from ais_bench.benchmark.registry import LOAD_DATASET
from ais_bench.benchmark.datasets.utils.datasets import get_data_path
from ais_bench.benchmark.utils.logging.logger import AISLogger
from ais_bench.benchmark.datasets.base import BaseDataset

logger = AISLogger()

@LOAD_DATASET.register_module()
class ExpertQADataset(BaseDataset):
    @staticmethod
    def load(path: str, name: str, local_mode: bool = True):
        # We can handle absolute path or relative path via get_data_path
        base_path = get_data_path(path, local_mode=local_mode)
        file_path = os.path.join(base_path, name)
        
        logger.debug(f"Loading ExpertQA dataset from: {file_path}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"ExpertQA dataset file not found: {file_path}")
            
        df = pd.read_excel(file_path)
        
        # Ensure we have the required columns
        if '问题' not in df.columns:
            raise ValueError(f"Excel file must contain '问题' column, found: {df.columns.tolist()}")
        
        ans_col = None
        if '答案' in df.columns:
            ans_col = '答案'
        elif '标准答案' in df.columns:
            ans_col = '标准答案'
            
        if ans_col is None:
            raise ValueError(f"Excel file must contain '答案' or '标准答案' column, found: {df.columns.tolist()}")
            
        # Convert to Huggingface Dataset format
        # rename '问题' -> 'question', '答案'/'标准答案' -> 'answer'
        df = df.rename(columns={'问题': 'question', ans_col: 'answer'})
        
        # Replace NaNs with empty string and convert all to string to avoid pyarrow mixed type errors
        df = df.fillna('')
        df = df.astype(str)
        
        # Convert to dict list
        data_list = df.to_dict('records')
        
        return Dataset.from_list(data_list)
