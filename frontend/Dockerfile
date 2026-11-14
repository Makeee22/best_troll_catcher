# The dashboard: static files behind nginx, which also proxies /api/ and /health
# to the "api" service of docker-compose.yml. Build context: frontend/
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY site /usr/share/nginx/html
COPY mock/samples /usr/share/nginx/html/samples
EXPOSE 80
