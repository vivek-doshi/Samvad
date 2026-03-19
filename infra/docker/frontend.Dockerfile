# Frontend Dockerfile — builds and serves the Angular application
# Note 1: Angular applications need a two-stage build:
# 1. Build stage: uses a Node.js image to run 'ng build --configuration production'
#    which compiles TypeScript, bundles JavaScript, and generates static HTML/CSS/JS
#    output in the dist/ directory.
# 2. Serve stage: uses a lightweight Nginx image to serve the static files.
#    A Node.js process is not needed at runtime — Angular apps are pure static files.
#
# Note 2: Typical multi-stage Dockerfile:
#
# --- Stage 1: Angular build ---
# FROM node:22-alpine AS builder
# WORKDIR /app
# COPY frontend/package*.json ./
# RUN npm ci                          # clean install from package-lock.json
# COPY frontend/ .
# RUN npm run build -- --configuration production
#
# --- Stage 2: Nginx serve ---
# FROM nginx:alpine
# COPY --from=builder /app/dist/frontend/browser /usr/share/nginx/html
# COPY infra/nginx/nginx.conf /etc/nginx/conf.d/default.conf
# EXPOSE 80
# CMD ["nginx", "-g", "daemon off;"]
#
# Note 3: 'npm ci' (clean install) is preferred over 'npm install' in Docker
# because it installs exactly the versions in package-lock.json — reproducible
# builds. 'npm install' may update patch versions, causing subtle differences.
#
# Note 4: 'daemon off' in the Nginx CMD keeps the Nginx process in the
# foreground. Docker requires the process to stay in the foreground to monitor
# its health — background processes cause the container to exit immediately.
#
# TODO: Add Angular build and nginx serve steps
