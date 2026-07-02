# 前端在宿主机 npm run build 完成后，直接将 dist/ 打入 nginx 镜像
# 避免依赖 node:20-alpine（内网无法拉取）
FROM nginx:alpine
# 应用统一挂在 /chuilei/eval/ 下，dist 放到对应子目录
COPY dist /usr/share/nginx/html/chuilei/eval
# 注意：构建上下文是 frontend/，故此处 COPY 的是 frontend/nginx.conf（唯一来源）
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
