# scripts/test_email_processor.py
"""メール処理のテストスクリプト"""

import sys
import os
import asyncio
import logging
from datetime import datetime

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.email_processor import (
    EmailProcessor,
    EmailType,
    ProjectStructured,
    EngineerStructured,
)
from src.config import Config

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def test_email_classification():
    """メール分類のテスト"""
    processor = EmailProcessor(Config.get_db_config(), Config.get_ai_config())
    await processor.initialize()

    test_emails = [
        {
            "subject": "Java開発案件のご紹介",
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
        },
    ]

    for email in test_emails:
        email_type = await processor.classify_email(email)
        logger.info(f"Subject: {email['subject']}")
        logger.info(f"Classification: {email_type}")
        print("-" * 50)

    await processor.close()


async def test_data_extraction():
    """データ抽出のテスト"""
    processor = EmailProcessor(Config.get_db_config(), Config.get_ai_config())
    await processor.initialize()

    project_email = {
        "subject": "Python開発案件",
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

    project_data = await processor.extract_project_info(project_email)
    if project_data:
        logger.info("Extracted project data:")
        logger.info(project_data.model_dump_json(indent=2))

    await processor.close()


if __name__ == "__main__":
    print("Running email processor tests...")
    asyncio.run(test_email_classification())
    print("\n" + "=" * 60 + "\n")
    asyncio.run(test_data_extraction())
