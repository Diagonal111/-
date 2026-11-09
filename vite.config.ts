import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: { manualChunks: { content: ['katex', 'rehype-katex', 'react-markdown', 'remark-math'] } },
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8765',
      '/attachments': 'http://127.0.0.1:8765',
    },
  },
})
