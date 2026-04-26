FROM node:20-alpine AS build

WORKDIR /frontend

COPY package.json tsconfig.json vite.config.ts index.html ./
COPY src ./src
COPY .env.example ./frontend.env.example
RUN npm install
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /frontend/dist /usr/share/nginx/html

EXPOSE 80
