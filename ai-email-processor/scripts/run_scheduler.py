# scripts/run_scheduler.py
"""スケジューラーの実行スクリプト"""

import sys
import os
import asyncio
import logging
import signal

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.scheduler import EmailScheduler
from src.config import Config

# ロギング設定
logging.basicConfig(
    level=getattr(logging, Config.LOGGING["level"]),
    format=Config.LOGGING["format"],
    handlers=[
        logging.FileHandler(
            os.path.join(
                os.path.dirname(__file__), "..", "logs", Config.LOGGING["file"]
            )
        ),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

scheduler = None


def signal_handler(sig, frame):
    """シグナルハンドラー"""
    logger.info("Received interrupt signal. Shutting down...")
    if scheduler:
        scheduler.stop()
    sys.exit(0)


if __name__ == "__main__":
    # 設定の検証
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # シグナルハンドラーの設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # スケジューラーの起動
    scheduler = EmailScheduler(
        interval_minutes=Config.EMAIL_PROCESSING["interval_minutes"]
    )

    logger.info("Starting email processing scheduler...")

    try:
        # イベントループを作成して実行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        scheduler.start()
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        sys.exit(1)
