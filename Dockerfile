FROM python:3.11-slim-bookworm AS builder
WORKDIR /app

# 1) 写全新的源文件（用 https）＋ 关闭 pipeline ＋ 重试
RUN printf "deb https://deb.debian.org/debian          bookworm main\n\
deb https://deb.debian.org/debian          bookworm-updates main\n\
deb https://security.debian.org/debian-security bookworm-security main\n" \
      > /etc/apt/sources.list \
 && printf 'Acquire::http::Pipeline-Depth "0";\n\
Acquire::https::Pipeline-Depth "0";\n\
Acquire::Retries "5";\n' \
      > /etc/apt/apt.conf.d/99fix-broken-cdn

# 2) 系统依赖
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

# 3) Python 依赖
RUN pip install --no-cache-dir poetry==1.6.1
COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt -o requirements.txt --without-hashes

# ------------ 运行层 ------------
FROM python:3.11-slim-bookworm AS runtime
WORKDIR /app

# 用同样的 apt 配置（复制文件即可，也可再写一次，体积差不多）
COPY --from=builder /etc/apt/sources.list /etc/apt/sources.list
COPY --from=builder /etc/apt/apt.conf.d/99fix-broken-cdn /etc/apt/apt.conf.d/

COPY --from=builder /app/requirements.txt .
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir gunicorn

COPY . .
EXPOSE 8000
CMD ["gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]
