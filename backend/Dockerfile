FROM python:3.12-slim

WORKDIR /app

# Долгие загрузки torch/моделей: большой таймаут и явный progress-bar, чтобы сборка не обрывалась по таймауту и было видно движение.
ENV PIP_DEFAULT_TIMEOUT=600 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install --progress-bar on --default-timeout=600 -r requirements.txt

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

COPY . .

ENTRYPOINT ["/docker-entrypoint.sh"]
