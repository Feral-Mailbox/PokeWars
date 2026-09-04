# Production Dockerfile - Build static files and serve with nginx
FROM node:20-alpine AS builder

WORKDIR /app

# Pin pnpm major so install behavior stays predictable in CI/Docker
RUN npm install -g pnpm@10

COPY package.json pnpm-lock.yaml ./
# Lockfile can lag package.json on this repo; still allow vite/esbuild native builds
# via package.json "pnpm.onlyBuiltDependencies".
RUN pnpm install --no-frozen-lockfile

COPY . .

RUN pnpm run build

# Serve with nginx
FROM nginx:stable

# Copy built files to nginx
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
