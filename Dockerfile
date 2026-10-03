# Exact runtime versions; update deliberately after Linux build verification.
ARG NODE_IMAGE=node:24.11.0-bookworm-slim
ARG PYTHON_IMAGE=python:3.13.7-slim-bookworm
FROM ${NODE_IMAGE} AS globe-build
WORKDIR /build/holo-view-maker
COPY holo-view-maker/package.json holo-view-maker/package-lock.json ./
RUN npm ci
COPY holo-view-maker/ ./
ENV BASE_PATH=/globe/
RUN npm run build

FROM ${PYTHON_IMAGE} AS python-build
WORKDIR /build
# requirements-server.txt is maintained by the backend agent and must include
# the application requirements plus the PostgreSQL driver; missing file fails build.
COPY requirements.txt requirements-server.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements-server.txt \
    && /opt/venv/bin/pip check

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    CLOUD_MODE=true \
    PORT=10000 \
    GLOBE_URL=/globe \
    GATEWAY_SITE_DIR=/app/_site \
    GATEWAY_GLOBE_DIR=/app/_site/globe \
    GATEWAY_GLOBE_DATA_DIR=/app/_site/globe/data \
    THERMAL_DATA_DIR=/var/lib/thermal/data \
    THERMAL_OUTPUT_DIR=/var/lib/thermal/output \
    ALERT_AUTO_DISPATCH_CRITICAL=false \
    ALERT_AUTO_ESCALATE_CALL=false
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 thermal \
    && useradd --uid 10001 --gid thermal --create-home thermal
COPY --from=python-build /opt/venv /opt/venv
COPY --chown=thermal:thermal app.py config.py start_all.py cloud_launcher.py ./
COPY --chown=thermal:thermal gateway/ gateway/
COPY --chown=thermal:thermal src/ src/
COPY --chown=thermal:thermal scripts/ scripts/
COPY --chown=thermal:thermal site/ site/
COPY --chown=thermal:thermal data/reference/ data/reference/
COPY --chown=thermal:thermal models/classifier.pkl models/classifier.pkl
COPY --from=globe-build --chown=thermal:thermal /build/holo-view-maker/.output/public/ holo-view-maker/.output/public/
RUN python scripts/assemble_pages_site.py --out /app/_site \
    && chown -R thermal:thermal /app/_site \
    && mkdir -p /var/lib/thermal/data /var/lib/thermal/output \
    && chown -R thermal:thermal /var/lib/thermal
USER thermal
EXPOSE 10000
STOPSIGNAL SIGTERM
CMD ["python", "cloud_launcher.py"]
