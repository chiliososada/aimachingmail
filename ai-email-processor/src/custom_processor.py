# src/custom_processor.py
"""自定义API处理器"""

import httpx
from typing import Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)


class CustomAPIProcessor:
    """自定义API处理器"""

    def __init__(self, api_key: str, api_base_url: str, timeout: float = 120.0):
        self.api_key = api_key
        self.base_url = api_base_url
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def classify_email(
        self, email_data: Dict, model: str = "gpt-3.5-turbo"
    ) -> str:
        """使用自定义API进行邮件分类"""
        prompt = f"""
        以下のメールを分析して、カテゴリーを判定してください。
        
        件名: {email_data['subject']}
        本文: {email_data['body_text'][:1000]}
        
        カテゴリー:
        1. project_related - 案件に関するメール
        2. engineer_related - 技術者に関するメール
        3. other - その他の重要なメール
        4. unclassified - 分類不能または無関係なメール
        
        カテゴリー名のみを回答してください。
        """

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self.headers,
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "あなたはメール分類の専門家です。",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 50,
                    },
                )

                response.raise_for_status()
                data = response.json()

                category = data["choices"][0]["message"]["content"].strip().lower()

                if "project" in category:
                    return "project_related"
                elif "engineer" in category:
                    return "engineer_related"
                elif "other" in category:
                    return "other"
                else:
                    return "unclassified"

            except Exception as e:
                logger.error(f"Error with Custom API: {e}")
                return "unclassified"

    async def extract_structured_data(
        self, email_data: Dict, data_type: str, model: str = "gpt-4"
    ) -> Optional[Dict]:
        """使用自定义API提取结构化数据"""

        if data_type == "project":
            prompt = f"""
            以下のメールから案件情報を抽出してJSON形式で返してください。
            
            件名: {email_data['subject']}
            本文: {email_data['body_text']}
            
            以下の形式で抽出してください：
            {{
                "title": "案件タイトル",
                "client_company": "クライアント企業名",
                "description": "案件概要",
                "skills": ["必要スキル1", "必要スキル2"],
                "location": "勤務地",
                "start_date": "開始日 (YYYY-MM-DD形式)",
                "duration": "期間",
                "budget": "予算/単価",
                "japanese_level": "日本語レベル",
                "work_type": "勤務形態",
                "experience": "必要経験"
            }}
            """
        else:  # engineer
            prompt = f"""
            以下のメールから技術者情報を抽出してJSON形式で返してください。
            
            件名: {email_data['subject']}
            本文: {email_data['body_text']}
            
            以下の形式で抽出してください：
            {{
                "name": "技術者名",
                "email": "メールアドレス",
                "phone": "電話番号",
                "skills": ["スキル1", "スキル2"],
                "experience": "経験年数",
                "japanese_level": "日本語レベル",
                "work_experience": "職務経歴",
                "education": "学歴",
                "desired_rate_min": 希望単価下限,
                "desired_rate_max": 希望単価上限
            }}
            """

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self.headers,
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "あなたは情報抽出の専門家です。JSONのみを返してください。",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1000,
                    },
                )

                response.raise_for_status()
                data = response.json()

                content = data["choices"][0]["message"]["content"]
                # JSON部分を抽出
                json_start = content.find("{")
                json_end = content.rfind("}") + 1

                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    return json.loads(json_str)

            except Exception as e:
                logger.error(f"Error extracting data with Custom API: {e}")

        return None

    async def test_connection(self) -> bool:
        """测试API连接"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self.headers,
                    json={
                        "model": "gpt-3.5-turbo",
                        "messages": [
                            {
                                "role": "user",
                                "content": "Hello, this is a test message.",
                            }
                        ],
                        "max_tokens": 10,
                    },
                )
                response.raise_for_status()
                logger.info("Custom API connection test successful")
                return True

            except Exception as e:
                logger.error(f"Custom API connection test failed: {e}")
                return False


# 使用示例
async def test_custom_api():
    """测试自定义API"""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("CUSTOM_API_KEY")
    api_base_url = os.getenv("CUSTOM_API_BASE_URL")

    if not api_key or not api_base_url:
        print("Custom API key or base URL not configured")
        return

    processor = CustomAPIProcessor(api_key, api_base_url)

    # 测试连接
    if await processor.test_connection():
        print("✅ Custom API connection successful")

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
        print(f"✅ Email classified as: {category}")

        # 测试数据提取
        if category == "project_related":
            project_data = await processor.extract_structured_data(
                test_email, "project"
            )
            if project_data:
                print(f"✅ Project data extracted: {project_data}")
    else:
        print("❌ Custom API connection failed")


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_custom_api())
