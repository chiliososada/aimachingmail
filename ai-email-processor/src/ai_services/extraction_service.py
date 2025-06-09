# src/ai_services/extraction_service.py
"""数据提取服务 - 封装AI数据提取逻辑"""

import json
import re
import logging
from datetime import datetime
from typing import Dict, Optional, Any
import httpx
from openai import AsyncOpenAI

from src.models.data_models import ProjectStructured, EngineerStructured, EmailData
from src.ai_services.ai_client_manager import ai_client_manager
from src.no_auth_processor import NoAuthCustomAPIProcessor

logger = logging.getLogger(__name__)


class ExtractionService:
    """数据提取服务"""

    def __init__(self):
        self.client_manager = ai_client_manager

    def _extract_json_from_text(self, text: str) -> Optional[Dict]:
        """从文本中提取JSON部分"""
        try:
            result = json.loads(text.strip())
            return result
        except json.JSONDecodeError:
            json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
            matches = re.findall(json_pattern, text, re.DOTALL)

            for match in matches:
                try:
                    result = json.loads(match)
                    return result
                except json.JSONDecodeError:
                    continue

            start_idx = text.find("{")
            if start_idx != -1:
                brace_count = 0
                for i, char in enumerate(text[start_idx:], start_idx):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            try:
                                extracted = text[start_idx : i + 1]
                                result = json.loads(extracted)
                                return result
                            except json.JSONDecodeError:
                                break

            logger.warning(f"无法从文本中提取JSON: {text[:200]}...")
            return None

    def _parse_date_string(self, date_str: str) -> Optional[str]:
        """日期字符串解析和标准化"""
        if not date_str or date_str.strip() == "":
            return None

        date_str = date_str.strip()

        # 处理"即日"的情况
        if date_str in ["即日", "即日開始", "すぐ", "今すぐ", "ASAP"]:
            return datetime.now().strftime("%Y-%m-%d")

        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                return date_str
            except ValueError:
                logger.warning(f"Invalid standard date format: {date_str}")
                return None

        try:
            match = re.match(r"(\d{4})年(\d{1,2})月?(?:(\d{1,2})日?)?", date_str)
            if match:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3)) if match.group(3) else 1

                if 1 <= month <= 12 and 1 <= day <= 31:
                    formatted_date = f"{year:04d}-{month:02d}-{day:02d}"
                    try:
                        datetime.strptime(formatted_date, "%Y-%m-%d")
                        return formatted_date
                    except ValueError:
                        return None

            match = re.match(r"(\d{4})[/-](\d{1,2})(?:[/-](\d{1,2}))?", date_str)
            if match:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3)) if match.group(3) else 1

                if 1 <= month <= 12 and 1 <= day <= 31:
                    formatted_date = f"{year:04d}-{month:02d}-{day:02d}"
                    try:
                        datetime.strptime(formatted_date, "%Y-%m-%d")
                        return formatted_date
                    except ValueError:
                        return None

            return None

        except Exception as e:
            logger.error(f"Error parsing date '{date_str}': {e}")
            return None

    async def extract_project_info(
        self, email_data: EmailData, extracted_content: str
    ) -> Optional[ProjectStructured]:
        """提取项目信息"""
        # 首先尝试主要提取客户端
        try:
            result = await self._extract_project_with_client(
                email_data, extracted_content, use_fallback=False
            )
            if result:
                return result
        except Exception as e:
            logger.warning(f"主要数据提取客户端调用失败: {e}")

        # 如果主要客户端失败，尝试后备客户端
        try:
            logger.info("尝试使用后备数据提取客户端")
            result = await self._extract_project_with_client(
                email_data, extracted_content, use_fallback=True
            )
            if result:
                return result
        except Exception as e:
            logger.warning(f"后备数据提取客户端调用失败: {e}")

        logger.warning("所有数据提取客户端都失败")
        return None

    async def _extract_project_with_client(
        self, email_data: EmailData, extracted_content: str, use_fallback: bool = False
    ) -> Optional[ProjectStructured]:
        """使用指定客户端提取项目信息"""

        client, config = self.client_manager.get_client("extraction", use_fallback)

        if not client or not config:
            client_type = "后备" if use_fallback else "主要"
            logger.warning(f"{client_type}数据提取客户端未初始化")
            return None

        provider_name = config.get("provider_name")
        model_extract = config.get("model_extract", "gpt-4")
        temperature = config.get("temperature", 0.3)
        max_tokens_extract = config.get("max_tokens", 2048)

        client_type = "后备" if use_fallback else "主要"
        logger.info(f"使用{client_type}数据提取客户端: {provider_name}")

        prompt = f"""
以下のメールから案件情報を抽出して、必ずJSON形式で返してください。他の説明は不要です。

件名: {email_data.subject}
本文: {extracted_content}

以下の形式で抽出してください：
{{
    "title": "案件タイトル",
    "client_company": "クライアント企業名",
    "partner_company": "パートナー企業名",
    "description": "案件概要",
    "detail_description": "詳細説明",
    "skills": ["必要スキル1", "必要スキル2"],
    "key_technologies": "主要技術",
    "location": "勤務地",
    "work_type": "勤務形態（常駐/リモート/ハイブリッド等）",
    "start_date": "開始日（YYYY-MM-DD形式、例：2024-06-01）",
    "duration": "期間",
    "application_deadline": "応募締切（YYYY-MM-DD形式）",
    "budget": "予算/単価",
    "desired_budget": "希望予算",
    "japanese_level": "日本語レベル",
    "experience": "必要経験",
    "foreigner_accepted": true,
    "freelancer_accepted": true,
    "interview_count": "1",
    "processes": ["工程1", "工程2"],
    "max_candidates": 5,
    "manager_name": "担当者名",
    "manager_email": "担当者メール"
}}

重要：
- start_dateは必ずYYYY-MM-DD形式で返してください
- 開始日が即日・すぐ等の場合は現在の日付を使用してください
- 情報が見つからない項目はnullにしてください
- interview_countは文字列で返してください（例："1", "2"）
- processesは配列で返してください（例：["要件定義", "設計"]、見つからない場合は[]）
- skillsは配列で返してください（例：["Java", "Spring"]、見つからない場合は[]）
- foreigner_accepted, freelancer_acceptedはtrue/falseで返してください
- max_candidatesは数値で返してください
- JSONのみを返してください
"""

        messages = [
            {
                "role": "system",
                "content": "あなたは案件情報抽出の専門家です。必ずJSONのみを返してください。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            data = None

            if provider_name == "openai":
                response = await client.chat.completions.create(
                    model=model_extract,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens_extract,
                )
                raw_content = response.choices[0].message.content
                data = self._extract_json_from_text(raw_content)

            elif provider_name in ["deepseek", "custom"]:
                if isinstance(client, httpx.AsyncClient):
                    response = await client.post(
                        "/v1/chat/completions",
                        json={
                            "model": model_extract,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens_extract,
                        },
                    )
                    response.raise_for_status()
                    response_json = response.json()
                    raw_response_content = response_json["choices"][0]["message"][
                        "content"
                    ]
                    data = self._extract_json_from_text(raw_response_content)
                elif isinstance(client, NoAuthCustomAPIProcessor):
                    email_data_for_extraction = {
                        "subject": email_data.subject,
                        "body_text": extracted_content,
                    }
                    data = await client.extract_structured_data(
                        email_data_for_extraction, "project", model_extract
                    )

            elif provider_name == "custom_no_auth":
                if isinstance(client, NoAuthCustomAPIProcessor):
                    email_data_for_extraction = {
                        "subject": email_data.subject,
                        "body_text": extracted_content,
                    }
                    data = await client.extract_structured_data(
                        email_data_for_extraction, "project", model_extract
                    )
            else:
                raise ValueError(f"Unsupported extraction provider: {provider_name}")

            if data:
                # 处理日期格式
                if not data.get("start_date"):
                    data["start_date"] = datetime.now().strftime("%Y-%m-%d")
                    logger.info("项目开始日期未指定，设置为当前日期（即日）")
                else:
                    normalized_date = self._parse_date_string(data["start_date"])
                    data["start_date"] = normalized_date or datetime.now().strftime(
                        "%Y-%m-%d"
                    )

                # 处理应募截止日期
                if data.get("application_deadline"):
                    normalized_deadline = self._parse_date_string(
                        data["application_deadline"]
                    )
                    data["application_deadline"] = normalized_deadline

                logger.info(f"{client_type}数据提取客户端成功提取项目信息")
                return ProjectStructured(**data)

        except Exception as e:
            logger.error(f"{client_type}数据提取客户端提取项目信息失败: {e}")
            raise  # 重新抛出异常以便上层处理fallback

        return None

    async def extract_engineer_info(
        self, email_data: EmailData, extracted_content: str
    ) -> Optional[EngineerStructured]:
        """提取工程师信息"""
        # 首先尝试主要提取客户端
        try:
            result = await self._extract_engineer_with_client(
                email_data, extracted_content, use_fallback=False
            )
            if result:
                return result
        except Exception as e:
            logger.warning(f"主要数据提取客户端调用失败: {e}")

        # 如果主要客户端失败，尝试后备客户端
        try:
            logger.info("尝试使用后备数据提取客户端")
            result = await self._extract_engineer_with_client(
                email_data, extracted_content, use_fallback=True
            )
            if result:
                return result
        except Exception as e:
            logger.warning(f"后备数据提取客户端调用失败: {e}")

        logger.warning("所有数据提取客户端都失败")
        return None

    async def _extract_engineer_with_client(
        self, email_data: EmailData, extracted_content: str, use_fallback: bool = False
    ) -> Optional[EngineerStructured]:
        """使用指定客户端提取工程师信息"""

        client, config = self.client_manager.get_client("extraction", use_fallback)

        if not client or not config:
            client_type = "后备" if use_fallback else "主要"
            logger.warning(f"{client_type}数据提取客户端未初始化")
            return None

        provider_name = config.get("provider_name")
        model_extract = config.get("model_extract", "gpt-4")
        temperature = config.get("temperature", 0.3)
        max_tokens_extract = config.get("max_tokens", 2048)

        client_type = "后备" if use_fallback else "主要"
        logger.info(f"使用{client_type}数据提取客户端: {provider_name}")

        prompt = f"""
以下のメールから技術者情報を抽出して、必ずJSON形式で返してください。

件名: {email_data.subject}
本文: {extracted_content[:1500]}

以下の形式で抽出してください（データ型と制約に注意）：
{{
    "name": "技術者名（文字列、必須）",
    "email": "メールアドレス（文字列またはnull）",
    "phone": "電話番号（文字列またはnull）",
    "gender": "性別（'男性', '女性', '回答しない' のいずれかまたはnull）",
    "age": "27"（文字列形式で年齢）,
    "nationality": "国籍（文字列またはnull）",
    "nearest_station": "最寄り駅（文字列またはnull）",
    "education": "学歴（文字列またはnull）",
    "arrival_year_japan": "来日年度（文字列またはnull）",
    "certifications": ["資格1", "資格2"]（文字列の配列、空の場合は[]）,
    "skills": ["Java", "Python", "Spring"]（文字列の配列、空の場合は[]）,
    "technical_keywords": ["Java", "Spring Boot", "MySQL"]（文字列の配列、空の場合は[]）,
    "experience": "5年"（文字列、必須）,
    "work_scope": "作業範囲（文字列またはnull）",
    "work_experience": "職務経歴（文字列またはnull）",
    "japanese_level": "ビジネスレベル"（必ず以下のいずれか: "不問", "日常会話レベル", "ビジネスレベル", "ネイティブレベル"）,
    "english_level": "日常会話レベル"（必ず以下のいずれか: "不問", "日常会話レベル", "ビジネスレベル", "ネイティブレベル"）,
    "availability": "稼働可能時期（文字列またはnull）",
    "current_status": "提案中"（以下のいずれか: "提案中", "事前面談", "面談", "結果待ち", "契約中", "営業終了", "アーカイブ"）,
    "preferred_work_style": ["常駐", "リモート"]（文字列の配列、空の場合は[]）,
    "preferred_locations": ["東京", "大阪"]（文字列の配列、空の場合は[]）,
    "desired_rate_min": 40（数値のみ、万円単位、不明の場合はnull）,
    "desired_rate_max": 50（数値のみ、万円単位、不明の場合はnull）,
    "overtime_available": false（true/false、不明の場合はfalse）,
    "business_trip_available": false（true/false、不明の場合はfalse）,
    "self_promotion": "自己PR（文字列またはnull）",
    "remarks": "備考（文字列またはnull）",
    "recommendation": "推薦コメント（文字列またはnull）"
}}

重要な制約事項：
1. nameとexperienceは必須フィールドです
2. japanese_levelとenglish_levelは必ず以下の4つの値のみを使用：
   - "不問" - 要求なし
   - "日常会話レベル" - N3-N5級、基本会話
   - "ビジネスレベル" - N2級、ビジネス会話
   - "ネイティブレベル" - N1級、流暢
3. genderは "男性", "女性", "回答しない" のいずれかのみ
4. current_statusは "提案中", "事前面談", "面談", "結果待ち", "契約中", "営業終了", "アーカイブ" のいずれか
5. 配列フィールドでデータがない場合は[]、nullではありません
6. 数値フィールドは純粋な数値のみ
7. 布尔值フィールドはtrue/falseのみ
8. JSONのみを返してください、他の説明は不要です
"""

        messages = [
            {
                "role": "system",
                "content": "あなたは技術者情報抽出の専門家です。データベース制約を厳密に守り、必ずJSONのみを返してください。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            data = None

            if provider_name == "openai":
                response = await client.chat.completions.create(
                    model=model_extract,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens_extract,
                )
                raw_content = response.choices[0].message.content
                data = self._extract_json_from_text(raw_content)

            elif provider_name in ["deepseek", "custom"]:
                if isinstance(client, httpx.AsyncClient):
                    response = await client.post(
                        "/v1/chat/completions",
                        json={
                            "model": model_extract,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens_extract,
                        },
                    )
                    response.raise_for_status()
                    response_json = response.json()
                    raw_response_content = response_json["choices"][0]["message"][
                        "content"
                    ]
                    data = self._extract_json_from_text(raw_response_content)
                elif isinstance(client, NoAuthCustomAPIProcessor):
                    email_data_for_extraction = {
                        "subject": email_data.subject,
                        "body_text": extracted_content,
                    }
                    data = await client.extract_structured_data(
                        email_data_for_extraction, "engineer", model_extract
                    )

            elif provider_name == "custom_no_auth":
                if isinstance(client, NoAuthCustomAPIProcessor):
                    email_data_for_extraction = {
                        "subject": email_data.subject,
                        "body_text": extracted_content,
                    }
                    data = await client.extract_structured_data(
                        email_data_for_extraction, "engineer", model_extract
                    )
            else:
                raise ValueError(f"Unsupported extraction provider: {provider_name}")

            if data:
                logger.info(f"{client_type}AI提取的原始数据: {data}")
                engineer_data = EngineerStructured(**data)
                logger.info(
                    f"{client_type}数据提取客户端成功提取并验证工程师数据: {engineer_data.name}"
                )
                return engineer_data

        except Exception as e:
            logger.error(f"{client_type}数据提取客户端提取工程师信息失败: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise  # 重新抛出异常以便上层处理fallback

        return None


# 全局提取服务实例
extraction_service = ExtractionService()
