FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/math_graph_ai.db \
    DOCKER=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir -p /data

COPY app ./app
COPY run.py ./run.py

# 与本地约定一致：uvicorn 固定监听 6108（host 0.0.0.0 供 compose 网络访问）
EXPOSE 6108

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "6108"]
