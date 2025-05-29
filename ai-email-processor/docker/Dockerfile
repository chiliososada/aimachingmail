# docker/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# システムの依存関係をインストール
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Pythonの依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY config/.env.example ./config/.env.example

# ログディレクトリの作成
RUN mkdir -p logs

# 非rootユーザーを作成
RUN useradd -m -u 1000 emailprocessor && \
    chown -R emailprocessor:emailprocessor /app

USER emailprocessor

# 環境変数の設定
ENV PYTHONPATH=/app

# スケジューラーを実行
CMD ["python", "scripts/run_scheduler.py"]