# src/deepseek_processor.py
"""DeepSeek APIを使用するメール処理器"""

import httpx
from typing import Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)


class DeepSeekProcessor:
    """DeepSeek API用のプロセッサー"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def classify_email(self, email_data: Dict) -> str:
        """DeepSeekを使用してメールを分類"""
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

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json={
                        "model": "deepseek-chat",
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
                    timeout=30.0,
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
                logger.error(f"Error with DeepSeek API: {e}")
                return "unclassified"

    async def extract_structured_data(
        self, email_data: Dict, data_type: str
    ) -> Optional[Dict]:
        """DeepSeekを使用して構造化データを抽出"""

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

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json={
                        "model": "deepseek-chat",
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
                    timeout=60.0,
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
                logger.error(f"Error extracting data with DeepSeek: {e}")

        return None
