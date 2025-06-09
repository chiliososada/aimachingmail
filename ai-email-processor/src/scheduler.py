# src/scheduler.py
"""更新的邮件处理调度器 - 使用重构后的架构"""

import asyncio
from datetime import datetime
import logging
from typing import Optional

from src.email_processor import EmailProcessor
from src.config import Config

logger = logging.getLogger(__name__)


class EmailScheduler:
    """邮件处理调度器 - 重构版本"""

    def __init__(self, interval_minutes: int = 10):
        self.interval_minutes = interval_minutes
        self.is_running = False
        self.processor: Optional[EmailProcessor] = None

    async def run_job(self):
        """执行邮件处理任务"""
        logger.info(f"Starting email processing job at {datetime.now()}")

        try:
            if not self.processor:
                # 初始化处理器
                self.processor = EmailProcessor()
                await self.processor.initialize()

                # 测试配置
                config_ok = await self.processor.test_configuration()
                if not config_ok:
                    logger.error("Configuration test failed")
                    return

            # 执行邮件处理
            results = await self.processor.process_all_tenants()

            # 统计结果
            from src.models.data_models import ProcessingStatus

            success_count = sum(
                1 for r in results if r.processing_status == ProcessingStatus.PROCESSED
            )
            error_count = sum(
                1 for r in results if r.processing_status == ProcessingStatus.ERROR
            )

            logger.info(
                f"Email processing job completed: {success_count} successful, {error_count} errors"
            )

        except Exception as e:
            logger.error(f"Error in email processing job: {e}")

    async def start_async(self):
        """启动调度器（异步）"""
        self.is_running = True
        logger.info(
            f"Email scheduler started. Running every {self.interval_minutes} minutes."
        )

        try:
            # 初始执行
            await self.run_job()

            # 调度循环
            while self.is_running:
                await asyncio.sleep(self.interval_minutes * 60)
                if self.is_running:  # 再次确认（防止在睡眠期间被停止）
                    await self.run_job()

        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            raise
        finally:
            # 清理资源
            if self.processor:
                await self.processor.close()
                self.processor = None

    def stop(self):
        """停止调度器"""
        self.is_running = False
        logger.info("Email scheduler stopping...")


# 向后兼容的函数
async def main():
    """主函数 - 调用重构后的邮件处理器"""
    from src.email_processor import main as processor_main

    await processor_main()


if __name__ == "__main__":
    asyncio.run(main())
