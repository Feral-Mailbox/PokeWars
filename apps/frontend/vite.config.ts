import { defineConfig } from 'vite';
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';

dotenv.config();

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
    host: true,
    port: 5173,
    strictPort: true,
    https: false,
    allowedHosts: ['poketactics.net', 'www.poketactics.net'],
    watch: {
      usePolling: true, // 🔥 Windows + WSL fix
    },
    hmr: {
      protocol: 'wss',
      host: 'poketactics.net',
      port: 443,
    },
    cors: {
      origin: ['https://poketactics.net', 'https://www.poketactics.net'],
      credentials: true,
    },
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
        secure: false,
        rewrite: path => path.replace(/^\/api/, ''),
        cookieDomainRewrite: 'poketactics.net', 
      },
    },
  },
  css: {
    postcss: './postcss.config.js',
  },
});
