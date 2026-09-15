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
            
        if file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path)
        elif file_path.endswith('.jsonl') or file_path.endswith('.json'):
            df = pd.read_json(file_path, lines=True)
        else:
            try:
                df = pd.read_excel(file_path)
            except Exception:
                try:
                    df = pd.read_json(file_path, lines=True)
                except Exception as e:
                    raise ValueError(f"Unsupported file format or error loading file: {file_path}. Error: {e}")
        
        # Ensure we have the required columns
        q_col = None
        for col in ['问题', 'question', 'instruction']:
            if col in df.columns:
                q_col = col
                break
        if q_col is None:
            raise ValueError(f"File must contain '问题', 'question', or 'instruction' column, found: {df.columns.tolist()}")
        
        ans_col = None
        for col in ['答案', '标准答案', 'answer', 'output']:
            if col in df.columns:
                ans_col = col
                break
        if ans_col is None:
            raise ValueError(f"File must contain '答案', '标准答案', 'answer', or 'output' column, found: {df.columns.tolist()}")
            
        # Convert to Huggingface Dataset format
        # rename q_col -> 'question', ans_col -> 'answer'
        df = df.rename(columns={q_col: 'question', ans_col: 'answer'})
        
        # Replace NaNs with empty string and convert all to string to avoid pyarrow mixed type errors
        df = df.fillna('')
        df = df.astype(str)
        
        # Convert to dict list
        data_list = df.to_dict('records')
        
        return Dataset.from_list(data_list)
