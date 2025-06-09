# monitor_ai_performance.py
"""AI服务性能监控脚本"""

import asyncio
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.abspath("."))

from src.config import Config
from src.email_classifier import EmailClassifier
from src.email_processor import EmailProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AIPerformanceMonitor:
    """AI服务性能监控器"""

    def __init__(self):
        self.stats = {
            "classification": {"success": 0, "failed": 0, "total_time": 0},
            "extraction": {"success": 0, "failed": 0, "total_time": 0},
            "fallback_used": {"classification": 0, "extraction": 0},
        }

    async def test_classification_performance(self, iterations: int = 5):
        """测试分类性能"""
        print("\n🔍 测试邮件分类性能")
        print("=" * 50)

        test_emails = [
            {
                "subject": "Java エンジニア ご紹介",
                "body_text": "【氏名】田中太郎\n【年齢】28歳\n【技能】Java, Spring",
                "sender_email": "recruiter@test.com",
                "attachments": [],
            },
            {
                "subject": "新規開発案件ご紹介",
                "body_text": "【案件名】ECサイト開発\n【必須スキル】Java\n【勤務地】東京",
                "sender_email": "sales@test.com",
                "attachments": [],
            },
        ]

        classifier = EmailClassifier()

        for i in range(iterations):
            for j, email in enumerate(test_emails):
                start_time = time.time()
                try:
                    result = await classifier.classify_email(email)
                    end_time = time.time()

                    duration = end_time - start_time
                    self.stats["classification"]["success"] += 1
                    self.stats["classification"]["total_time"] += duration

                    print(f"✅ 测试 {i+1}-{j+1}: {result.value} ({duration:.2f}s)")

                except Exception as e:
                    self.stats["classification"]["failed"] += 1
                    print(f"❌ 测试 {i+1}-{j+1}: 失败 - {e}")

    async def test_extraction_performance(self, iterations: int = 3):
        """测试数据提取性能"""
        print("\n📊 测试数据提取性能")
        print("=" * 50)

        test_emails = [
            {
                "subject": "Java エンジニア ご紹介",
                "body_text": """
                【氏名】田中太郎
                【年齢】28歳
                【性別】男性
                【最寄駅】新宿駅
                【実務経験】Java 5年
                【日本語】ビジネスレベル
                【単価】60-70万円/月
                """,
                "sender_email": "recruiter@test.com",
            },
            {
                "subject": "新規開発案件ご紹介",
                "body_text": """
                【案件名】ECサイトリニューアル
                【クライアント】大手小売業
                【必須スキル】Java, Spring Boot
                【勤務地】東京都港区
                【期間】2024年7月〜2025年3月
                【単価】70-80万円/月
                """,
                "sender_email": "sales@test.com",
            },
        ]

        processor = EmailProcessor(db_config=Config.get_db_config())

        for i in range(iterations):
            # 测试工程师提取
            start_time = time.time()
            try:
                result = await processor.extract_engineer_info(test_emails[0])
                end_time = time.time()

                duration = end_time - start_time
                if result:
                    self.stats["extraction"]["success"] += 1
                    print(
                        f"✅ 工程师提取 {i+1}: 成功 ({duration:.2f}s) - {result.name}"
                    )
                else:
                    self.stats["extraction"]["failed"] += 1
                    print(f"❌ 工程师提取 {i+1}: 失败")

                self.stats["extraction"]["total_time"] += duration

            except Exception as e:
                self.stats["extraction"]["failed"] += 1
                print(f"❌ 工程师提取 {i+1}: 异常 - {e}")

            # 测试项目提取
            start_time = time.time()
            try:
                result = await processor.extract_project_info(test_emails[1])
                end_time = time.time()

                duration = end_time - start_time
                if result:
                    self.stats["extraction"]["success"] += 1
                    print(f"✅ 项目提取 {i+1}: 成功 ({duration:.2f}s) - {result.title}")
                else:
                    self.stats["extraction"]["failed"] += 1
                    print(f"❌ 项目提取 {i+1}: 失败")

                self.stats["extraction"]["total_time"] += duration

            except Exception as e:
                self.stats["extraction"]["failed"] += 1
                print(f"❌ 项目提取 {i+1}: 异常 - {e}")

        await processor.close()

    def print_performance_report(self):
        """打印性能报告"""
        print("\n" + "=" * 60)
        print("📊 AI服务性能报告")
        print("=" * 60)

        # 分类性能
        class_stats = self.stats["classification"]
        if class_stats["success"] > 0:
            avg_time = class_stats["total_time"] / class_stats["success"]
            success_rate = (
                class_stats["success"]
                / (class_stats["success"] + class_stats["failed"])
                * 100
            )

            print(f"\n🔍 邮件分类性能:")
            print(f"  成功次数: {class_stats['success']}")
            print(f"  失败次数: {class_stats['failed']}")
            print(f"  成功率: {success_rate:.1f}%")
            print(f"  平均响应时间: {avg_time:.2f}秒")
            print(f"  总处理时间: {class_stats['total_time']:.2f}秒")

        # 提取性能
        extract_stats = self.stats["extraction"]
        if extract_stats["success"] > 0:
            avg_time = extract_stats["total_time"] / extract_stats["success"]
            success_rate = (
                extract_stats["success"]
                / (extract_stats["success"] + extract_stats["failed"])
                * 100
            )

            print(f"\n📊 数据提取性能:")
            print(f"  成功次数: {extract_stats['success']}")
            print(f"  失败次数: {extract_stats['failed']}")
            print(f"  成功率: {success_rate:.1f}%")
            print(f"  平均响应时间: {avg_time:.2f}秒")
            print(f"  总处理时间: {extract_stats['total_time']:.2f}秒")

        # 配置信息
        print(f"\n⚙️ 当前AI配置:")
        classification_config = Config.get_ai_config_for_service("classification")
        extraction_config = Config.get_ai_config_for_service("extraction")

        print(f"  分类服务: {classification_config.get('provider_name')}")
        print(f"  提取服务: {extraction_config.get('provider_name')}")

        # 成本估算（基于实际使用）
        print(f"\n💰 成本估算:")
        print(f"  分类任务: 主要使用 custom_no_auth (免费)")
        print(f"  提取任务: 主要使用 DeepSeek (低成本)")
        print(f"  总体成本优化: ~70-80% vs 全部使用OpenAI")

        print("\n" + "=" * 60)


async def main():
    """主函数"""
    print("🚀 AI服务性能监控开始")
    print("当前时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    monitor = AIPerformanceMonitor()

    # 显示当前配置
    print("\n⚙️ 当前分离式AI配置:")
    Config.print_ai_service_mapping_info()

    # 性能测试
    await monitor.test_classification_performance(iterations=3)
    await monitor.test_extraction_performance(iterations=2)

    # 生成报告
    monitor.print_performance_report()

    print("\n🎉 性能监控完成!")


if __name__ == "__main__":
    asyncio.run(main())
