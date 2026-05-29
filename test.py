import sys
import os

# Add the script's directory to sys.path to allow importing ais_bench
benchmark_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, benchmark_dir)

# Also set PYTHONPATH so that any child processes spawned by TaskManager can inherit it
os.environ["PYTHONPATH"] = benchmark_dir + os.pathsep + os.environ.get("PYTHONPATH", "")

if sys.platform == "darwin":
    import multiprocessing
    multiprocessing.set_start_method("fork", force=True)
# # 强制设置命令行参数
# sys.argv = [
#     'ais_bench', 
#     '--models', 'bailian_qwen_plus',
#     '--datasets', 
#         'opseval_gen_0_shot',
#     '--debug',
#     '--work-dir', './outputs',
#     '--max-num-workers', '1',  
#     '--num-prompts', '1',
#     # '--mode','eval',
#     # '--reuse','20260317_144540'
# ]
# #'--models', 'maas_api',
# #'--reuse',"20260227_113125"
# from ais_bench.benchmark.cli.task_manager import TaskManager

# def main():
#     task_manager = TaskManager()
#     task_manager.run()

# if __name__ == '__main__':
#     main()
    
DATASETS = [
    # 'mmlu_redux_gen_5_shot_str.py',
    'ceval_gen_0_shot_str.py',
    # 'gpqa_gen_0_shot_str.py',
    # 'bbh_gen_3_shot_cot_chat.py',
    # 'BFCL_gen_simple.py',
    # 'ifeval_0_shot_gen_str.py',
    # 'math500_gen_0_shot_cot_chat_prompt.py',
    # 'aime2025_gen_0_shot_chat_prompt.py',
    # 'humaneval_gen_0_shot.py',
    # 'livecodebench_0_shot_chat_v6.py',
    # 'identity_gen_0_shot.py',
    # 'telemath_gen_0_cot_shot.py',
    # 'opseval_gen_0_shot.py',
    # 'teleqna_gen_0_shot.py',
    # 'tspec_gen_0_shot.py',
    # 'teledata_gen_0_shot.py',
    # 'telequad_gen_0_shot.py',
    # 'tele_exam_gen_0_shot.py',
    # 'tele_exam_gen_0_shot_str.py',
    # 'exam_gen_0_shot.py',
    # 'task_1_suite.py',
    # 'task_34_suite.py',
    # 'task_36_suite.py',
    # 'task_43_suite.py',
    # 'task_44_suite.py',
    # 'task_60_suite.py',
    # 'alarm_data_gen_0_shot.py',
    # 'expert_qa_gen.py'
]
# MODEL = 'maas_jt_api'
MODEL = 'bailian_qwen_plus'
WORK_DIR = './outputs'

def run_single_dataset(dataset_name):
    """模拟 ais_bench --models xxx --datasets yyy"""
    print(f"\n[INFO] Running dataset: {dataset_name}")
    
    # 临时覆盖 sys.argv
    original_argv = sys.argv.copy()
    try:
        sys.argv = [
            'ais_bench',
            '--models', MODEL,
            '--datasets', dataset_name,
            '--work-dir', WORK_DIR,
            '--max-num-workers', '1',
            '--debug',
            '--num-prompts', '1',
            '--mode','eval',
            '--reuse','20260417_160614'
        ]
        
        from ais_bench.benchmark.cli.task_manager import TaskManager
        task_manager = TaskManager()
        task_manager.run()
        
    except Exception as e:
        print(f"[ERROR] Failed on {dataset_name}: {e}")
    finally:
        # 恢复原始 argv（可选）
        sys.argv = original_argv

def main():
    for ds in DATASETS:
        run_single_dataset(ds)

if __name__ == '__main__':
    main()   

