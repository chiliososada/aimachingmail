# scripts/run_scheduler.py
"""更新的调度器运行脚本 - 重构版本"""

import sys
import os
import asyncio
import logging
import signal

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.scheduler import EmailScheduler
from src.config import Config

# 日志设置
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
    """信号处理器"""
    logger.info("Received interrupt signal. Shutting down...")
    if scheduler:
        scheduler.stop()
    sys.exit(0)


if __name__ == "__main__":
    # 配置验证
    try:
        Config.validate()
        logger.info("✅ Configuration validation passed")
    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        sys.exit(1)

    # 打印配置信息
    Config.print_ai_service_mapping_info()

    # 信号处理器设置
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 调度器启动
    scheduler = EmailScheduler(
        interval_minutes=Config.EMAIL_PROCESSING["interval_minutes"]
    )

    logger.info("Starting email processing scheduler...")

    try:
        # 创建并运行事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(scheduler.start_async())
    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user.")
        if scheduler:
            scheduler.stop()
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        sys.exit(1)
    finally:
        logger.info("Scheduler finished.")
