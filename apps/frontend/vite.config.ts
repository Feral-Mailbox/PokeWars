import { defineConfig } from 'vite';
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import type { InlineConfig } from 'vitest';
import type { Plugin } from 'vite';

dotenv.config();

const isDev = process.env.NODE_ENV === 'development';
let httpsConfig: any = false;

if (isDev) {
  const keyPath = path.resolve(__dirname, 'certs/privkey.pem');
  const certPath = path.resolve(__dirname, 'certs/fullchain.pem');

  if (fs.existsSync(keyPath) && fs.existsSync(certPath)) {
    try {
      httpsConfig = {
        key: fs.readFileSync(keyPath),
        cert: fs.readFileSync(certPath),
      };
    } catch (e: unknown) {
      console.warn('⚠️ Failed to read HTTPS cert files:', (e as Error).message);
    }
  } else {
    console.warn('⚠️ HTTPS certs not found, skipping HTTPS config');
  }
}

const assetsRoot = path.resolve(__dirname, '../../assets');

function serveGameAssets(): Plugin {
  return {
    name: 'serve-game-assets',
    configureServer(server) {
      server.middlewares.use('/game-assets', (req, res, next) => {
        const urlPath = decodeURIComponent(req.url ?? '/');
        const relativePath = urlPath.replace(/^\/+/, '');
        const filePath = path.join(assetsRoot, relativePath);
        if (!filePath.startsWith(assetsRoot)) {
          res.statusCode = 403;
          res.end('Forbidden');
          return;
        }
        fs.readFile(filePath, (err, data) => {
          if (err) {
            next();
            return;
          }
          if (filePath.endsWith('.json')) {
            res.setHeader('Content-Type', 'application/json');
          } else if (filePath.endsWith('.png')) {
            res.setHeader('Content-Type', 'image/png');
          }
          res.setHeader('Access-Control-Allow-Origin', '*');
          res.end(data);
        });
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), serveGameAssets()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './tests/setup.ts',
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"], // text summary and lcov for CI tools
    },
  } as InlineConfig,
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    https: httpsConfig,
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
