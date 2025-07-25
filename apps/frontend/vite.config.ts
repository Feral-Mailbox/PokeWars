import { defineConfig } from 'vitest/config';
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';

dotenv.config();

let httpsConfig: undefined | { key: Buffer; cert: Buffer } = undefined;

const isDev = process.env.NODE_ENV === 'development';

if (isDev) {
  const keyPath = path.resolve(__dirname, 'certs/privkey.pem');
  const certPath = path.resolve(__dirname, 'certs/fullchain.pem');

  if (fs.existsSync(keyPath) && fs.existsSync(certPath)) {
    try {
      httpsConfig = {
        key: fs.readFileSync(keyPath),
        cert: fs.readFileSync(certPath),
      };
    } catch (e) {
      console.warn('⚠️ Failed to read HTTPS cert files:', e.message);
    }
  } else {
    console.warn('⚠️ HTTPS certs not found, skipping HTTPS config');
  }
}

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './tests/setup.ts',
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"], // text summary and lcov for CI tools
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
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
    https: httpsConfig,
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
      '/assets': {
        target: 'https://localhost', // Nginx https
        changeOrigin: true,
        secure: false,
      }
    },
  },
  css: {
    postcss: './postcss.config.js',
  },
});
