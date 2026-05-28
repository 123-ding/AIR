import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { resolve } from 'node:path'

function copyMxCadAssets() {
  return {
    name: 'copy-mxcad-assets',
    closeBundle() {
      const root = process.cwd()
      const dist = resolve(root, 'dist', 'mxcad')
      const source = resolve(root, 'node_modules', 'mxcad', 'dist')
      if (!existsSync(source)) return
      rmSync(dist, { recursive: true, force: true })
      mkdirSync(dist, { recursive: true })
      cpSync(resolve(source, 'wasm'), resolve(dist, 'wasm'), { recursive: true })
      cpSync(resolve(source, 'fonts'), resolve(dist, 'fonts'), { recursive: true })
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue(), copyMxCadAssets()],
  server: {
    port: 5173,
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
    proxy: {
      // 把后端 API 路径代理到 FastAPI（默认 8000）
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
