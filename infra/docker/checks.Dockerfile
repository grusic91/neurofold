# Local Linux acceptance runner; no source, data or credentials are baked in.
FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM node:24-bookworm-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
RUN uv python install 3.12 3.13
WORKDIR /opt/browser-tools
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci && npm run test:browser:install -- --with-deps
RUN mkdir -p /work/neurofold && chown -R node:node /work
USER node
WORKDIR /work/neurofold
# Mount a source-only tar at /input/source.tar. Run the checked-in script below.
ENTRYPOINT ["/bin/sh", "-c", "tar -xf /input/source.tar -C /work/neurofold && exec sh infra/testing/linux_checks.sh \"$0\""]
