FROM python:3.14-slim AS packages
COPY . /usr/local/src/gramfood-api

RUN useradd --create-home --gid www-data gramfood-api; \
    pip install --no-cache-dir --editable /usr/local/src/gramfood-api; \
    chown gramfood-api:www-data /usr/local/src/gramfood-api/config.toml;

USER gramfood-api
WORKDIR /usr/local/src/gramfood-api
ENTRYPOINT ["python", "-m", "gramfood_api"]
