#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

export WORKSPACE_DIR="$PROJECT_DIR/workspace"
export BACKEND_DATA_DIR="$PROJECT_DIR/backend/backend_data"

echo "========================================"
echo "  Score Platform 本地关闭"
echo "========================================"

docker compose -f "$PROJECT_DIR/deploy_docker/docker-compose.yml" down

echo ""
echo "✅ 所有容器已停止"
