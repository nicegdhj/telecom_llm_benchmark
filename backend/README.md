# 评测后端

## 运行

    cd backend
    pip install -e '.[dev]'
    uvicorn app.main:app --reload --port 8080

## 测试

    pytest -v
