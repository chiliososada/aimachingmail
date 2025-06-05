# ====================
# 6. 测试脚本
# scripts/test_no_auth_api.py
# ====================

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.no_auth_processor import NoAuthCustomAPIProcessor


async def test_no_auth_api():
    """测试无认证自定义API"""
    # 配置你的无认证API端点
    api_base_url = "http://hpe1.toyousoft.co.jp:45678"  # 替换为你的API地址

    processor = NoAuthCustomAPIProcessor(
        api_base_url=api_base_url, default_model="", timeout=30.0  # 无模型名
    )

    print("🔧 测试无认证自定义API连接...")

    # 测试连接
    if await processor.test_connection():
        print("✅ API连接成功")

        # 测试邮件分类
        test_email = {
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
        }

        category = await processor.classify_email(test_email)
        print(f"✅ 邮件分类结果: {category}")

        #     # 测试数据提取
        if category == "project_related":
            project_data = await processor.extract_structured_data(
                test_email, "project"
            )
            if project_data:
                print(f"✅ 项目数据提取成功: {project_data}")
    else:
        print("❌ API连接失败")


if __name__ == "__main__":
    asyncio.run(test_no_auth_api())
