import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 整个应用统一挂载在 /chuilei/eval/ 命名空间下（私域部署：http://ip:host/chuilei/eval/xxx）。
// 这是唯一的前缀来源：Router basename / API_BASE / 登录跳转都从 import.meta.env.BASE_URL 派生。
const BASE = '/chuilei/eval/'

export default defineConfig({
  base: BASE,
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      [`${BASE}api/v1`]: {
        target: 'http://localhost:8080',
        changeOrigin: true,
        rewrite: (p) => p.replace('/chuilei/eval', ''),
      },
    },
  },
})
