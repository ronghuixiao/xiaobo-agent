# 小柏 Agent - 多阶段构建 Dockerfile
# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装构建依赖
RUN pip install --no-cache-dir hatchling

# 复制项目文件
COPY pyproject.toml README.md ./
COPY src/ src/
COPY config/ config/

# 安装项目依赖
RUN pip install --no-cache-dir -e ".[all]"

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

# 从 builder 复制已安装的依赖
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# 创建数据目录
RUN mkdir -p /root/.xiaobo-agent

# 暴露端口
EXPOSE 8088

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8088/api/health'); assert r.status_code == 200"

# 启动命令
CMD ["python", "main.py", "--daemon"]
