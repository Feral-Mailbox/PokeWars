import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import dotenv from 'dotenv';
import path from 'path';
import fs from 'fs';

dotenv.config();

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    host: true,
    open: true,
    strictPort: true,
    watch: {
      usePolling: true, // 🔥 Windows + WSL fix
    },
    https: {
      key: fs.readFileSync(process.env.VITE_SSL_KEY_PATH!),
      cert: fs.readFileSync(process.env.VITE_SSL_CERT_PATH!),
    },
    hmr: {
      host: process.env.VITE_HOST || 'localhost',
      protocol: 'wss',
      port: Number(process.env.VITE_DEV_PORT) || 5173,
    },
    cors: {
      origin: 'http://localhost:8000',
      credentials: true,
    },
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://backend:8000',
        changeOrigin: true,
        secure: false,
        rewrite: path => path.replace(/^\/api/, ''),
        cookieDomainRewrite: process.env.VITE_HOST || 'localhost', 
      },
    },
  },
  css: {
    postcss: './postcss.config.js',
  },
});
