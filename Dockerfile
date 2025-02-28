FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --without dev --no-root && \
    pip install alembic && \
    pip uninstall -y poetry

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令 - changed to run migrations before starting the app
CMD ["bash", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
