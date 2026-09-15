测试与日志最佳实践参考指南
=============

一份关于使用 structlog 进行结构化日志记录以及全面测试策略的简明参考指南。

* * *

目录
--

**第 1 部分：使用 structlog 记录日志**

1.  [为什么选择 structlog](https://www.google.com/search?q=%231-%E4%B8%BA%E4%BB%80%E4%B9%88%E9%80%89%E6%8B%A9-structlog)
2.  [配置](https://www.google.com/search?q=%232-%E9%85%8D%E7%BD%AE)
3.  [FastAPI 集成](https://www.google.com/search?q=%233-fastapi-%E9%9B%86%E6%88%90)
4.  [上下文绑定 (Context Binding)](https://www.google.com/search?q=%234-%E4%B8%8A%E4%B8%8B%E6%96%87%E7%BB%91%E5%AE%9A)
5.  [异常日志记录](https://www.google.com/search?q=%235-%E5%BC%82%E5%B8%B8%E6%97%A5%E5%BF%97%E8%AE%B0%E5%BD%95)
6.  [使用 structlog 进行测试](https://www.google.com/search?q=%236-%E4%BD%BF%E7%94%A8-structlog-%E8%BF%9B%E8%A1%8C%E6%B5%8B%E8%AF%95)

**第 2 部分：测试策略** 7. 
[测试金字塔](https://www.google.com/search?q=%237-%E6%B5%8B%E8%AF%95%E9%87%91%E5%AD%97%E5%A1%94)
 8. 
[单元测试 (Python)](https://www.google.com/search?q=%238-%E5%8D%95%E5%85%83%E6%B5%8B%E8%AF%95-python)
 9. 
[集成测试 (FastAPI)](https://www.google.com/search?q=%239-%E9%9B%86%E6%88%90%E6%B5%8B%E8%AF%95-fastapi)
 10. 
[React 组件测试](https://www.google.com/search?q=%2310-react-%E7%BB%84%E4%BB%B6%E6%B5%8B%E8%AF%95)
 11. 
[使用 Playwright 进行 E2E 测试](https://www.google.com/search?q=%2311-%E4%BD%BF%E7%94%A8-playwright-%E8%BF%9B%E8%A1%8C-e2e-%E6%B5%8B%E8%AF%95)
 12. 
[测试组织结构](https://www.google.com/search?q=%2312-%E6%B5%8B%E8%AF%95%E7%BB%84%E7%BB%87%E7%BB%93%E6%9E%84)

* * *

第 1 部分：使用 structlog 记录日志
========================

1\. 为什么选择 structlog
-------------------

### 与标准日志库 (Standard Logging) 的对比

| 功能  | 标准日志库 (Standard logging) | structlog |
| --- | --- | --- |
| 输出格式 | 纯文本 | 结构化键值对 |
| 上下文 | 每次调用需手动传入 | 绑定后的记录器自动携带上下文 |
| 配置  | 复杂的层级结构 | 声明式的处理器链 (Processor chains) |
| JSON 输出 | 需要自定义格式化器 | 内置支持 |
| 性能  | 良好  | 通过缓存机制实现极佳性能 |

### 核心优势

*   **结构化数据**：日志以键值对形式呈现，易于解析。
*   **绑定记录器 (Bound loggers)**：一次添加上下文，后续所有日志都会携带。
*   **处理器管道 (Processor pipelines)**：通过可组合的函数转换日志。
*   **环境感知**：开发环境使用美观的控制台输出，生产环境使用 JSON。

* * *

2\. 配置
------

### 基础设置

```
# app/logging_config.py
import logging
import structlog

def configure_logging(json_format: bool = False):
    """为应用程序配置 structlog。"""

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_format:
        # 生产环境：JSON 输出
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # 开发环境：美化控制台输出
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

### 基于环境的配置

```
import os
import sys

def configure_logging():
    # 自动检测：生产/CI 环境使用 JSON，开发环境使用控制台
    use_json = (
        os.environ.get("LOG_JSON", "false").lower() == "true"
        or os.environ.get("CI", "false").lower() == "true"
        or not sys.stderr.isatty()
    )
    configure_logging(json_format=use_json)
```

### 在 FastAPI 中初始化

```
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.logging_config import configure_logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    yield

app = FastAPI(lifespan=lifespan)
```

* * *

3\. FastAPI 集成
--------------

### 请求日志中间件

```
# app/middleware.py
import time
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

logger = structlog.get_logger()

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 清除上下文并绑定请求信息
        structlog.contextvars.clear_contextvars()

        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "Request completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Request failed",
                duration_ms=round(duration_ms, 2),
            )
            raise
```

### 将中间件添加到应用

```
# app/main.py
from app.middleware import LoggingMiddleware

app.add_middleware(LoggingMiddleware)
```

* * *

4\. 上下文绑定
---------

### 请求范围上下文 (Request-Scoped Context)

```
import structlog

# 在中间件或请求处理早期阶段执行
structlog.contextvars.bind_contextvars(
    request_id="abc-123",
    user_id=42,
    path="/api/habits",
)

# 后续所有日志都会自动包含这些上下文
logger = structlog.get_logger()
logger.info("Processing request")  # 包含 request_id, user_id, path
logger.info("Fetching data")       # 包含相同的上下文
```

### 临时上下文

```
# 为特定代码块添加临时上下文
with structlog.contextvars.bound_contextvars(operation="streak_calculation"):
    logger.info("Starting calculation")
    # ... 执行任务
    logger.info("Calculation complete")
# 代码块结束后上下文将恢复
```

### 针对记录器的绑定 (Per-Logger Binding)

```
# 创建一个带有绑定上下文的记录器
logger = structlog.get_logger().bind(
    component="habit_service",
    version="1.0",
)

logger.info("Service started")  # 包含 component, version
```

* * *

5\. 异常日志记录
----------

### 记录异常

```
logger = structlog.get_logger()

try:
    risky_operation()
except Exception:
    # 选项 1：使用 exc_info=True
    logger.error("Operation failed", exc_info=True)

    # 选项 2：使用 .exception() 方法 (效果等同于 error 配合 exc_info=True)
    logger.exception("Operation failed")
```

### 结构化异常输出

对于 JSON 日志，请配置 `dict_tracebacks` 处理器：

```
structlog.processors.dict_tracebacks
```

这将生成 JSON 序列化的异常数据，而不是多行字符串。

* * *

6\. 使用 structlog 进行测试
---------------------

### 使用 capture\_logs

```
import structlog
from structlog.testing import capture_logs

def test_logs_habit_creation():
    with capture_logs() as captured:
        # 调用会记录日志的函数
        create_habit("Exercise")

    assert captured == [
        {
            "event": "Habit created",
            "habit_name": "Exercise",
            "log_level": "info",
        }
    ]
```

### Pytest Fixture

```
# tests/conftest.py
import pytest
import structlog
from structlog.testing import LogCapture

@pytest.fixture
def log_output():
    return LogCapture()

@pytest.fixture(autouse=True)
def configure_structlog(log_output):
    structlog.configure(processors=[log_output])
    yield
    structlog.reset_defaults()
```

```
# tests/test_service.py
def test_service_logs_correctly(log_output):
    do_something()

    assert log_output.entries == [
        {"event": "something happened", "log_level": "info"}
    ]
```

* * *

第 2 部分：测试策略
===========

7\. 测试金字塔
---------

### 比例分配

| 层级  | 百分比 | 速度  | 范围  |
| --- | --- | --- | --- |
| 单元测试 (Unit) | 70% | 毫秒级 | 单个函数/类 |
| 集成测试 (Integration) | 20% | 秒级  | 多个组件协作 |
| 端到端测试 (E2E) | 10% | 分钟级 | 整个系统 |

### 各层级适用范围

**单元测试 (Unit Tests)：**

*   纯函数（连续天数计算、日期工具类）
*   Pydantic 验证器
*   带有模拟依赖 (Mocked dependencies) 的业务逻辑

**集成测试 (Integration Tests)：**

*   使用真实数据库的 API 端点
*   存储库 (Repository) 操作
*   使用真实依赖的服务层

**E2E 测试 (E2E Tests)：**

*   仅针对关键用户路径
*   完整的完整的前端 + 后端交互
*   视觉回归测试

* * *

8\. 单元测试 (Python)
-----------------

### 结构

```
# tests/unit/test_streak_calculator.py
import pytest
from datetime import date
from app.services.streak import calculate_streak

class TestStreakCalculation:
    def test_returns_zero_for_empty_completions(self):
        result = calculate_streak([])
        assert result == 0

    def test_returns_one_for_single_completion_today(self):
        result = calculate_streak([date.today()])
        assert result == 1

    def test_counts_consecutive_days(self):
        completions = [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)]
        result = calculate_streak(completions)
        assert result == 3

    def test_breaks_on_gap(self):
        completions = [date(2025, 1, 1), date(2025, 1, 3)]  # 1月2日有缺漏
        result = calculate_streak(completions)
        assert result == 1  # 只有 1月3日计入
```

### 参数化测试

```
@pytest.mark.parametrize("completions,expected", [
    ([], 0),
    ([date(2025, 1, 1)], 1),
    ([date(2025, 1, 1), date(2025, 1, 2)], 2),
    ([date(2025, 1, 1), date(2025, 1, 3)], 1),  # 缺漏会中断连续天数
])
def test_streak_calculation(completions, expected):
    assert calculate_streak(completions) == expected
```

### 模拟 (Mocking)

```
from unittest.mock import Mock, patch

def test_service_calls_repository():
    mock_repo = Mock()
    mock_repo.get_by_id.return_value = Habit(id=1, name="Exercise")

    service = HabitService(repository=mock_repo)
    result = service.get_habit(1)

    mock_repo.get_by_id.assert_called_once_with(1)
    assert result.name == "Exercise"
```

* * *

9\. 集成测试 (FastAPI)
------------------

### 测试设置

```
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

@pytest.fixture(scope="function")
def db_session():
    """为每个测试创建一个全新的数据库。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)

@pytest.fixture(scope="function")
def client(db_session):
    """创建带有数据库覆盖的测试客户端。"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
```

### API 测试

```
# tests/integration/test_api_habits.py

class TestHabitAPI:
    def test_create_habit_returns_201(self, client):
        response = client.post(
            "/api/habits",
            json={"name": "Exercise", "description": "Daily workout"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Exercise"
        assert "id" in data

    def test_create_habit_without_name_returns_422(self, client):
        response = client.post("/api/habits", json={})

        assert response.status_code == 422

    def test_get_habit_returns_habit(self, client, db_session):
        # 准备：在数据库中创建习惯
        habit = Habit(name="Test", created_at=datetime.utcnow())
        db_session.add(habit)
        db_session.commit()

        # 测试
        response = client.get(f"/api/habits/{habit.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Test"

    def test_get_nonexistent_habit_returns_404(self, client):
        response = client.get("/api/habits/99999")

        assert response.status_code == 404
```

### 使用事务实现数据库隔离

```
@pytest.fixture
def db_session():
    """每个测试后回滚以实现隔离。"""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
```

* * *

10\. React 组件测试
---------------

### 使用 Vitest 进行设置

```
// vite.config.js
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
  },
});

// src/test/setup.js
import '@testing-library/jest-dom';
```

### 组件测试

```
// src/features/habits/__tests__/HabitCard.test.jsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HabitCard } from '../components/HabitCard';

describe('HabitCard', () => {
  const mockHabit = {
    id: 1,
    name: 'Exercise',
    currentStreak: 5,
    completedToday: false,
  };

  it('renders habit name', () => {
    render(<HabitCard habit={mockHabit} />);

    expect(screen.getByText('Exercise')).toBeInTheDocument();
  });

  it('displays current streak', () => {
    render(<HabitCard habit={mockHabit} />);

    expect(screen.getByText(/5.*streak/i)).toBeInTheDocument();
  });

  it('calls onComplete when button clicked', async () => {
    const onComplete = vi.fn();
    render(<HabitCard habit={mockHabit} onComplete={onComplete} />);

    await userEvent.click(screen.getByRole('button', { name: /complete/i }));

    expect(onComplete).toHaveBeenCalledWith(1);
  });

  it('shows completed state', () => {
    const completedHabit = { ...mockHabit, completedToday: true };
    render(<HabitCard habit={completedHabit} />);

    expect(screen.getByRole('button')).toBeDisabled();
  });
});
```

### 包含 Provider 的测试

```
// src/test/utils.jsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

export function renderWithProviders(ui) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {ui}
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

### 查询优先级 (按顺序使用)

1.  `getByRole` - 辅助功能名称（最佳实践）
2.  `getByLabelText` - 表单标签
3.  `getByText` - 文本内容
4.  `getByTestId` - 最后的手段
    
```
// 推荐写法
screen.getByRole('button', { name: /submit/i });
screen.getByLabelText('Email');

// 避免使用
screen.getByTestId('submit-button');  // 仅在必要时使用
```

* * *

11\. 使用 Playwright 进行 E2E 测试
----------------------------

### Playwright MCP 服务器设置

```
# 将 Playwright MCP 添加到 Claude Code
claude mcp add playwright npx @playwright/mcp@latest
```

### 配置

```
// playwright.config.js
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
  },
});
```

### 页面对象模型 (Page Object Model)

```
// tests/e2e/pages/DashboardPage.js
export class DashboardPage {
  constructor(page) {
    this.page = page;
    this.addHabitButton = page.getByRole('button', { name: /add habit/i });
    this.habitList = page.getByTestId('habit-list');
  }

  async goto() {
    await this.page.goto('/');
  }

  async addHabit(name) {
    await this.addHabitButton.click();
    await this.page.getByLabel('Habit name').fill(name);
    await this.page.getByRole('button', { name: /save/i }).click();
  }

  async completeHabit(name) {
    const habitCard = this.page.getByTestId(`habit-${name}`);
    await habitCard.getByRole('button', { name: /complete/i }).click();
  }

  async getHabitStreak(name) {
    const habitCard = this.page.getByTestId(`habit-${name}`);
    return habitCard.getByTestId('streak-count').textContent();
  }
}
```

### E2E 测试

```
// tests/e2e/habits.spec.js
import { test, expect } from '@playwright/test';
import { DashboardPage } from './pages/DashboardPage';

test.describe('Habit Tracking', () => {
  test('user can create and complete a habit', async ({ page }) => {
    const dashboard = new DashboardPage(page);

    await dashboard.goto();
    await dashboard.addHabit('Exercise');

    // 验证习惯已显示
    await expect(page.getByText('Exercise')).toBeVisible();

    // 完成习惯
    await dashboard.completeHabit('Exercise');

    // 验证连续天数已更新
    await expect(page.getByTestId('streak-count')).toHaveText('1');
  });

  test('streak increments on consecutive days', async ({ page }) => {
    // 使用预设种子数据测试多日场景
  });
});
```

### 视觉测试 (Visual Testing)

```
test('dashboard matches snapshot', async ({ page }) => {
  await page.goto('/');

  // 等待数据加载
  await expect(page.getByTestId('habit-list')).toBeVisible();

  // 对比快照
  await expect(page).toHaveScreenshot('dashboard.png', {
    mask: [page.locator('.timestamp')],  // 屏蔽动态内容
  });
});
```

### 运行 E2E 测试

```
# 运行所有 E2E 测试
npx playwright test

# 以 UI 模式运行 (调试用)
npx playwright test --ui

# 运行特定测试文件
npx playwright test habits.spec.js

# 更新快照
npx playwright test --update-snapshots
```

* * *

12\. 测试组织结构
-----------

### 目录结构

```
tests/
├── conftest.py                 # 共享 fixture
├── pytest.ini                  # Pytest 配置
├── unit/
│   ├── conftest.py             # 单元测试 fixture
│   ├── test_streak.py
│   └── test_validators.py
├── integration/
│   ├── conftest.py             # 集成测试 fixture (db, client)
│   ├── test_api_habits.py
│   └── test_api_completions.py
└── e2e/
    ├── playwright.config.js
    ├── pages/
    │   └── DashboardPage.js
    └── habits.spec.js

frontend/
└── src/
    ├── features/
    │   └── habits/
    │       └── __tests__/
    │           ├── HabitCard.test.jsx
    │           └── useHabits.test.js
    └── test/
        ├── setup.js
        └── utils.jsx
```

### Pytest 标记 (Markers)

```
# pytest.ini
[pytest]
markers =
    unit: 单元测试 (运行快，无 I/O)
    integration: 集成测试 (涉及数据库, API)
    slow: 运行较慢的测试
```

```
@pytest.mark.unit
def test_calculate_streak():
    pass

@pytest.mark.integration
def test_api_creates_habit():
    pass
```

```
# 按标记运行
pytest -m unit
pytest -m integration
pytest -m "not slow"
```

### 覆盖率配置 (Coverage)

```
# pyproject.toml
[tool.coverage.run]
source = ["app"]
omit = ["*/tests/*", "*/__pycache__/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
]
fail_under = 80
```

```
# 运行并生成覆盖率报告
pytest --cov=app --cov-report=html --cov-report=term-missing
```

* * *

快速参考
----

### 测试命令

```
# 后端
pytest                              # 运行所有测试
pytest tests/unit                   # 仅运行单元测试
pytest tests/integration            # 仅运行集成测试
pytest -m unit                      # 按标记运行
pytest --cov=app                    # 检查覆盖率
pytest -x                           # 遇到第一次失败即停止
pytest -v                           # 输出详细信息

# 前端
npm test                            # 运行所有测试
npm test -- --watch                 # 监听模式
npm test -- --coverage              # 检查覆盖率

# E2E
npx playwright test                 # 运行所有 E2E 测试
npx playwright test --ui            # UI 模式
npx playwright test --debug         # 调试模式
```

### 断言速记表 (Assertion Cheatsheet)

```
# Pytest
assert result == expected
assert result is not None
assert "text" in result
assert len(items) == 3
pytest.raises(ValueError)
```

```
// React Testing Library
expect(element).toBeInTheDocument();
expect(element).toBeVisible();
expect(element).toHaveText('text');
expect(element).toBeDisabled();
expect(mockFn).toHaveBeenCalledWith(arg);
```

```
// Playwright
await expect(locator).toBeVisible();
await expect(locator).toHaveText('text');
await expect(page).toHaveURL('/path');
await expect(page).toHaveScreenshot();
```

* * *

资源
--

*   [structlog 文档](https://www.structlog.org/)
*   [pytest 文档](https://docs.pytest.org/)
*   [FastAPI 测试指南](https://fastapi.tiangolo.com/tutorial/testing/)
*   [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
*   [Playwright 文档](https://playwright.dev/)
*   [Playwright MCP](https://github.com/microsoft/playwright-mcp)
