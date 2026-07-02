#!/bin/bash
set -e

echo "Building eval-frontend..."

docker build -t eval-frontend:latest .
docker save eval-frontend:latest | gzip > eval-frontend.tar.gz

echo "Build complete. Artifact: eval-frontend.tar.gz"
