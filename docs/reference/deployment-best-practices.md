部署最佳实践参考指南
==========

一份关于部署 Python/FastAPI + React 应用的简洁参考手册。

* * *

目录
--

1.  [本地开发](https://www.google.com/search?q=%231-%E6%9C%AC%E5%9C%B0%E5%BC%80%E5%8F%91)
2.  [生产构建](https://www.google.com/search?q=%232-%E7%94%9F%E4%BA%A7%E6%9E%84%E5%BB%BA)
3.  [后端部署](https://www.google.com/search?q=%233-%E5%90%8E%E7%AB%AF%E9%83%A8%E7%BD%B2)
4.  [前端部署](https://www.google.com/search?q=%234-%E5%89%8D%E7%AB%AF%E9%83%A8%E7%BD%B2)
5.  [Docker](https://www.google.com/search?q=%235-docker)
6.  [反向代理 (Nginx)](https://www.google.com/search?q=%236-%E5%8F%8D%E5%90%91%E4%BB%A3%E7%90%86-nginx)
7.  [环境与配置](https://www.google.com/search?q=%237-%E7%8E%AF%E5%A2%83%E4%B8%8E%E9%85%8D%E7%BD%AE)
8.  [生产环境数据库](https://www.google.com/search?q=%238-%E7%94%9F%E4%BA%A7%E7%8E%AF%E5%A2%83%E6%95%B0%E6%8D%AE%E5%BA%93)
9.  [监控与日志](https://www.google.com/search?q=%239-%E7%9B%91%E6%8E%A7%E4%B8%8E%E6%97%A5%E5%BF%97)
10.  [云平台](https://www.google.com/search?q=%2310-%E4%BA%91%E5%B9%B3%E5%8F%B0)
11.  [安全](https://www.google.com/search?q=%2311-%E5%AE%89%E5%85%A8)
12.  [单个二进制文件部署](https://www.google.com/search?q=%2312-%E5%8D%95%E4%B8%AA%E4%BA%8C%E8%BF%9B%E5%88%B6%E6%96%87%E4%BB%B6%E9%83%A8%E7%BD%B2)

* * *

1\. 本地开发
--------

### 运行前端和后端

**双终端方式：**

```
# 终端 1: 后端
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows 用户: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 终端 2: 前端
cd frontend
npm install
npm run dev  # 运行在 5173 端口
```

### Vite 代理配置

通过 Vite 代理 API 请求来避免跨域 (CORS) 问题：

```
// frontend/vite.config.js
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

现在前端代码可以使用相对路径：

```
fetch('/api/habits')  // 会被代理到 http://localhost:8000/api/habits
```

### 热重载 (Hot Reloading)

*   **后端**: `uvicorn --reload` 监听文件更改。
*   **前端**: Vite 内置了 HMR (模块热替换)。

### 环境变量

```
# backend/.env
DATABASE_URL=sqlite:///./habits.db
DEBUG=true
CORS_ORIGINS=["http://localhost:5173"]

# frontend/.env
VITE_API_URL=/api
```

* * *

2\. 生产构建
--------

### 前端构建 (Vite)

```
cd frontend
npm run build  # 创建 dist/ 文件夹
```

**输出结构：**

```
dist/
├── index.html
├── assets/
│   ├── index-abc123.js
│   └── index-def456.css
```

### 构建优化

```
// vite.config.js
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          query: ['@tanstack/react-query'],
        },
      },
    },
  },
});
```

### 产物分析 (Bundle Analysis)

```
npm install rollup-plugin-visualizer --save-dev
```

```
// vite.config.js
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
  plugins: [
    react(),
    visualizer({ open: true }),
  ],
});
```

* * *

3\. 后端部署
--------

### Uvicorn (大多数场景下的推荐方案)

```
# 开发环境
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生产环境 (使用多个工作进程)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**工作进程数 (Worker count)**：对于异步工作进程，通常设置为 CPU 核心数。

### Gunicorn + Uvicorn 工作进程

```
# 安装
pip install gunicorn uvicorn

# 运行
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

**Gunicorn 配置文件示例：**

```
# gunicorn.conf.py
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count()
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 30
keepalive = 5
max_requests = 10000
max_requests_jitter = 1000
```

```
gunicorn app.main:app -c gunicorn.conf.py
```

### Systemd 服务

```
# /etc/systemd/system/habittracker.service
[Unit]
Description=Habit Tracker API
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/habit-tracker/backend
Environment="PATH=/var/www/habit-tracker/backend/.venv/bin"
ExecStart=/var/www/habit-tracker/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl enable habittracker
sudo systemctl start habittracker
sudo systemctl status habittracker
```

* * *

4\. 前端部署
--------

### 方案 1：FastAPI 提供静态文件服务

```
# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
import os

app = FastAPI()

# API 路由排在前面
@app.get("/api/habits")
async def list_habits():
    pass

# 服务 React 应用
frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")

@app.get("/")
async def serve_react_app():
    return FileResponse(os.path.join(frontend_path, "index.html"))

# 处理客户端路由 (Client-side routing)
@app.exception_handler(404)
async def custom_404_handler(request, exc):
    if not request.url.path.startswith("/api"):
        return FileResponse(os.path.join(frontend_path, "index.html"))
    raise exc

# 最后挂载静态文件
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
```

**优点**：单一部署，无跨域问题，基础设施更简单。

### 方案 2：Nginx 提供静态文件服务

静态资源性能更好：

```
server {
    listen 80;
    server_name yourdomain.com;
    root /var/www/habit-tracker/frontend/dist;

    # 服务静态文件
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 代理 API 到 FastAPI
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 方案 3：CDN/静态托管

将前端部署到 Vercel, Netlify 或 Cloudflare Pages：

```
# Vercel
npm install -g vercel
vercel --prod

# Netlify
npm install -g netlify-cli
netlify deploy --prod
```

为独立后端配置 API 地址：

```
// frontend/.env.production
VITE_API_URL=https://api.yourdomain.com
```

* * *

5\. Docker
----------

### Dockerfile (多阶段构建)

```
# backend/Dockerfile
# 阶段 1: 构建
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# 阶段 2: 运行环境
FROM python:3.11-slim

WORKDIR /app

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 从构建阶段复制依赖
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# 复制应用代码
COPY . .

# 设置权限
RUN chown -R appuser:appuser /app

# 切换到非 root 用户
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 前端 Dockerfile

```
# frontend/Dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Docker Compose

```
# docker-compose.yml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///./data/habits.db
    volumes:
      - ./data:/app/data  # 持久化 SQLite 数据库
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped
```

### Docker 常用命令

```
# 构建并运行
docker-compose up --build

# 后台运行
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重新构建单个服务
docker-compose up --build backend
```

### 镜像优化技巧

| 技巧  | 影响  |
| --- | --- |
| 使用 slim 基础镜像 | `python:3.11-slim` (45MB) vs 标准版 (125MB) |
| 多阶段构建 | 镜像体积减小 70% 以上 |
| 使用 `.dockerignore` | 构建速度更快 |
| 按变更频率排列层 | 更好的缓存利用 |
| 合并 RUN 命令 | 减少镜像层数 |

**.dockerignore:**

```
__pycache__
*.pyc
.git
.env
.venv
node_modules
dist
*.md
```

* * *

6\. 反向代理 (Nginx)
----------------

### 基础配置

```
# /etc/nginx/sites-available/habittracker
server {
    listen 80;
    server_name yourdomain.com;

    # 服务 React 静态文件
    root /var/www/habit-tracker/frontend/dist;
    index index.html;

    # 处理 React Router (客户端路由)
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 将 API 请求代理到 FastAPI
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 缓存静态资源
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 启用站点

```
sudo ln -s /etc/nginx/sites-available/habittracker /etc/nginx/sites-enabled/
sudo nginx -t  # 测试配置文件
sudo systemctl reload nginx
```

### 使用 Let's Encrypt 配置 SSL

```
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d yourdomain.com

# 自动续期 (certbot 已自动配置)
sudo certbot renew --dry-run
```

**结果** (由 certbot 自动生成):

```
server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # ... 其他配置
}

server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}
```

* * *

7\. 环境与配置
---------

### 12 因子应用原则 (12-Factor App)

| 要素  | 应用方法 |
| --- | --- |
| 配置 (Config) | 使用环境变量 |
| 依赖 (Dependencies) | requirements.txt / package.json |
| 进程 (Processes) | 无状态应用 |
| 端口绑定 (Port binding) | 应用自行绑定端口 |
| 日志 (Logs) | 流式输出到标准输出 (stdout) |
| 环境等同性 | 使用 Docker |

### Pydantic Settings 配置

```
# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "Habit Tracker"
    database_url: str = "sqlite:///./habits.db"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### 环境文件

```
# .env.development
DATABASE_URL=sqlite:///./habits.db
DEBUG=true
CORS_ORIGINS=["http://localhost:5173"]

# .env.production
DATABASE_URL=sqlite:///./data/habits.db
DEBUG=false
CORS_ORIGINS=["https://yourdomain.com"]
```

### 密钥管理 (生产环境)

| 环境  | 解决方案 |
| --- | --- |
| 本地开发 | `.env` 文件 (加入 gitignore) |
| Docker | 环境变量 / Docker secrets |
| 云平台 | 平台自带的 Secrets (Railway, Fly.io) |
| 企业级 | HashiCorp Vault, AWS Secrets Manager |

* * *

8\. 生产环境数据库
-----------

### SQLite 注意事项

**何时可以使用 SQLite**：

*   单服务器部署
*   低并发写入
*   数据库体积 \< 1TB
*   本地/个人应用

**何时需要迁移到 PostgreSQL**：

*   多服务器/负载均衡
*   高并发写入
*   需要副本/高可用 (HA)

### 数据库文件位置

```
# 不要存储在应用目录下
# 错误做法
DATABASE_URL = "sqlite:///./habits.db"

# 正确做法 - 应用外部的绝对路径
DATABASE_URL = "sqlite:////var/data/habit-tracker/habits.db"
```

### Docker 卷持久化

```
# docker-compose.yml
services:
  backend:
    volumes:
      - db-data:/app/data

volumes:
  db-data:
```

### 使用 Litestream 备份

```
# litestream.yml
dbs:
  - path: /data/habits.db
    replicas:
      - url: s3://bucket-name/habits
        sync-interval: 1s
        retention: 24h
```

```
# 运行 litestream
litestream replicate -config litestream.yml
```

### 手动备份

```
# 使用 SQLite CLI 进行安全备份
sqlite3 /data/habits.db "VACUUM INTO '/backups/habits-$(date +%Y%m%d).db'"

# 或使用 Python 脚本
python -c "import sqlite3; src=sqlite3.connect('/data/habits.db'); dst=sqlite3.connect('/backups/backup.db'); src.backup(dst)"
```

### 使用 Alembic 进行迁移

```
# 生成迁移脚本
alembic revision --autogenerate -m "Add description column"

# 应用迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

**生产部署流程：**

1.  创建备份
2.  执行迁移：`alembic upgrade head`
3.  启动应用
4.  验证健康检查

* * *

9\. 监控与日志
---------

### 结构化日志

```
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
        }
        return json.dumps(log_data)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
```

### 请求日志中间件

```
import time
import logging

logger = logging.getLogger(__name__)

@app.middleware("http")
async def log_requests(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    logger.info(
        f"{request.method} {request.url.path} "
        f"status={response.status_code} "
        f"duration={duration:.3f}s"
    )
    return response
```

### 健康检查接口

```
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/health/ready")
async def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not ready", "error": str(e)},
        )
```

### 监控技术栈 (可选)

| 工具  | 用途  |
| --- | --- |
| Prometheus | 指标收集 |
| Grafana | 可视化 |
| Sentry | 错误追踪 |
| Loki | 日志聚合 |

* * *

10\. 云平台
--------

### 平台对比

| 平台  | 计费方式 | 最适合 | SQLite 支持 |
| --- | --- | --- | --- |
| **Railway** | 按量计费 | 快速部署 | 有限  |
| **Render** | \$7+/月 | 托管服务 | 有限  |
| **Fly.io** | \$2+/月 | 全球分布, SQLite | 支持 (卷存储) |
| **DigitalOcean** | \$4+/月 | VPS 控制权 | 支持  |
| **Hetzner** | \$4+/月 | 欧洲地区, 预算有限 | 支持  |

### Fly.io 部署

```
# 安装 flyctl
curl -L https://fly.io/install.sh | sh

# 登录
fly auth login

# 启动应用
fly launch

# 部署
fly deploy

# 为 SQLite 创建卷
fly volumes create data --size 1

# 检查状态
fly status
```

**fly.toml:**

```
app = "habit-tracker"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8000
  force_https = true

[mounts]
  source = "data"
  destination = "/data"
```

### Railway 部署

```
# 安装 Railway CLI
npm install -g @railway/cli

# 登录
railway login

# 初始化
railway init

# 部署
railway up
```

### VPS 部署清单

1.  **服务器初始化**
    ```
    sudo apt update && sudo apt upgrade
    sudo apt install nginx python3-pip python3-venv
    ```
2.  **克隆仓库**
    ```
    git clone https://github.com/user/habit-tracker /var/www/habit-tracker
    ```
3.  **后端设置**
    ```
    cd /var/www/habit-tracker/backend
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
4.  **构建前端**
    ```
    cd /var/www/habit-tracker/frontend
    npm install && npm run build
    ```
5.  **配置 systemd 服务**
6.  **配置 Nginx**
7.  **使用 Certbot 设置 SSL**
8.  **配置防火墙**
    ```
    sudo ufw allow 80
    sudo ufw allow 443
    sudo ufw enable
    ```

* * *

11\. 安全
-------

### CORS 配置

```
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # 仅允许特定源
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

### 安全响应头 (Nginx)

```
# 添加到 server 块中
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;
```

### Docker 安全

```
# 以非 root 用户运行
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

# 使用具体版本号
FROM python:3.11.7-slim

# 不要在镜像中存储密钥
# 使用运行时的环境变量
```

### 全站 HTTPS

*   使用 Let's Encrypt 获取免费 SSL 证书
*   将 HTTP 重定向到 HTTPS
*   启用 HSTS
    
```
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

### 环境安全

```
# 永远不要提交 .env 文件
echo ".env" >> .gitignore
echo ".env.*" >> .gitignore

# 设置严格的权限
chmod 600 .env
```

* * *

12\. 单个二进制文件部署
--------------

### PyInstaller

```
pip install pyinstaller

# 创建 spec 文件
pyi-makespec --onefile --name habittracker backend/app/main.py
```

**entrypoint.py:**

```
import multiprocessing
import uvicorn

if __name__ == "__main__":
    multiprocessing.freeze_support()  # Windows 环境必须
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
```

**构建：**

```
pyinstaller --onefile --add-data "frontend/dist:frontend/dist" entrypoint.py
```

### Tauri (桌面应用)

作为原生桌面端包装：

```
# 安装 Tauri CLI
cargo install tauri-cli

# 初始化
cargo tauri init

# 构建
cargo tauri build
```

**优点**：

*   原生 WebView (不捆绑浏览器)
*   二进制体积小 (~10-50MB)
*   跨平台支持

* * *

部署场景
----

### 场景 1：本地/个人使用

```
┌─────────────────────────────────┐
│  uvicorn + 嵌入式 React         │
│  SQLite 文件位于 ./data         │
└─────────────────────────────────┘
```

**命令：**

```
cd backend && uvicorn app.main:app --port 8000
# 访问地址 http://localhost:8000
```

### 场景 2：自托管 VPS

```
┌──────────┐      ┌──────────┐      ┌──────────┐
│  Nginx   │──────│  FastAPI │──────│  SQLite  │
│  (SSL)   │      │ (systemd)│      │  (文件)  │
└──────────┘      └──────────┘      └──────────┘
```

**成本**：约 \$4-5/月

### 场景 3：Docker Compose

```
┌──────────────────────────────────────────┐
│  docker-compose                          │
│  ┌────────────┐    ┌────────────┐        │
│  │  前端      │    │  后端      │        │
│  │  (nginx)   │────│  (uvicorn) │        │
│  └────────────┘    └─────┬──────┘        │
│                          │               │
│                    ┌─────▼──────┐        │
│                    │   数据卷   │        │
│                    │  (sqlite)  │        │
│                    └────────────┘        │
└──────────────────────────────────────────┘
```

### 场景 4：云端 PaaS (Fly.io)

```
┌──────────────────────────────────────────┐
│  Fly.io                                  │
│  ┌────────────────────────┐              │
│  │  Docker 容器           │              │
│  │  FastAPI + React       │              │
│  └───────────┬────────────┘              │
│              │                           │
│        ┌─────▼─────┐                     │
│        │   数据卷  │                     │
│        │  (SQLite) │                     │
│        └───────────┘                     │
└──────────────────────────────────────────┘
```

**成本**：约 \$2-5/月

* * *

快速参考
----

### 常用命令

```
# 开发环境
uvicorn app.main:app --reload
npm run dev

# 生产构建
npm run build
pip install -r requirements.txt

# Docker
docker-compose up --build
docker-compose logs -f

# 部署
fly deploy
railway up

# SSL
sudo certbot --nginx -d yourdomain.com

# 数据库备份
sqlite3 db.db "VACUUM INTO 'backup.db'"
```

### 端口参考

| 服务  | 默认端口 |
| --- | --- |
| Vite 开发服务器 | 5173 |
| FastAPI/Uvicorn | 8000 |
| Nginx HTTP | 80  |
| Nginx HTTPS | 443 |
| PostgreSQL | 5432 |

* * *

相关资源
----

*   [FastAPI 部署文档](https://fastapi.tiangolo.com/deployment/)
*   [Vite 静态部署指南](https://vitejs.dev/guide/static-deploy.html)
*   [Docker 官方文档](https://docs.docker.com/)
*   [Nginx 官方文档](https://nginx.org/en/docs/)
*   [Let's Encrypt](https://letsencrypt.org/)
*   [Fly.io 文档](https://fly.io/docs/)
*   [Litestream](https://litestream.io/)



