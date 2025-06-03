# scripts/test_custom_api.py
"""测试自定义API配置的脚本"""

import sys
import os
import asyncio
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import Config
from src.email_classifier import EmailClassifier
from src.email_processor import EmailProcessor
from src.attachment_processor import AttachmentProcessor
from src.custom_processor import CustomAPIProcessor

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_custom_api_configuration():
    """测试自定义API配置"""
    print("🔧 测试自定义API配置")
    print("=" * 50)

    # 1. 验证配置
    try:
        Config.validate()
        print("✅ 配置验证通过")
    except Exception as e:
        print(f"❌ 配置验证失败: {e}")
        return False

    # 2. 获取AI配置
    ai_config = Config.get_ai_config()
    provider_name = ai_config.get("provider_name")

    print(f"📋 当前AI提供商: {provider_name}")
    print(f"📋 API Base URL: {ai_config.get('api_base_url', 'N/A')}")
    print(f"📋 分类模型: {ai_config.get('model_classify')}")
    print(f"📋 提取模型: {ai_config.get('model_extract')}")

    if provider_name != "custom":
        print(f"⚠️  当前提供商不是 'custom'，而是 '{provider_name}'")
        print("如果要测试自定义API，请在 .env 文件中设置 DEFAULT_AI_PROVIDER=custom")
        return False

    # 3. 测试自定义API连接
    api_key = ai_config.get("api_key")
    api_base_url = ai_config.get("api_base_url")

    if not api_key or not api_base_url:
        print("❌ 自定义API密钥或URL未配置")
        return False

    print(f"\n🔌 测试自定义API连接...")
    processor = CustomAPIProcessor(api_key, api_base_url)

    connection_ok = await processor.test_connection()
    if connection_ok:
        print("✅ 自定义API连接成功")
    else:
        print("❌ 自定义API连接失败")
        return False

    return True


async def test_email_classification_with_custom_api():
    """使用自定义API测试邮件分类"""
    print("\n📧 测试邮件分类功能")
    print("-" * 30)

    ai_config = Config.get_ai_config()
    classifier = EmailClassifier(ai_config)

    # 测试邮件
    test_emails = [
        {
            "subject": "Java开发案件のご紹介",
            "body_text": """
            お世話になっております。
            
            下記の案件についてご紹介させていただきます。
            
            【案件概要】
            ・案件名：金融系システムのJava開発
            ・必須スキル：Java, Spring Boot, MySQL
            ・期間：2024年6月〜長期
            ・場所：東京都港区
            ・単価：70-80万円/月
            
            ご興味がございましたら、ご連絡ください。
            """,
            "sender_email": "agent@example.com",
            "attachments": [],
        },
        {
            "subject": "エンジニアのご紹介",
            "body_text": """
            お世話になっております。
            
            弊社エンジニアをご紹介させていただきます。
            
            【エンジニア情報】
            ・氏名：山田太郎
            ・経験年数：Java 5年、Python 3年
            ・希望単価：60-70万円
            ・日本語：ネイティブレベル
            
            詳細な経歴書を添付いたします。
            """,
            "sender_email": "hr@company.com",
            "attachments": [],
        },
    ]

    for i, email_data in enumerate(test_emails, 1):
        print(f"\n📨 测试邮件 {i}: {email_data['subject']}")

        try:
            email_type = await classifier.classify_email(email_data)
            print(f"✅ 分类结果: {email_type.value}")
        except Exception as e:
            print(f"❌ 分类失败: {e}")


