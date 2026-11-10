FROM node:24-bookworm-slim

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
COPY LICENSE /app/LICENSE
# Vite writes its dependency cache into node_modules during development.
RUN chown -R node:node /app/frontend

USER node
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
