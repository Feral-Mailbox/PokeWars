import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import dotenv from 'dotenv';

dotenv.config();

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: Number(process.env.VITE_DEV_PORT) || 5173,
    open: true,
    strictPort: true,
    watch: {
      usePolling: true, // 🔥 Windows + WSL fix
    },
    hmr: {
      host: process.env.VITE_HOST || 'localhost',
      protocol: 'ws',
      port: Number(process.env.VITE_DEV_PORT) || 5173,
    },
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://backend:8000',
        changeOrigin: true,
        secure: false,
        rewrite: path => path.replace(/^\/api/, ''),
      },
    },
  },
  css: {
    postcss: './postcss.config.js',
  },
});