async def test_data_extraction_with_custom_api():
    """使用自定义API测试数据提取"""
    print("\n🔍 测试数据提取功能")
    print("-" * 30)

    ai_config = Config.get_ai_config()
    processor = EmailProcessor(db_config=Config.get_db_config(), ai_config=ai_config)

    # 测试项目信息提取
    project_email = {
        "subject": "Python开发案件",
        "body_text": """
        【案件詳細】
        案件名：ECサイトのバックエンド開発
        クライアント：某大手EC企業
        
        必要スキル：
        - Python (Django/FastAPI)
        - PostgreSQL
        - AWS
        - Docker
        
        期間：2024年7月〜2025年3月
        場所：リモート可（月1-2回出社）
        単価：65万円〜75万円
        
        日本語：ビジネスレベル以上
        """,
    }

    print("📋 测试项目信息提取...")
    try:
        project_data = await processor.extract_project_info(project_email)
        if project_data:
            print("✅ 项目信息提取成功")
            print(f"   项目名称: {project_data.title}")
            print(f"   技能要求: {project_data.skills[:3]}")
            print(f"   工作地点: {project_data.location}")
        else:
            print("❌ 项目信息提取失败")
    except Exception as e:
        print(f"❌ 项目信息提取异常: {e}")

    # 测试工程师信息提取
    engineer_email = {
        "subject": "技術者ご紹介",
        "body_text": """
        【技術者情報】
        氏名：田中花子
        年齢：28歳
        性別：女性
        経験：Java 6年、React 3年
        日本語：ビジネスレベル
        希望単価：55万円〜65万円
        稼働：即日可能
        """,
    }

    print("\n👨‍💻 测试工程师信息提取...")
    try:
        engineer_data = await processor.extract_engineer_info(engineer_email)
        if engineer_data:
            print("✅ 工程师信息提取成功")
            print(f"   姓名: {engineer_data.name}")
            print(f"   年龄: {engineer_data.age}")
            print(f"   技能: {engineer_data.skills[:3]}")
            print(f"   日语水平: {engineer_data.japanese_level}")
        else:
            print("❌ 工程师信息提取失败")
    except Exception as e:
        print(f"❌ 工程师信息提取异常: {e}")


async def test_attachment_processing_with_custom_api():
    """使用自定义API测试附件处理"""
    print("\n📎 测试附件处理功能")
    print("-" * 30)

    ai_config = Config.get_ai_config()
    attachment_processor = AttachmentProcessor(ai_config)

    # 模拟简历文本
    resume_text = """
    履歴書

    氏名: 佐藤次郎
    年齢: 30歳
    性別: 男性
    最寄駅: 新宿駅

    【職歴】
    2020年4月 - 現在: ABC株式会社
    - Java, Spring Bootを使用したWebアプリケーション開発
    - PostgreSQL, MySQLでのデータベース設計・運用
    - AWS EC2, RDSでのインフラ構築

    【スキル】
    - Java (5年)
    - Python (2年)
    - Spring Boot
    - React
    - AWS

    【資格】
    - Java Silver
    - AWS Solutions Architect Associate

    【希望条件】
    - 希望単価: 60万円〜70万円
    - リモートワーク希望
    - 残業: 月20時間以内
    """

    print("📄 测试简历数据提取...")
    try:
        resume_data = await attachment_processor.extract_resume_data_with_ai(
            resume_text, "佐藤次郎_履歴書.docx"
        )
        if resume_data:
            print("✅ 简历数据提取成功")
            print(f"   姓名: {resume_data.name}")
            print(f"   年龄: {resume_data.age}")
            print(f"   技能: {resume_data.skills[:3]}")
            print(
                f"   希望单价: {resume_data.desired_rate_min}-{resume_data.desired_rate_max}万円"
            )
        else:
            print("❌ 简历数据提取失败")
    except Exception as e:
        print(f"❌ 简历数据提取异常: {e}")


async def main():
    """主测试函数"""
    print("🚀 自定义API集成测试")
    print("=" * 60)

    # 1. 测试配置
    config_ok = await test_custom_api_configuration()
    if not config_ok:
        print("\n❌ 配置测试失败，停止后续测试")
        return

    # 2. 测试邮件分类
    await test_email_classification_with_custom_api()

    # 3. 测试数据提取
    await test_data_extraction_with_custom_api()

    # 4. 测试附件处理
    await test_attachment_processing_with_custom_api()

    print("\n" + "=" * 60)
    print("🎉 自定义API集成测试完成")
    print("\n📋 接下来你可以：")
    print("1. 运行完整的邮件处理: python scripts/run_scheduler.py")
    print("2. 运行邮件处理测试: python scripts/test_email_processor.py")
    print("3. 检查日志确认API调用情况")


if __name__ == "__main__":
    asyncio.run(main())
