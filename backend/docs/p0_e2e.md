# P0 端到端验证

前置：docker 镜像 benchmark-eval:latest 已存在；workspace 配置正确。

## 1. 启动后端

```bash
cd backend
pip install -e '.[dev]'
python -m backend.scripts.seed_tasks
EVAL_BACKEND_WORKSPACE_DIR=/opt/eval_workspace \
EVAL_BACKEND_CODE_DIR=/opt/eval_workspace/code \
uvicorn backend.app.main:app --host 0.0.0.0 --port 8080
```

## 2. 注册一个模型

```bash
curl -X POST http://localhost:8080/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"name":"qwen32b","host":"188.109.35.147","port":9092,"model_name":"qwen3-32b","concurrency":20}'
```

## 3. 查看任务

```bash
curl http://localhost:8080/api/v1/tasks
```

## 4. 创建一个小批次（一个模型 × 一个任务 × 推理+评测）

```bash
curl -X POST http://localhost:8080/api/v1/batches \
  -H 'Content-Type: application/json' \
  -d '{"name":"smoke-1","mode":"all","model_ids":[1],"task_ids":[1]}'
```

## 5. 观察 job 进度

```bash
watch -n 2 'curl -s http://localhost:8080/api/v1/jobs?batch_id=1 | jq'
```

## 6. 查看战报

```bash
curl http://localhost:8080/api/v1/batches/1/report | jq
```

## 验收标准

- `/api/v1/jobs` 状态从 pending → running → success
- `/api/v1/batches/1/report` 返回的 row 有 accuracy 值（数字）
- `backend_data/logs/job_{id}.log` 存在可查看
- `outputs/{output_task_id}/eval_{version}/` 下有实际产物
