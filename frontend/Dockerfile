# ── Stage 1: Build the React app ──────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
# Reproducible install from the lockfile; fall back to a fresh install if the
# lockfile is missing or out of sync.
RUN npm ci || npm install

COPY . .
RUN npm run build

# ── Stage 2: Serve with nginx ─────────────────────────────────────────────────
FROM nginx:alpine

# Replace default nginx config with our proxy config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built React app from Stage 1
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
