# ====================
# 3. 创建新的无认证自定义API处理器
# src/no_auth_processor.py
# ====================

import httpx
from typing import Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)


def extract_json(content):
    """从响应内容中提取JSON数据"""
    if isinstance(content, dict):
        return content  # 已经是JSON对象了

    if isinstance(content, str):
        json_start = content.find("{")
        json_end = content.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            json_str = content[json_start:json_end]
            return json.loads(json_str)

    return None


class NoAuthCustomAPIProcessor:
    """无认证自定义API处理器"""

    def __init__(
        self, api_base_url: str, default_model: str = "default", timeout: float = 120.0
    ):
        self.base_url = api_base_url
        self.default_model = default_model
        self.timeout = timeout
        # 不设置Authorization头
        self.headers = {
            "Content-Type": "application/json",
        }

    async def classify_email(self, email_data: Dict, model: str = None) -> str:
        """使用无认证自定义API进行邮件分类"""
        # 使用默认模型或传入的模型
        use_model = model or self.default_model

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
                request_data = {"content": email_data["body_text"]}

                # 只有当模型名不为空时才添加model字段
                if use_model and use_model.strip() and use_model != "default":
                    request_data["model"] = use_model

                response = await client.post(
                    f"{self.base_url}/classify",
                    headers=self.headers,
                    json=request_data,
                )

                response.raise_for_status()
                data = response.json()

                category = data["category"]

                if "project" in category:
                    return "project_related"
                elif "engineer" in category:
                    return "engineer_related"
                elif "other" in category:
                    return "other"
                else:
                    return "unclassified"

            except Exception as e:
                logger.error(f"Error with No-Auth Custom API: {e}")
                return "unclassified"

    async def extract_structured_data(
        self, email_data: Dict, data_type: str, model: str = None
    ) -> Optional[Dict]:
        """使用无认证自定义API提取结构化数据"""
        use_model = model or self.default_model

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
                request_data = {"content": email_data["body_text"]}

                # 只有当模型名不为空时才添加model字段
                if use_model and use_model.strip() and use_model != "default":
                    request_data["model"] = use_model

                response = await client.post(
                    (
                        f"{self.base_url}/extract_cv"
                        if data_type == "engineer"
                        else f"{self.base_url}/extract_case"
                    ),
                    headers=self.headers,
                    json=request_data,
                )
                response.raise_for_status()
                data = response.json()

                content = data
                logger.info(content)

                # 如果已经是字典对象，直接返回
                if isinstance(content, dict):
                    return content

                # 提取JSON部分
                return extract_json(content)

            except Exception as e:
                logger.error(f"Error extracting data with No-Auth Custom API: {e}")

        return None

    async def test_connection(self) -> bool:
        """测试API连接"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                request_data = {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Hello, this is a test message.",
                        }
                    ],
                    "max_tokens": 10,
                }

                # 测试时如果有默认模型就使用
                if (
                    self.default_model
                    and self.default_model.strip()
                    and self.default_model != "default"
                ):
                    request_data["model"] = self.default_model

                # 这里可以添加实际的API测试请求
                # response = await client.post(
                #     f"{self.base_url}/test",
                #     headers=self.headers,
                #     json=request_data,
                # )
                # response.raise_for_status()

                logger.info("No-Auth Custom API connection test successful")
                return True

            except Exception as e:
                logger.error(f"No-Auth Custom API connection test failed: {e}")
                return False
