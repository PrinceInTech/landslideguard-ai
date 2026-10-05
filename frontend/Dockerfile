# LandslideGuard AI - frontend image (build Vite bundle, serve with nginx)

FROM node:20-alpine AS build
WORKDIR /app

# Install from the lockfile for reproducible builds.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# VITE_API_URL is inlined at BUILD time, so it must be an --build-arg and not a
# runtime environment variable. Leaving it empty makes the bundle call
# same-origin relative URLs ("/api/..."), which nginx proxies to the backend.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]