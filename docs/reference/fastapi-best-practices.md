FastAPI 最佳实践参考指南
================

构建生产级 FastAPI 应用程序的简明参考指南。

* * *

目录
--

1.  [项目结构](https://www.google.com/search?q=%231-%E9%A1%B9%E7%9B%AE%E7%BB%93%E6%9E%84)
2.  [路由与端点](https://www.google.com/search?q=%232-%E8%B7%AF%E7%94%B1%E4%B8%8E%E7%AB%AF%E7%82%B9)
3.  [Pydantic 模型与校验](https://www.google.com/search?q=%233-pydantic-%E6%A8%A1%E5%9E%8B%E4%B8%8E%E6%A0%A1%E9%AA%8C)
4.  [依赖注入](https://www.google.com/search?q=%234-%E4%BE%9D%E8%B5%96%E6%B3%A8%E5%85%A5)
5.  [错误处理](https://www.google.com/search?q=%235-%E9%94%99%E8%AF%AF%E5%A4%84%E7%90%86)
6.  [数据库集成](https://www.google.com/search?q=%236-%E6%95%B0%E6%8D%AE%E5%BA%93%E9%9B%86%E6%88%90)
7.  [性能与异步](https://www.google.com/search?q=%237-%E6%80%A7%E8%83%BD%E4%B8%8E%E5%BC%82%E6%AD%A5)
8.  [测试](https://www.google.com/search?q=%238-%E6%B5%8B%E8%AF%95)
9.  [安全](https://www.google.com/search?q=%239-%E5%AE%89%E5%85%A8)
10.  [配置](https://www.google.com/search?q=%2310-%E9%85%8D%E7%BD%AE)
11.  [反模式](https://www.google.com/search?q=%2311-%E5%8F%8D%E6%A8%A1%E5%BC%8F)

* * *

1\. 项目结构
--------

### 小型项目（按文件类型组织结构）

```
app/
├── main.py           # FastAPI 实例
├── routers/          # API 路由处理器
├── models.py         # SQLAlchemy 模型
├── schemas.py        # Pydantic 模式 (Schemas)
├── database.py       # 数据库配置
├── dependencies.py   # 共享依赖项
└── config.py         # 设置
```

### 大型项目（按领域/业务组织结构）

```
src/
├── habits/           # 习惯业务模块
│   ├── router.py
│   ├── schemas.py
│   ├── models.py
│   ├── service.py
│   ├── dependencies.py
│   └── exceptions.py
├── completions/      # 完成情况业务模块
│   └── (结构同上)
├── shared/           # 共享模块
│   ├── config.py
│   ├── database.py
│   └── exceptions.py
└── main.py
```

### 核心原则

*   **关注点分离**：将路由、模型、模式、服务逻辑分开。
*   **每个领域一个路由**：将相关的端点分组在一起。
*   **显式导入**：跨包导入时使用完整的模块路径。
    
```
# 推荐：显式导入
from src.habits import service as habits_service
from src.habits import constants as habits_constants

# 避免：模糊导入
from src.habits.service import *
```

* * *

2\. 路由与端点
---------

### 使用 APIRouter

```
from fastapi import APIRouter, Depends, status

router = APIRouter(
    prefix="/habits",
    tags=["habits"],
    responses={404: {"description": "未找到"}},
)

@router.get("/", response_model=list[HabitResponse])
async def list_habits():
    pass

@router.post("/", response_model=HabitResponse, status_code=status.HTTP_201_CREATED)
async def create_habit(habit: HabitCreate):
    pass
```

### 在主应用中引入

```
from fastapi import FastAPI
from .routers import habits, completions

app = FastAPI()
app.include_router(habits.router, prefix="/api")
app.include_router(completions.router, prefix="/api")
```

### 路径参数 vs 查询参数

```
from typing import Annotated
from fastapi import Path, Query

@router.get("/habits/{habit_id}")
async def get_habit(
    # 路径参数：用于资源标识
    habit_id: Annotated[int, Path(ge=1, description="习惯 ID")],
    # 查询参数：用于过滤/选项
    include_stats: Annotated[bool, Query()] = False,
):
    pass
```

**经验法则**：

*   路径参数用于资源标识：`/habits/{id}`
*   查询参数用于过滤、排序、分页：`/habits?status=active&page=1`

### 响应模型与状态码

```
from fastapi import status
from fastapi.responses import JSONResponse

@router.post("/", response_model=HabitResponse, status_code=status.HTTP_201_CREATED)
async def create_habit(habit: HabitCreate):
    return created_habit

@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_habit(habit_id: int):
    return None  # 204 状态码没有响应体

@router.get("/{habit_id}")
async def get_habit(habit_id: int):
    if not habit:
        raise HTTPException(status_code=404, detail="习惯未找到")
    return habit
```

### API 版本控制

```
# URL 路径版本控制（推荐）
app.include_router(v1_router, prefix="/api/v1")
app.include_router(v2_router, prefix="/api/v2")

# 或者使用子应用
v1_app = FastAPI()
v2_app = FastAPI()
app.mount("/api/v1", v1_app)
app.mount("/api/v2", v2_app)
```

* * *

3\. Pydantic 模型与校验
------------------

### 基础 Schema 模式

```
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # 用于 ORM 兼容性
```

### 请求/响应 Schema 模式

```
from pydantic import BaseModel, Field

# 共享属性
class HabitBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None

# 创建 Schema - 客户端发送的数据
class HabitCreate(HabitBase):
    color: str = Field(default="#10B981", pattern=r"^#[0-9A-Fa-f]{6}$")

# 更新 Schema - 所有字段均为可选
class HabitUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")

# 响应 Schema - 包含数据库字段，排除敏感数据
class HabitResponse(HabitBase):
    id: int
    color: str
    created_at: datetime
    current_streak: int
    completion_rate: float

    model_config = ConfigDict(from_attributes=True)
```

### 字段校验

```
from pydantic import BaseModel, Field, field_validator, model_validator

class HabitCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    target_days: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("名称不能为空")
        return v.strip()

    @field_validator("target_days")
    @classmethod
    def validate_days(cls, v: list[str]) -> list[str]:
        valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        for day in v:
            if day.lower() not in valid_days:
                raise ValueError(f"无效的日期: {day}")
        return [d.lower() for d in v]

    @model_validator(mode="after")
    def check_consistency(self):
        # 跨字段校验
        return self
```

### 嵌套模型

```
class CompletionResponse(BaseModel):
    date: str
    status: str
    notes: str | None

class HabitDetailResponse(HabitResponse):
    completions: list[CompletionResponse]
    longest_streak: int
```

### OpenAPI 示例

```
class HabitCreate(BaseModel):
    name: str
    description: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "晨练",
                    "description": "30 分钟有氧运动",
                }
            ]
        }
    )
```

* * *

4\. 依赖注入
--------

### 基础依赖项

```
from fastapi import Depends

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/habits")
def list_habits(db: Session = Depends(get_db)):
    return db.query(Habit).all()
```

### 校验依赖项

```
from fastapi import Depends, HTTPException

async def valid_habit_id(habit_id: int, db: Session = Depends(get_db)) -> Habit:
    habit = db.query(Habit).filter(Habit.id == habit_id).first()
    if not habit:
        raise HTTPException(status_code=404, detail="习惯未找到")
    return habit

@router.get("/habits/{habit_id}")
async def get_habit(habit: Habit = Depends(valid_habit_id)):
    return habit  # 已经过校验并获取

@router.delete("/habits/{habit_id}")
async def delete_habit(habit: Habit = Depends(valid_habit_id), db: Session = Depends(get_db)):
    db.delete(habit)
    db.commit()
```

### 链式依赖项

```
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    # 解码并校验 token
    return user

async def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_active:
        raise HTTPException(status_code=400, detail="非活动用户")
    return user

@router.get("/me")
async def read_current_user(user: User = Depends(get_current_active_user)):
    return user
```

### 类形式的依赖项

```
class Pagination:
    def __init__(self, skip: int = 0, limit: int = Query(default=100, le=100)):
        self.skip = skip
        self.limit = limit

@router.get("/habits")
async def list_habits(pagination: Pagination = Depends()):
    return habits[pagination.skip : pagination.skip + pagination.limit]
```

### 关键点

*   默认情况下，依赖项在 **单个请求内会被缓存**。
*   使用 `Depends(dep, use_cache=False)` 来禁用缓存。
*   尽可能对依赖项使用 `async def`。
*   依赖项可以依赖于其他依赖项（形成链式调用）。

* * *

5\. 错误处理
--------

### HTTPException

```
from fastapi import HTTPException, status

@router.get("/habits/{habit_id}")
async def get_habit(habit_id: int):
    habit = get_habit_by_id(habit_id)
    if not habit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="习惯未找到",
            headers={"X-Error-Code": "HABIT_NOT_FOUND"},
        )
    return habit
```

### 自定义异常类

```
# exceptions.py
class AppException(Exception):
    def __init__(self, status_code: int, detail: str, error_code: str):
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code

class HabitNotFoundError(AppException):
    def __init__(self, habit_id: int):
        super().__init__(
            status_code=404,
            detail=f"未找到 ID 为 {habit_id} 的习惯",
            error_code="HABIT_NOT_FOUND",
        )

class DuplicateCompletionError(AppException):
    def __init__(self, habit_id: int, date: str):
        super().__init__(
            status_code=409,
            detail=f"习惯 {habit_id} 在 {date} 已有完成记录",
            error_code="DUPLICATE_COMPLETION",
        )
```

### 全局异常处理器

```
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "detail": exc.detail,
            "path": str(request.url),
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "detail": exc.errors(),
        },
    )
```

### 统一的错误响应格式

```
{
    "error": "HABIT_NOT_FOUND",
    "detail": "未找到 ID 为 123 的习惯",
    "path": "/api/habits/123"
}
```

* * *

6\. 数据库集成
---------

### SQLAlchemy 设置

```
# database.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./habits.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # 仅限 SQLite
)

# 为 SQLite 应用 PRAGMA 设置
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
```

### 模型定义

```
# models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

class Habit(Base):
    __tablename__ = "habits"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    color = Column(String(7), default="#10B981")
    created_at = Column(DateTime, default=datetime.utcnow)
    archived_at = Column(DateTime, nullable=True)

    completions = relationship(
        "Completion",
        back_populates="habit",
        cascade="all, delete-orphan",
        lazy="selectin",  # 适用于集合加载
    )

class Completion(Base):
    __tablename__ = "completions"

    id = Column(Integer, primary_key=True, index=True)
    habit_id = Column(Integer, ForeignKey("habits.id", ondelete="CASCADE"), nullable=False, index=True)
    completed_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    status = Column(String(10), default="completed")  # completed, skipped
    notes = Column(Text)

    habit = relationship("Habit", back_populates="completions")

    __table_args__ = (
        UniqueConstraint("habit_id", "completed_date", name="uq_habit_date"),
    )
```

### 带有上下文管理器的依赖项

```
from typing import Generator
from sqlalchemy.orm import Session

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 仓储模式（可选）

```
# repositories/habits.py
class HabitRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, habit_id: int) -> Habit | None:
        return self.db.query(Habit).filter(Habit.id == habit_id).first()

    def get_all(self, include_archived: bool = False) -> list[Habit]:
        query = self.db.query(Habit)
        if not include_archived:
            query = query.filter(Habit.archived_at.is_(None))
        return query.all()

    def create(self, data: HabitCreate) -> Habit:
        habit = Habit(**data.model_dump())
        self.db.add(habit)
        self.db.commit()
        self.db.refresh(habit)
        return habit
```

### 预加载 (Eager Loading)

```
from sqlalchemy.orm import joinedload, selectinload

# 用于多对一关系
habit = db.query(Habit).options(joinedload(Habit.category)).first()

# 用于一对多集合
habits = db.query(Habit).options(selectinload(Habit.completions)).all()
```

* * *

7\. 性能与异步
---------

### 异步 vs 同步函数

| 任务类型 | 函数定义 | 原因  |
| --- | --- | --- |
| 异步 I/O (数据库, HTTP) | `async def` | 非阻塞 |
| 同步/阻塞 I/O | `def` | 在线程池中运行 |
| CPU 密集型 | 外部 worker (如 Celery) | 避免阻塞主线程 |

```
# 推荐：对 I/O 操作使用异步
@router.get("/habits")
async def list_habits(db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(Habit))
    return result.scalars().all()

# 推荐：对阻塞操作使用同步（FastAPI 会自动在线程池处理）
@router.get("/file")
def read_file():
    with open("file.txt") as f:
        return f.read()

# 错误：在异步函数中调用阻塞代码
@router.get("/bad")
async def bad_endpoint():
    time.sleep(5)  # 阻塞整个事件循环！
    return {"status": "done"}
```

### 后台任务

```
from fastapi import BackgroundTasks

def send_notification(email: str, message: str):
    # 耗时较长的任务
    pass

@router.post("/habits")
async def create_habit(habit: HabitCreate, background_tasks: BackgroundTasks):
    created_habit = create_habit_in_db(habit)
    background_tasks.add_task(send_notification, "user@example.com", "习惯已创建！")
    return created_habit
```

### 缓存

```
from functools import lru_cache

# 缓存设置（仅调用一次）
@lru_cache
def get_settings():
    return Settings()

# 对于 Redis 缓存，使用 fastapi-cache
from fastapi_cache.decorator import cache

@router.get("/stats")
@cache(expire=60)
async def get_stats():
    return calculate_expensive_stats()
```

* * *

8\. 测试
------

### 基础测试设置

```
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        yield session

@pytest.fixture(name="client")
def client_fixture(session):
    def get_session_override():
        return session

    app.dependency_overrides[get_db] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
```

### 编写测试

```
# tests/test_habits.py
def test_create_habit(client):
    response = client.post(
        "/api/habits",
        json={"name": "运动", "description": "每日健身"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "运动"
    assert "id" in data

def test_create_habit_validation_error(client):
    response = client.post("/api/habits", json={"name": ""})
    assert response.status_code == 422

def test_get_habit_not_found(client):
    response = client.get("/api/habits/999")
    assert response.status_code == 404

def test_list_habits(client, session):
    # 设置
    habit = Habit(name="测试习惯")
    session.add(habit)
    session.commit()

    # 测试
    response = client.get("/api/habits")
    assert response.status_code == 200
    assert len(response.json()) == 1
```

### 异步测试

```
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.mark.anyio
async def test_async_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/habits")
        assert response.status_code == 200
```

* * *

9\. 安全
------

### 输入校验

FastAPI + Pydantic 处理了大部分校验。其他措施如下：

```
from pydantic import BaseModel, Field, field_validator
import bleach

class CommentCreate(BaseModel):
    content: str = Field(..., max_length=1000)

    @field_validator("content")
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        return bleach.clean(v)  # 移除 XSS 攻击向量
```

### CORS 配置

```
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # 指定来源，不要使用 "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

### SQL 注入防御

```
# 推荐：使用 ORM
habit = db.query(Habit).filter(Habit.id == habit_id).first()

# 推荐：参数化查询
result = db.execute(text("SELECT * FROM habits WHERE id = :id"), {"id": habit_id})

# 错误：字符串格式化（易受攻击！）
db.execute(f"SELECT * FROM habits WHERE id = {habit_id}")  # 绝不要这样做
```

### 速率限制 (限流)

```
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/api/habits")
@limiter.limit("100/minute")
async def list_habits(request: Request):
    pass
```

* * *

10\. 配置
-------

### 使用 Pydantic Settings

```
# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "习惯追踪器"
    database_url: str = "sqlite:///./habits.db"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### 使用方法

```
from .config import get_settings

settings = get_settings()
print(settings.database_url)
```

### .env 文件示例

```
DATABASE_URL=sqlite:///./habits.db
DEBUG=true
CORS_ORIGINS=["http://localhost:5173"]
```

* * *

11\. 反模式
--------

### 应当避免的关键反模式

| 反模式 | 问题  | 解决方案 |
| --- | --- | --- |
| 在 `async def` 中使用阻塞 I/O | 导致事件循环停滞 | 使用异步库或改用普通 `def` |
| 端点对端点调用 | 强耦合 | 使用服务层 (Service Layer) |
| 全局可变状态 | 竞态条件 | 使用 Redis 或数据库 |
| 直接返回 ORM 对象 | 暴露内部实现细节 | 使用响应 Schema |
| 不使用 Pydantic | 缺失校验 | 始终定义 Schema |
| 字符串格式化 SQL | SQL 注入风险 | 使用 ORM 或参数化查询 |
| 硬编码配置 | 灵活性差 | 使用环境变量 |

### 常见错误示例

```
# 错误：在异步函数中阻塞
async def bad():
    time.sleep(5)  # 阻塞事件循环

# 错误：不关闭数据库连接
def bad_db():
    return SessionLocal()  # 永远不会关闭！

# 错误：在请求之间共享 session
db = SessionLocal()  # 全局 session - 会导致竞态条件！

# 错误：暴露内部模型
@router.get("/habits")
def list_habits(db: Session = Depends(get_db)):
    return db.query(Habit).all()  # 直接返回 ORM 对象

# 推荐：使用响应模型 (response_model)
@router.get("/habits", response_model=list[HabitResponse])
def list_habits(db: Session = Depends(get_db)):
    return db.query(Habit).all()  # 通过 Pydantic 序列化
```

* * *

寿命周期事件 (Lifespan Events)
------------------------

### 现代模式（推荐）

```
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动阶段
    print("正在启动...")
    # 初始化资源（数据库连接池、缓存等）
    yield
    # 停机阶段
    print("正在关闭...")
    # 清理资源
运用
app = FastAPI(lifespan=lifespan)
```

* * *

快速参考
----

### HTTP 状态码

| 代码  | 常量  | 使用场景 |
| --- | --- | --- |
| 200 | `HTTP_200_OK` | 成功的 GET, PUT |
| 201 | `HTTP_201_CREATED` | 成功的 POST |
| 204 | `HTTP_204_NO_CONTENT` | 成功的 DELETE |
| 400 | `HTTP_400_BAD_REQUEST` | 无效请求 |
| 404 | `HTTP_404_NOT_FOUND` | 资源未找到 |
| 409 | `HTTP_409_CONFLICT` | 资源冲突（如重复） |
| 422 | `HTTP_422_UNPROCESSABLE_ENTITY` | 校验错误 |
| 500 | `HTTP_500_INTERNAL_SERVER_ERROR` | 服务器内部错误 |

### 常用导入语句

```
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Query, Path, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, ConfigDict
from sqlalchemy.orm import Session
from typing import Annotated
```

* * *

资源
--
*   [FastAPI 官方文档](https://fastapi.tiangolo.com/)
*   [Pydantic 官方文档](https://docs.pydantic.dev/)
*   [SQLAlchemy 2.0 官方文档](https://docs.sqlalchemy.org/en/20/)
*   [FastAPI 最佳实践 (GitHub)](https://github.com/zhanymkanov/fastapi-best-practices)


