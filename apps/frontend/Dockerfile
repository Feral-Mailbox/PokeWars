# Production Dockerfile - Build static files and serve with nginx
FROM node:20-alpine AS builder

WORKDIR /app

# Install pnpm
RUN npm install -g pnpm

COPY package.json ./
RUN pnpm install

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
