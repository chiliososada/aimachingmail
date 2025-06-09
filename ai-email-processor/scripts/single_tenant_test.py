# scripts/single_tenant_test.py
"""单租户测试脚本 - 测试特定租户的邮件处理"""

import sys
import os
import asyncio
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.email_processor import EmailProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_single_tenant(tenant_id: str):
    """测试单个租户的邮件处理"""
    logger.info(f"Testing email processing for tenant: {tenant_id}")

    processor = EmailProcessor()

    try:
        await processor.initialize()

        # 处理指定租户的邮件
        results = await processor.process_tenant(tenant_id)

        logger.info(f"Processing completed for tenant {tenant_id}")
        logger.info(f"Total results: {len(results)}")

        # 统计结果
        from src.models.data_models import ProcessingStatus

        success_count = sum(
            1 for r in results if r.processing_status == ProcessingStatus.PROCESSED
        )
        error_count = sum(
            1 for r in results if r.processing_status == ProcessingStatus.ERROR
        )

        logger.info(f"Successful: {success_count}, Errors: {error_count}")

        return results

    except Exception as e:
        logger.error(f"Error processing tenant {tenant_id}: {e}")
        raise
    finally:
        await processor.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/single_tenant_test.py <tenant_id>")
        sys.exit(1)

    tenant_id = sys.argv[1]
    asyncio.run(test_single_tenant(tenant_id))
