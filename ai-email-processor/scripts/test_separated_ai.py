# test_separated_ai.py
"""分离式AI配置测试脚本"""

import asyncio
import logging
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.abspath("."))

from src.config import Config
from src.email_classifier import EmailClassifier
from src.email_processor import EmailProcessor

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 测试邮件数据
TEST_EMAILS = [
    {
        "subject": "Java開発エンジニア ご紹介",
        "body_text": """
        お疲れ様です。
        
        下記の要員についてご紹介させていただきます。
        
        【氏名】: 田中太郎
        【年齢】: 28歳
        【性別】: 男性
        【最寄駅】: 新宿駅
        【実務経験】: Java 5年、Spring Boot 3年
        【日本語】: ビジネスレベル
        【単価】: 60-70万円/月
        【稼働日】: 即日可能
        
        履歴書を添付いたします。
        ご検討のほどよろしくお願いいたします。
        """,
        "sender_email": "recruiter@example.com",
        "sender_name": "採用担当",
        "attachments": [],
        "expected_type": "engineer_related",
    },
    {
        "subject": "新規Java開発案件のご紹介",
        "body_text": """
        お疲れ様です。
        
        下記案件についてご紹介いたします。
        
        【案件名】: ECサイトリニューアル
        【クライアント】: 大手小売業
        【必須スキル】: Java, Spring Boot, MySQL
        【勤務地】: 東京都港区
        【期間】: 2024年7月〜2025年3月
        【単価】: 70-80万円/月
        【面談回数】: 1回
        
        ご興味がございましたらご連絡ください。
        """,
        "sender_email": "sales@agency.com",
        "sender_name": "営業担当",
        "attachments": [],
        "expected_type": "project_related",
    },
]


async def test_classification_service():
    """测试邮件分类服务"""
    print("\n" + "=" * 60)
    print("🔍 测试邮件分类服务")
    print("=" * 60)

    try:
        # 获取分类服务配置
        classification_config = Config.get_ai_config_for_service("classification")
        print(f"分类服务提供商: {classification_config.get('provider_name')}")

        # 初始化分类器
        classifier = EmailClassifier(classification_config)

        for i, email_data in enumerate(TEST_EMAILS, 1):
            print(f"\n📧 测试邮件 {i}:")
            print(f"  件名: {email_data['subject']}")
            print(f"  期待分类: {email_data['expected_type']}")

            # 执行分类
            result = await classifier.classify_email(email_data)

            print(f"  实际分类: {result.value}")

            if result.value == email_data["expected_type"]:
                print("  ✅ 分类正确")
            else:
                print("  ❌ 分类错误")

    except Exception as e:
        print(f"❌ 分类服务测试失败: {e}")


async def test_extraction_service():
    """测试数据提取服务"""
    print("\n" + "=" * 60)
    print("📊 测试数据提取服务")
    print("=" * 60)

    try:
        # 获取提取服务配置
        extraction_config = Config.get_ai_config_for_service("extraction")
        print(f"提取服务提供商: {extraction_config.get('provider_name')}")

        # 初始化邮件处理器（仅用于测试提取功能）
        processor = EmailProcessor(db_config=Config.get_db_config())

        # 测试工程师信息提取
        engineer_email = TEST_EMAILS[0]
        print(f"\n👨‍💻 测试工程师信息提取:")
        print(f"  件名: {engineer_email['subject']}")

        engineer_data = await processor.extract_engineer_info(engineer_email)

        if engineer_data:
            print(f"  ✅ 提取成功:")
            print(f"    姓名: {engineer_data.name}")
            print(f"    年龄: {engineer_data.age}")
            print(f"    性别: {engineer_data.gender}")
            print(f"    技能: {engineer_data.skills}")
            print(f"    日语水平: {engineer_data.japanese_level}")
        else:
            print("  ❌ 提取失败")

        # 测试项目信息提取
        project_email = TEST_EMAILS[1]
        print(f"\n📋 测试项目信息提取:")
        print(f"  件名: {project_email['subject']}")

        project_data = await processor.extract_project_info(project_email)

        if project_data:
            print(f"  ✅ 提取成功:")
            print(f"    项目名: {project_data.title}")
            print(f"    客户: {project_data.client_company}")
            print(f"    技能: {project_data.skills}")
            print(f"    地点: {project_data.location}")
            print(f"    开始日期: {project_data.start_date}")
        else:
            print("  ❌ 提取失败")

        await processor.close()

    except Exception as e:
        print(f"❌ 提取服务测试失败: {e}")


async def test_fallback_mechanism():
    """测试fallback机制"""
    print("\n" + "=" * 60)
    print("🔄 测试Fallback机制")
    print("=" * 60)

    try:
        # 获取主要和备用配置
        primary_config = Config.get_ai_config_for_service("classification")
        fallback_config = Config.get_ai_config_for_service(
            "classification", use_fallback=True
        )

        print(f"主要分类提供商: {primary_config.get('provider_name')}")
        print(f"备用分类提供商: {fallback_config.get('provider_name')}")

        primary_extraction = Config.get_ai_config_for_service("extraction")
        fallback_extraction = Config.get_ai_config_for_service(
            "extraction", use_fallback=True
        )

        print(f"主要提取提供商: {primary_extraction.get('provider_name')}")
        print(f"备用提取提供商: {fallback_extraction.get('provider_name')}")

        print("✅ Fallback配置正常")

    except Exception as e:
        print(f"❌ Fallback测试失败: {e}")


def test_config_validation():
    """测试配置验证"""
    print("\n" + "=" * 60)
    print("⚙️ 测试配置验证")
    print("=" * 60)

    try:
        Config.validate()
        print("✅ 配置验证通过")

        # 打印配置信息
        Config.print_ai_service_mapping_info()

    except Exception as e:
        print(f"❌ 配置验证失败: {e}")


async def main():
    """主测试函数"""
    print("🚀 分离式AI配置测试开始")
    print("=" * 60)

    # 1. 配置验证
    test_config_validation()

    # 2. 测试分类服务
    await test_classification_service()

    # 3. 测试提取服务
    await test_extraction_service()

    # 4. 测试fallback机制
    await test_fallback_mechanism()

    print("\n" + "=" * 60)
    print("🎉 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
