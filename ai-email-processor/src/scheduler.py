# src/scheduler.py
import asyncio
from datetime import datetime
import logging
from typing import Optional

# 相対インポート
from .email_processor import EmailProcessor, main as process_emails

logger = logging.getLogger(__name__)


class EmailScheduler:
    """メール処理のスケジューラー"""

    def __init__(self, interval_minutes: int = 10):
        self.interval_minutes = interval_minutes
        self.is_running = False

    async def run_job(self):
        """ジョブを実行"""
        logger.info(f"Starting email processing job at {datetime.now()}")
        try:
            await process_emails()
            logger.info("Email processing job completed successfully")
        except Exception as e:
            logger.error(f"Error in email processing job: {e}")

    async def start_async(self):
        """スケジューラーを開始 (非同期)"""
        self.is_running = True
        logger.info(
            f"Email scheduler started. Running every {self.interval_minutes} minutes."
        )

        # 最初の実行
        await self.run_job()

        # スケジュールループ
        while self.is_running:
            await asyncio.sleep(self.interval_minutes * 60)
            if self.is_running: # 再度確認 (stopが呼ばれた場合のため)
                await self.run_job()

    def stop(self):
        """スケジューラーを停止"""
        self.is_running = False
        logger.info("Email scheduler stopping...")
