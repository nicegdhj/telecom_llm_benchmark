import re
import json
from typing import List
from datasets import Dataset

from ais_bench.benchmark.registry import ICL_EVALUATORS
from ais_bench.benchmark.openicl.icl_evaluator.icl_base_evaluator import BaseEvaluator
from ais_bench.benchmark.utils.logging.logger import AISLogger

def extract_clusters_from_text(text: str) -> List:
    if not isinstance(text, str):
        return []
    
    # 1. Try to extract from <clustering_labels> tag first
    match = re.search(r'<clustering_labels>(.*?)</clustering_labels>', text, re.DOTALL)
    if match:
        content = match.group(1).strip()
        try:
            return json.loads(content)
        except Exception:
            try:
                import ast
                return ast.literal_eval(content)
            except Exception:
                pass
    
    # 2. Try parsing the whole string directly as JSON
    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "clusters" in parsed:
            return parsed["clusters"]
    except Exception:
        pass
        
    # 3. Try literal eval on the whole string
    try:
        import ast
        parsed = ast.literal_eval(text.strip())
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
        
    return []

def normalize_clusters(clusters_list) -> set:
    normalized = set()
    if not isinstance(clusters_list, list):
        return normalized
    for c in clusters_list:
        if not isinstance(c, (list, tuple, set)):
            continue
        parsed_c = []
        for x in c:
            s = str(x).strip()
            # Remove "index " or "index_" prefix (case-insensitive)
            s = re.sub(r'^index[\s_]*', '', s, flags=re.IGNORECASE)
            parsed_c.append(s)
        if parsed_c:
            normalized.add(frozenset(parsed_c))
    return normalized

@ICL_EVALUATORS.register_module()
class AlarmClusterEvaluator(BaseEvaluator):
    def __init__(self) -> None:
        super().__init__()
        self.logger = AISLogger()

    def score(self, predictions: List, references: List, test_set: Dataset = None) -> dict:
        if len(predictions) != len(references):
            return {
                'error': f'Predictions and references have different length: {len(predictions)} vs {len(references)}'
            }

        correct_count = 0
        total_count = len(predictions)
        details = []

        for i in range(total_count):
            pred = predictions[i]
            ref = references[i]
            
            # Extract clusters from prediction
            pred_clusters = extract_clusters_from_text(pred)
            
            # Try to get gt_edges from test_set first
            gt_clusters = None
            if test_set and i < len(test_set):
                item = test_set[i]
                gt_edges = item.get('gt_edges')
                if gt_edges:
                    gt_clusters = extract_clusters_from_text(gt_edges)

            # Fallback to extracting from reference answer
            if not gt_clusters:
                gt_clusters = extract_clusters_from_text(ref)

            # Normalize and compare
            norm_pred = normalize_clusters(pred_clusters)
            norm_gt = normalize_clusters(gt_clusters)
            
            is_correct = (norm_pred == norm_gt)
            if is_correct:
                correct_count += 1
                
            self.logger.info(f"[AlarmClusterEvaluator] Sample {i}: is_correct={is_correct}")
            self.logger.info(f"  Normalized Pred: {norm_pred}")
            self.logger.info(f"  Normalized GT: {norm_gt}")

            details.append({
                'pred': pred,
                'answer': ref,
                'correct': is_correct,
                'eval_res': is_correct,
                'eval_details': {
                    'pred_clusters': pred_clusters,
                    'gt_clusters': gt_clusters,
                    'normalized_pred': [list(c) for c in norm_pred],
                    'normalized_gt': [list(c) for c in norm_gt]
                }
            })

        accuracy = (correct_count / total_count) * 100 if total_count > 0 else 0.0
        return {
            'accuracy': accuracy,
            'details': details
        }
