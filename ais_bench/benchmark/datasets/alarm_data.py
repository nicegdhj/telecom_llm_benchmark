import json
import os
from datasets import Dataset

from ais_bench.benchmark.registry import LOAD_DATASET
from ais_bench.benchmark.datasets.base import BaseDataset
from ais_bench.benchmark.utils.logging.logger import AISLogger

logger = AISLogger()

@LOAD_DATASET.register_module()
class AlarmDataDataset(BaseDataset):

    @staticmethod
    def load(path: str, name: str = None, **kwargs):
        if os.path.isdir(path):
            if name:
                full_path = os.path.join(path, f"{name}.json")
                if not os.path.exists(full_path):
                    full_path = os.path.join(path, f"{name}.jsonl")
            else:
                candidates = [f for f in os.listdir(path) if f.endswith('.json') or f.endswith('.jsonl')]
                full_path = os.path.join(path, candidates[0]) if candidates else None
        else:
            full_path = path

        if not full_path or not os.path.exists(full_path):
            raise FileNotFoundError(f"Alarm data file not found: {full_path}")

        data_list = []
        with open(full_path, 'r', encoding='utf-8') as f:
            if full_path.endswith('.json'):
                data = json.load(f)
                for item in data:
                    messages = item.get('messages', [])
                    system_prompt = ""
                    user_prompt = ""
                    assistant_response = ""
                    
                    for msg in messages:
                        if msg['role'] == 'system':
                            system_prompt = msg['content']
                        elif msg['role'] == 'user':
                            user_prompt = msg['content']
                        elif msg['role'] == 'assistant':
                            assistant_response = msg['content']
                    
                    question = ""
                    if system_prompt:
                        question += f"{system_prompt}\n\n"
                    question += user_prompt

                    data_list.append({
                        'question': question,
                        'answer': assistant_response,
                        'reference': assistant_response
                    })
            else:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    messages = item.get('messages', [])
                    system_prompt = ""
                    user_prompt = ""
                    assistant_response = ""
                    
                    for msg in messages:
                        if msg['role'] == 'system':
                            system_prompt = msg['content']
                        elif msg['role'] == 'user':
                            user_prompt = msg['content']
                        elif msg['role'] == 'assistant':
                            assistant_response = msg['content']
                    
                    question = ""
                    if system_prompt:
                        question += f"{system_prompt}\n\n"
                    question += user_prompt

                    data_list.append({
                        'question': question,
                        'answer': assistant_response,
                        'reference': assistant_response
                    })
                
        logger.info(f"[AlarmDataDataset] Loaded {len(data_list)} samples from {full_path}")
        return Dataset.from_list(data_list)
