SQLite & SQL 最佳实践参考指南
=====================

一份关于在 Python 应用程序中使用 SQLite 数据库的简洁参考指南。

* * *

目录
--

1.  [何时使用 SQLite](https://www.google.com/search?q=%231-%E4%BD%95%E6%97%B6%E4%BD%BF%E7%94%A8-sqlite)
2.  [模式设计 (Schema Design)](https://www.google.com/search?q=%232-%E6%A8%A1%E5%BC%8F%E8%AE%BE%E8%AE%A1)
3.  [数据类型](https://www.google.com/search?q=%233-%E6%95%B0%E6%8D%AE%E7%B1%BB%E5%9E%8B)
4.  [索引](https://www.google.com/search?q=%234-%E7%B4%A2%E5%BC%95)
5.  [查询优化](https://www.google.com/search?q=%235-%E6%9F%A5%E8%AF%A2%E4%BC%98%E5%8C%96)
6.  [SQLAlchemy 模式](https://www.google.com/search?q=%236-sqlalchemy-%E6%A8%A1%E5%BC%8F)
7.  [数据完整性](https://www.google.com/search?q=%237-%E6%95%B0%E6%8D%AE%E5%AE%8C%E6%95%B4%E6%80%A7)
8.  [事务](https://www.google.com/search?q=%238-%E4%BA%8B%E5%8A%A1)
9.  [Python 集成](https://www.google.com/search?q=%239-python-%E9%9B%86%E6%88%90)
10.  [性能调优](https://www.google.com/search?q=%2310-%E6%80%A7%E8%83%BD%E8%B0%83%E4%BC%98)
11.  [备份与恢复](https://www.google.com/search?q=%2311-%E5%A4%87%E4%BB%BD%E4%B8%8E%E6%81%A2%E5%A4%8D)
12.  [反模式 (Anti-Patterns)](https://www.google.com/search?q=%2312-%E5%8F%8D%E6%A8%A1%E5%BC%8F)

* * *

1\. 何时使用 SQLite
---------------

### 理想使用场景

*   **嵌入式/物联网设备**：移动应用、桌面应用、本地工具
*   **应用程序文件格式**：用于存储应用数据的单文件数据库
*   **低至中等流量网站**：每日请求量少于 10 万次
*   **开发与测试**：快速设置，无需服务器
*   **数据分析**：导入 CSV，运行 SQL 查询
*   **缓存层**：远程数据的本地缓存
*   **单用户应用程序**：个人工具、本地应用

### 何时不使用 SQLite

*   **高写入并发**：SQLite 每次只允许一个写入者
*   **网络文件系统**：NFS、SMB 可能会导致损坏
*   **多服务器**：无法跨机器共享 SQLite
*   **超大型数据集**：超过 1TB 可能需要分布式解决方案
*   **高流量生产环境**：应考虑使用 PostgreSQL

### 关键特性

| 特性  | 数值  |
| --- | --- |
| 库大小 | \<600KB |
| 最大数据库大小 | 281 TB |
| 最大行大小 | 1 GB |
| 并发读取者 | 无限制 |
| 并发写入者 | 1   |
| 符合 ACID 特性 | 是   |

* * *

2\. 模式设计 (Schema Design)
------------------------

### 主键

```
-- 推荐方式：INTEGER PRIMARY KEY（别名指向 rowid，且自动增长）
CREATE TABLE habits (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 使用显式的 AUTOINCREMENT（防止删除后重复使用 rowid）
CREATE TABLE habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

-- 复合主键
CREATE TABLE completions (
    habit_id INTEGER NOT NULL,
    completed_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    PRIMARY KEY (habit_id, completed_date)
);
```

### 外键

```
-- 外键默认是禁用的 - 必须在每个连接中启用
PRAGMA foreign_keys = ON;

CREATE TABLE completions (
    id INTEGER PRIMARY KEY,
    habit_id INTEGER NOT NULL,
    completed_date TEXT NOT NULL,
    FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
);
```

**级联操作**：

| 操作  | 行为  |
| --- | --- |
| `NO ACTION` | 如果存在子行则拒绝（默认） |
| `CASCADE` | 删除/更新子行 |
| `SET NULL` | 将外键设置为 NULL |
| `SET DEFAULT` | 将外键设置为默认值 |
| `RESTRICT` | 类似于 NO ACTION，但会立即执行 |

### 表约束

```
CREATE TABLE habits (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#10B981',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    archived_at TEXT,

    -- 检查约束
    CHECK (length(name) > 0),
    CHECK (color GLOB '#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]')
);

CREATE TABLE completions (
    id INTEGER PRIMARY KEY,
    habit_id INTEGER NOT NULL,
    completed_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',

    FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE,
    UNIQUE (habit_id, completed_date),
    CHECK (status IN ('completed', 'skipped'))
);
```

### WITHOUT ROWID 表

```
-- 用于非整数或复合主键
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;
```

**何时使用**：

*   非整数主键
*   复合主键
*   行大小较小
*   频繁进行主键查找

**何时避免**：

*   大型主键（在所有索引中都会重复）
*   存在许多辅助索引
*   行大小较大

* * *

3\. 数据类型
--------

### SQLite 类型亲和性 (Type Affinity)

SQLite 使用动态类型——类型与值相关联，而不是与列相关联。

**五种存储类**：

| 类   | 描述  |
| --- | --- |
| `NULL` | NULL 值 |
| `INTEGER` | 有符号整数（1-8 字节） |
| `REAL` | 8 字节 IEEE 浮点数 |
| `TEXT` | UTF-8/UTF-16 字符串 |
| `BLOB` | 二进制数据 |

**类型亲和性规则**（基于声明的类型名称）：

1.  包含 "INT" → INTEGER
2.  包含 "CHAR", "CLOB", "TEXT" → TEXT
3.  包含 "BLOB" 或没有类型 → BLOB
4.  包含 "REAL", "FLOA", "DOUB" → REAL
5.  其他情况 → NUMERIC

### 日期/时间存储

**选项 1：TEXT (ISO 8601) - 推荐**

```
CREATE TABLE completions (
    id INTEGER PRIMARY KEY,
    completed_date TEXT NOT NULL,  -- 'YYYY-MM-DD'
    created_at TEXT NOT NULL DEFAULT (datetime('now'))  -- 'YYYY-MM-DD HH:MM:SS'
);

-- 查询示例
SELECT * FROM completions WHERE completed_date = '2025-01-15';
SELECT * FROM completions WHERE completed_date >= '2025-01-01' AND completed_date < '2025-02-01';
SELECT * FROM completions WHERE completed_date BETWEEN '2025-01-01' AND '2025-01-31';
```

**优点**：人类可读、按字典顺序排序、兼容 SQLite 日期函数。

**选项 2：INTEGER (Unix 时间戳)**

```
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    timestamp INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
);

-- 查询示例
SELECT * FROM events WHERE timestamp >= strftime('%s', '2025-01-01');
SELECT datetime(timestamp, 'unixepoch') as readable_time FROM events;
```

**优点**：存储更小（8 字节）、比较速度更快。

### 布尔值处理

```
-- SQLite 没有原生的 BOOLEAN - 使用 INTEGER 0/1
CREATE TABLE habits (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- TRUE 和 FALSE 是 1 和 0 的别名 (SQLite 3.23.0+)
INSERT INTO habits (name, is_active) VALUES ('Exercise', TRUE);
SELECT * FROM habits WHERE is_active = TRUE;
```

### JSON 存储

```
-- 存储为 TEXT，使用 JSON 函数查询 (SQLite 3.38.0+)
CREATE TABLE habits (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    settings TEXT  -- JSON 字符串
);

INSERT INTO habits (name, settings)
VALUES ('Exercise', '{"reminder_time": "09:00", "notifications": true}');

-- 查询 JSON
SELECT
    name,
    json_extract(settings, '$.reminder_time') as reminder
FROM habits
WHERE json_extract(settings, '$.notifications') = 1;
```

### STRICT 表 (SQLite 3.37.0+)

```
-- 强制类型检查
CREATE TABLE habits (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    count INTEGER NOT NULL
) STRICT;

-- 这将失败：INSERT INTO habits (name, count) VALUES ('Test', 'not a number');
```

* * *

4\. 索引
------

### 何时索引

*   `WHERE` 子句中的列
*   `JOIN` 条件中的列
*   `ORDER BY` 子句中的列
*   外键列（对 CASCADE 操作至关重要）

### 索引类型

```
-- 单列索引
CREATE INDEX idx_habits_name ON habits(name);

-- 复合索引（列顺序很重要！）
CREATE INDEX idx_completions_habit_date ON completions(habit_id, completed_date);

-- 唯一索引
CREATE UNIQUE INDEX idx_habits_name_unique ON habits(name);

-- 部分索引（仅索引行的子集）
CREATE INDEX idx_active_habits ON habits(name) WHERE archived_at IS NULL;

-- 表达式索引
CREATE INDEX idx_habits_lower_name ON habits(lower(name));
```

### 复合索引列顺序

复合索引中列的顺序非常重要：

```
CREATE INDEX idx_completions ON completions(habit_id, completed_date);

-- 使用索引（habit_id 是最左侧列）
SELECT * FROM completions WHERE habit_id = 1;

-- 使用索引（两列均按顺序使用）
SELECT * FROM completions WHERE habit_id = 1 AND completed_date = '2025-01-15';

-- 不会高效使用索引（completed_date 不是最左侧列）
SELECT * FROM completions WHERE completed_date = '2025-01-15';
```

### 覆盖索引 (Covering Indexes)

```
-- 包含查询所需的所有列，以避免查表
CREATE INDEX idx_completions_covering ON completions(habit_id, completed_date, status);

-- 此查询可完全由索引满足
SELECT completed_date, status FROM completions WHERE habit_id = 1;
```

### 索引权衡

| 收益  | 成本  |
| --- | --- |
| 读取速度更快 | 写入速度更慢 |
| ORDER BY 速度更快 | 占用更多磁盘空间 |
| JOIN 速度更快 | 内存开销 |

**经验法则**：每增加一个辅助索引，预期 INSERT 速度会变慢约 5 倍。

* * *

5\. 查询优化
--------

### EXPLAIN QUERY PLAN

```
EXPLAIN QUERY PLAN
SELECT h.name, COUNT(*) as completions
FROM habits h
JOIN completions c ON h.id = c.habit_id
WHERE c.completed_date >= '2025-01-01'
GROUP BY h.id;

-- 输出解读：
-- SCAN = 全表扫描（通常较差）
-- SEARCH = 使用索引（良好）
-- USING INDEX = 仅索引访问（极佳）
-- USING COVERING INDEX = 无需访问原始表（最佳）
```

### 查询技巧

```
-- 差：SELECT *
SELECT * FROM habits;

-- 好：仅选择需要的列
SELECT id, name, created_at FROM habits;

-- 差：在没有索引的情况下对前缀搜索使用 LIKE
SELECT * FROM habits WHERE name LIKE '%exercise%';

-- 好：前缀 LIKE 可以使用索引
SELECT * FROM habits WHERE name LIKE 'exercise%';

-- 差：在索引列上使用函数
SELECT * FROM habits WHERE lower(name) = 'exercise';

-- 好：创建表达式索引，或规范化数据
CREATE INDEX idx_lower_name ON habits(lower(name));

-- 差：在不同列上使用 OR（难以优化）
SELECT * FROM habits WHERE name = 'Exercise' OR description = 'workout';

-- 好：对复杂的 OR 条件使用 UNION
SELECT * FROM habits WHERE name = 'Exercise'
UNION
SELECT * FROM habits WHERE description = 'workout';
```

### 高效日期查询

```
-- 对于 TEXT 日期 (ISO 8601)
SELECT * FROM completions
WHERE completed_date >= '2025-01-01'
  AND completed_date < '2025-02-01';

-- 对于当前月份
SELECT * FROM completions
WHERE completed_date >= date('now', 'start of month')
  AND completed_date < date('now', 'start of month', '+1 month');

-- 不要对日期使用 LIKE
-- 差：WHERE completed_date LIKE '2025-01%'
```

### 运行 ANALYZE

```
-- 为查询规划器更新统计信息
ANALYZE;

-- 在关闭连接前运行 (SQLite 3.18.0+)
PRAGMA optimize;
```

* * *

6\. SQLAlchemy 模式
-----------------

### 引擎设置

```
from sqlalchemy import create_engine, event

engine = create_engine(
    "sqlite:///habits.db",
    connect_args={"check_same_thread": False},  # 用于多线程应用
    echo=False,  # 设置为 True 以开启 SQL 日志
)

# 在每个连接上应用 PRAGMA 设置
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.close()
```

### 模型定义

```
from sqlalchemy import Column, Integer, String, Text, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Habit(Base):
    __tablename__ = "habits"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    color = Column(String(7), default="#10B981")
    created_at = Column(String(19), nullable=False)  # YYYY-MM-DD HH:MM:SS
    archived_at = Column(String(19))

    completions = relationship(
        "Completion",
        back_populates="habit",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("length(name) > 0", name="name_not_empty"),
    )

class Completion(Base):
    __tablename__ = "completions"

    id = Column(Integer, primary_key=True)
    habit_id = Column(Integer, ForeignKey("habits.id", ondelete="CASCADE"), nullable=False, index=True)
    completed_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    status = Column(String(10), default="completed")
    notes = Column(Text)

    habit = relationship("Habit", back_populates="completions")

    __table_args__ = (
        UniqueConstraint("habit_id", "completed_date", name="uq_habit_date"),
        CheckConstraint("status IN ('completed', 'skipped')", name="valid_status"),
    )
```

### 关系加载策略

| 策略  | 使用场景 |
| --- | --- |
| `lazy="select"` | 默认，访问时产生 N+1 查询 |
| `lazy="joined"` | 多对一关系 |
| `lazy="selectin"` | 一对多集合 |
| `lazy="raise"` | 防止意外的懒加载 |

```
from sqlalchemy.orm import joinedload, selectinload

# 在查询中预加载 (Eager load)
habits = session.query(Habit).options(selectinload(Habit.completions)).all()

# 对于多对一
completions = session.query(Completion).options(joinedload(Completion.habit)).all()
```

### 会话管理

```
from sqlalchemy.orm import sessionmaker, Session

SessionLocal = sessionmaker(bind=engine)

# 上下文管理器模式（推荐）
def get_habits():
    with Session(engine) as session:
        return session.query(Habit).all()

# 包含事务处理
def create_habit(name: str):
    with Session(engine) as session, session.begin():
        habit = Habit(name=name, created_at=datetime.now().isoformat())
        session.add(habit)
        # 成功时自动提交，发生异常时自动回滚
        return habit

# 用于 FastAPI 依赖注入
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

* * *

7\. 数据完整性
---------

### 约束摘要

```
CREATE TABLE example (
    id INTEGER PRIMARY KEY,                    -- 主键
    name TEXT NOT NULL,                        -- 必填字段
    email TEXT UNIQUE,                         -- 无重复
    age INTEGER CHECK (age >= 0),              -- 数值验证
    category_id INTEGER REFERENCES categories(id),  -- 外键
    status TEXT DEFAULT 'active'               -- 默认值
);
```

### 强制执行外键

```
# 必须在每个连接中启用外键
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# 验证是否已启用
result = connection.execute("PRAGMA foreign_keys").fetchone()
assert result[0] == 1
```

### 软删除

```
-- 使用设置 archived_at 来代替 DELETE
UPDATE habits SET archived_at = datetime('now') WHERE id = 1;

-- 查询活动记录
SELECT * FROM habits WHERE archived_at IS NULL;

-- 为活动记录创建部分索引
CREATE INDEX idx_active_habits ON habits(name) WHERE archived_at IS NULL;
```

* * *

8\. 事务
------

### 基本事务

```
BEGIN TRANSACTION;
INSERT INTO habits (name, created_at) VALUES ('Exercise', datetime('now'));
INSERT INTO completions (habit_id, completed_date) VALUES (last_insert_rowid(), '2025-01-15');
COMMIT;

-- 发生错误时
ROLLBACK;
```

### Python 中的事务

```
# 显式事务
with engine.begin() as connection:
    connection.execute(text("INSERT INTO habits ..."))
    connection.execute(text("INSERT INTO completions ..."))
    # 成功时自动提交，发生异常时自动回滚

# SQLAlchemy ORM
with Session(engine) as session, session.begin():
    habit = Habit(name="Exercise")
    session.add(habit)
    completion = Completion(habit=habit, completed_date="2025-01-15")
    session.add(completion)
    # 自动提交/回滚
```

### 隔离级别

SQLite 默认支持可串行化 (serializable) 隔离。写入者会阻塞其他写入者，但读取者永远不会阻塞。

* * *

9\. Python 集成
-------------

### 连接基础

```
import sqlite3

# 上下文管理器（成功时提交，但不会自动关闭连接！）
with sqlite3.connect("habits.db") as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * * FROM habits")
    rows = cursor.fetchall()

# 显式关闭
conn = sqlite3.connect("habits.db")
try:
    # ... 操作
    conn.commit()
finally:
    conn.close()
```

### 参数化查询（防止 SQL 注入）

```
# 问号占位符
cursor.execute(
    "INSERT INTO habits (name, description) VALUES (?, ?)",
    (name, description)
)

# 命名占位符
cursor.execute(
    "INSERT INTO habits (name, description) VALUES (:name, :desc)",
    {"name": name, "desc": description}
)

# 用于 IN 子句
ids = [1, 2, 3]
placeholders = ",".join("?" * len(ids))
cursor.execute(f"SELECT * FROM habits WHERE id IN ({placeholders})", ids)

# 永远不要使用字符串格式化！
# 差：cursor.execute(f"SELECT * FROM habits WHERE name = '{user_input}'")
```

### 行工厂 (Row Factories)

```
# 将行作为字典返回
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT * FROM habits")
row = cursor.fetchone()
print(row["name"])  # 通过列名访问
print(row[0])       # 通过索引访问
print(dict(row))    # 转换为字典
```

### 批量操作

```
# 使用 executemany 进行大批量插入
data = [("Exercise",), ("Reading",), ("Meditation",)]
cursor.executemany("INSERT INTO habits (name) VALUES (?)", data)

# 为了性能，将其包裹在事务中
conn.execute("BEGIN")
try:
    for chunk in chunks(large_data, 1000):
        cursor.executemany("INSERT INTO habits (name) VALUES (?)", chunk)
    conn.commit()
except:
    conn.rollback()
    raise
```

* * *

10\. 性能调优
---------

### 核心 PRAGMA 设置

```
-- 在每个连接上运行
PRAGMA journal_mode = WAL;        -- 预写式日志（更好的并发性）
PRAGMA synchronous = NORMAL;      -- 在 WAL 模式下是安全的，比 FULL 快
PRAGMA foreign_keys = ON;         -- 启用外键约束
PRAGMA cache_size = -64000;       -- 64MB 页面缓存（负数表示 KB）
PRAGMA temp_store = MEMORY;       -- 在 RAM 中存储临时表
PRAGMA mmap_size = 268435456;     -- 256MB 内存映射 I/O

-- 定期运行或在关闭前运行
PRAGMA optimize;                   -- 优化查询规划器统计信息
```

### PRAGMA 参考

| PRAGMA | 用途  | 推荐值 |
| --- | --- | --- |
| `journal_mode` | 事务日志记录模式 | `WAL` |
| `synchronous` | 磁盘同步频率 | `NORMAL` (配合 WAL 使用) |
| `foreign_keys` | 外键强制执行 | `ON` |
| `cache_size` | 页面缓存大小 | `-64000` (64MB) |
| `temp_store` | 临时表存储位置 | `MEMORY` |
| `busy_timeout` | 等待锁定的时间 (ms) | `5000` |

### WAL 模式

```
PRAGMA journal_mode = WAL;
```

**收益**：

*   读取者不会阻塞写入者
*   写入者不会阻塞读取者
*   更好的崩溃恢复
*   对大多数工作负载而言速度更快

**局限性**：

*   不适用于网络文件系统
*   会在数据库旁创建 `-wal` 和 `-shm` 文件

### 数据库维护

```
-- 整理碎片并优化（在维护期间运行）
VACUUM;

-- 为查询规划器更新统计信息
ANALYZE;

-- 重建索引
REINDEX;

-- 检查数据库完整性
PRAGMA integrity_check;
```

* * *

11\. 备份与恢复
----------

### 安全的备份方法

```
import sqlite3

def backup_database(source_path: str, dest_path: str):
    """使用 SQLite 的备份 API 进行安全备份。"""
    source = sqlite3.connect(source_path)
    dest = sqlite3.connect(dest_path)

    with dest:
        source.backup(dest)

    dest.close()
    source.close()
```

```
-- VACUUM INTO 创建一个清理过的副本 (SQLite 3.27.0+)
VACUUM INTO '/path/to/backup.db';
```

### 禁忌事项

```
# 永远不要在运行中的数据库上使用 cp/copy - 这不是事务安全的！
cp database.db backup.db  # 差！
```

### Litestream (持续备份)

```
# litestream.yml
dbs:
  - path: /data/habits.db
    replicas:
      - url: s3://bucket-name/habits
        sync-interval: 1s
```

### 完整性检查

```
-- 全面完整性检查
PRAGMA integrity_check;

-- 快速检查（速度更快）
PRAGMA quick_check;

-- 如果健康则返回 'ok'
```

* * *

12\. 反模式 (Anti-Patterns)
------------------------

### 配置错误

| 错误  | 解决方案 |
| --- | --- |
| 未启用外键 | 每个连接运行 `PRAGMA foreign_keys=ON` |
| 使用默认日志模式 | 启用 WAL：`PRAGMA journal_mode=WAL` |
| 在网络文件系统上运行 SQLite | 仅使用本地文件系统 |

### 模式错误

| 错误  | 解决方案 |
| --- | --- |
| 存储逗号分隔的列表 | 使用规范的连接表 |
| 未对外键建立索引 | 始终对外键列建立索引 |
| 过度索引 | 仅对频繁查询的列建立索引 |
| 使用错误的日期格式 | 使用 ISO 8601：`YYYY-MM-DD` |

### 查询错误

| 错误  | 解决方案 |
| --- | --- |
| `SELECT *` | 仅选择需要的列 |
| 对日期查询使用 LIKE | 使用日期比较运算符 |
| 在索引列上使用函数 | 创建表达式索引 |
| 未使用 EXPLAIN | 分析慢查询 |

### Python 错误

| 错误  | 解决方案 |
| --- | --- |
| 字符串格式化 SQL | 使用参数化查询 |
| 未关闭连接 | 使用上下文管理器 |
| 每个请求都创建引擎 | 创建一次，重复使用 |
| 忽略 N+1 查询问题 | 使用预加载 (eager loading) |

* * *

快速参考
----

### 连接设置模板

```
from sqlalchemy import create_engine, event

engine = create_engine("sqlite:///habits.db", connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.close()
```

### SQLite 日期函数

```
-- 当前日期/时间
SELECT date('now');                    -- 2025-01-15
SELECT datetime('now');                -- 2025-01-15 12:30:00
SELECT strftime('%s', 'now');          -- Unix 时间戳

-- 日期算术
SELECT date('now', '-7 days');         -- 7 天前
SELECT date('now', '+1 month');        -- 1 个月后
SELECT date('now', 'start of month');  -- 当前月的第一天

-- 提取部分
SELECT strftime('%Y', '2025-01-15');   -- 2025
SELECT strftime('%m', '2025-01-15');   -- 01
SELECT strftime('%d', '2025-01-15');   -- 15
```

* * *

资源
--

*   [SQLite 官方文档](https://sqlite.org/docs.html)
*   [SQLite 何时使用指南](https://sqlite.org/whentouse.html)
*   [SQLAlchemy 2.0 文档](https://docs.sqlalchemy.org/en/20/)
*   [Litestream](https://litestream.io/)

