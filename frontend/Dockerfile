# Stage 1: Build the application
FROM node:24 AS builder

WORKDIR /app

# Copy package.json and install dependencies
# Using --legacy-peer-deps to ignore conflict between React 18 and MSAL v5 (which usually wants React 19)
COPY frontend/package.json ./
RUN npm install --legacy-peer-deps

# Copy the frontend source code
COPY frontend/ .

# Vite reads VITE_* vars from root .env (envDir: ".." in vite.config.ts).
# WORKDIR is /app, so envDir resolves to /. Place .env there at build time.
COPY .env /.env

# Çalışan sürüm — deploy.sh git SHA'sını geçer, lokal build'de "dev" kalır.
# Login rozeti bunu gösterir. Bilinçli olarak COPY'lerden SONRA: sürüm değişimi
# yalnız build katmanını yeniler, npm install cache'i korunur.
ARG APP_VERSION=dev
ENV VITE_APP_VERSION=$APP_VERSION

# Build the application
RUN npm run build

# Stage 2: Serve the application with Nginx
FROM nginx:alpine

# Copy the build output from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]
