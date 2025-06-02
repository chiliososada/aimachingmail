# src/email_processor.py
import os
import json
import imaplib
import email
from email.header import decode_header
from datetime import datetime
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re

import asyncpg
from openai import AsyncOpenAI
import httpx
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from src.encryption_utils import decrypt, DecryptionError
from src.config import Config

# ロギング設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 環境変数の読み込み
load_dotenv()


# Enumクラス
class EmailType(str, Enum):
    PROJECT_RELATED = "project_related"
    ENGINEER_RELATED = "engineer_related"
    OTHER = "other"
    UNCLASSIFIED = "unclassified"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    ERROR = "error"


# データモデル
@dataclass
class SMTPSettings:
    id: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    security_protocol: str
    from_email: str
    from_name: Optional[str]
    imap_host: Optional[str] = None
    imap_port: Optional[int] = 993


class ProjectStructured(BaseModel):
    """構造化された案件データ"""

    title: str
    client_company: Optional[str] = None
    description: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    start_date: Optional[str] = None
    duration: Optional[str] = None
    budget: Optional[str] = None
    japanese_level: Optional[str] = None
    work_type: Optional[str] = None
    experience: Optional[str] = None


class EngineerStructured(BaseModel):
    """構造化された技術者データ"""

    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    experience: str
    japanese_level: Optional[str] = None
    work_experience: Optional[str] = None
    education: Optional[str] = None
    desired_rate_min: Optional[int] = None
    desired_rate_max: Optional[int] = None


class EmailProcessor:
    def __init__(self, db_config: Dict, ai_config: Dict):
        self.db_config = db_config
        self.ai_config = ai_config  # This now includes 'provider_name'
        self.db_pool: Optional[asyncpg.Pool] = None
        self.ai_client: Optional[AsyncOpenAI | httpx.AsyncClient] = (
            None  # Generic AI client
        )

        provider_name = self.ai_config.get("provider_name")
        api_key = self.ai_config.get("api_key")

        if provider_name == "openai":
            if api_key:
                self.ai_client = AsyncOpenAI(api_key=api_key)
            else:
                logger.error(
                    "OpenAI API key not found in config. OpenAI client not initialized."
                )
        elif provider_name == "deepseek":
            # Placeholder for DeepSeek Client
            # For now, we'll use httpx.AsyncClient if an API key and base URL are provided.
            # This is a simplified direct HTTP client. A dedicated library would be better.
            api_base_url = self.ai_config.get("api_base_url")
            timeout = self.ai_config.get("timeout", 120.0)  # 从配置获取超时时间
            if api_key and api_base_url:
                self.ai_client = httpx.AsyncClient(
                    base_url=api_base_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=timeout,  # 使用配置的超时时间
                )
                logger.info(
                    f"DeepSeek client initialized with base URL: {api_base_url}, timeout: {timeout}s"
                )
            else:
                logger.warning(
                    "DeepSeek API key or base URL not found. DeepSeek client not initialized. "
                    "AI features will not work if DeepSeek is selected and not configured."
                )
                # self.ai_client will remain None
        else:
            logger.error(
                f"Unsupported AI provider: {provider_name}. No AI client initialized."
            )

        # The old self.openai_client is removed by not being assigned here.

    async def initialize(self):
        """初期化処理"""
        self.db_pool = await asyncpg.create_pool(**self.db_config)
        logger.info("Database pool created successfully")

    async def close(self):
        """クリーンアップ処理"""
        if self.db_pool:
            await self.db_pool.close()

    def _extract_json_from_text(self, text: str) -> Optional[Dict]:
        """テキストからJSON部分を抽出する"""
        logger.debug(f"Attempting to extract JSON from text: {text[:500]}...")

        try:
            # まず全体をJSONとして解析を試行
            result = json.loads(text.strip())
            logger.debug("Direct JSON parsing successful")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"Direct JSON parsing failed: {e}")
            # 失敗した場合、JSON部分を探して抽出
            json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
            matches = re.findall(json_pattern, text, re.DOTALL)

            logger.debug(f"Found {len(matches)} potential JSON matches")

            for i, match in enumerate(matches):
                logger.debug(f"Trying match {i+1}: {match[:100]}...")
                try:
                    result = json.loads(match)
                    logger.debug(f"Match {i+1} parsed successfully")
                    return result
                except json.JSONDecodeError:
                    logger.debug(f"Match {i+1} failed to parse")
                    continue

            # より複雑なネストしたJSONを処理
            start_idx = text.find("{")
            if start_idx != -1:
                logger.debug(
                    f"Trying complex JSON extraction starting at position {start_idx}"
                )
                brace_count = 0
                for i, char in enumerate(text[start_idx:], start_idx):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            try:
                                extracted = text[start_idx : i + 1]
                                logger.debug(
                                    f"Extracted complex JSON: {extracted[:100]}..."
                                )
                                result = json.loads(extracted)
                                logger.debug("Complex JSON extraction successful")
                                return result
                            except json.JSONDecodeError:
                                logger.debug("Complex JSON extraction failed")
                                break

            logger.warning(f"Could not extract JSON from text: {text[:200]}...")
            return None

    def _parse_date_string(self, date_str: str) -> Optional[str]:
        """日期字符串解析和标准化"""
        if not date_str or date_str.strip() == "":
            return None

        date_str = date_str.strip()

        # 如果已经是标准格式，直接返回
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            try:
                # 验证日期是否有效
                datetime.strptime(date_str, "%Y-%m-%d")
                return date_str
            except ValueError:
                logger.warning(f"Invalid standard date format: {date_str}")
                return None

        # 处理中文日期格式
        try:
            # 匹配 "2024年6月" 格式
            match = re.match(r"(\d{4})年(\d{1,2})月?(?:(\d{1,2})日?)?", date_str)
            if match:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3)) if match.group(3) else 1  # 默认为月初

                # 验证日期范围
                if 1 <= month <= 12 and 1 <= day <= 31:
                    formatted_date = f"{year:04d}-{month:02d}-{day:02d}"
                    # 验证日期是否有效
                    try:
                        datetime.strptime(formatted_date, "%Y-%m-%d")
                        logger.info(
                            f"Converted date '{date_str}' to '{formatted_date}'"
                        )
                        return formatted_date
                    except ValueError:
                        logger.warning(f"Invalid converted date: {formatted_date}")
                        return None

            # 匹配其他可能的格式 "2024/06", "2024-06" 等
            match = re.match(r"(\d{4})[/-](\d{1,2})(?:[/-](\d{1,2}))?", date_str)
            if match:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3)) if match.group(3) else 1

                if 1 <= month <= 12 and 1 <= day <= 31:
                    formatted_date = f"{year:04d}-{month:02d}-{day:02d}"
                    try:
                        datetime.strptime(formatted_date, "%Y-%m-%d")
                        logger.info(
                            f"Converted date '{date_str}' to '{formatted_date}'"
                        )
                        return formatted_date
                    except ValueError:
                        logger.warning(f"Invalid converted date: {formatted_date}")
                        return None

            # 如果无法识别格式，记录警告并返回None
            logger.warning(f"Unable to parse date format: {date_str}")
            return None

        except Exception as e:
            logger.error(f"Error parsing date '{date_str}': {e}")
            return None

    async def get_smtp_settings(self, tenant_id: str) -> List[SMTPSettings]:
        """テナントのSMTP設定を取得"""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, smtp_host, smtp_port, smtp_username, 
                       smtp_password_encrypted, security_protocol,
                       from_email, from_name
                FROM email_smtp_settings
                WHERE tenant_id = $1 AND is_active = true
                ORDER BY is_default DESC
            """,
                tenant_id,
            )

            settings = []
            for row in rows:
                # NOTE: This decryption logic handles both string and bytes BYTEA fields
                decrypted_password = None
                try:
                    if row["smtp_password_encrypted"]:
                        password_data = row["smtp_password_encrypted"]

                        # 处理PostgreSQL BYTEA字段类型转换
                        if isinstance(password_data, str):
                            # 如果是字符串（十六进制编码），转换为字节
                            hex_str = password_data
                            if hex_str.startswith("\\x"):
                                hex_str = hex_str[2:]
                            try:
                                password_bytes = bytes.fromhex(hex_str)
                                decrypted_password = decrypt(
                                    password_bytes, Config.ENCRYPTION_KEY
                                )
                            except ValueError as ve:
                                logger.error(
                                    f"Failed to convert hex string to bytes for SMTP setting {row['id']}: {ve}"
                                )
                                continue
                        elif isinstance(password_data, bytes):
                            # 正常的字节类型处理
                            decrypted_password = decrypt(
                                password_data, Config.ENCRYPTION_KEY
                            )
                        else:
                            logger.error(
                                f"Unexpected password data type {type(password_data)} for SMTP setting {row['id']}"
                            )
                            continue

                except DecryptionError as e:
                    logger.error(
                        f"Failed to decrypt password for SMTP setting {row['id']}: {e}"
                    )
                    continue
                except Exception as e:
                    logger.error(
                        f"Unexpected error decrypting password for SMTP setting {row['id']}: {e}"
                    )
                    continue

                settings.append(
                    SMTPSettings(
                        id=str(row["id"]),
                        smtp_host=row["smtp_host"],
                        smtp_port=row["smtp_port"],
                        smtp_username=row["smtp_username"],
                        smtp_password=decrypted_password,
                        security_protocol=row["security_protocol"],
                        from_email=row["from_email"],
                        from_name=row["from_name"],
                        # IMAPホストは通常SMTPホストから推測
                        imap_host=row["smtp_host"].replace("smtp.", "imap."),
                    )
                )

            return settings

    async def fetch_emails(self, settings: SMTPSettings) -> List[Dict]:
        """メールサーバーから新着メールを取得"""
        emails = []

        try:
            # IMAP接続
            if settings.security_protocol == "SSL":
                mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
            else:
                mail = imaplib.IMAP4(settings.imap_host, settings.imap_port)

            mail.login(settings.smtp_username, settings.smtp_password)
            mail.select("INBOX")

            # 未読メールを検索
            _, messages = mail.search(None, "UNSEEN")

            for msg_num in messages[0].split():
                _, msg = mail.fetch(msg_num, "(RFC822)")

                for response in msg:
                    if isinstance(response, tuple):
                        email_message = email.message_from_bytes(response[1])

                        # メール情報を抽出
                        email_data = await self._parse_email(email_message)
                        emails.append(email_data)

                        # 既読にマーク
                        mail.store(msg_num, "+FLAGS", "\\Seen")

            mail.logout()

        except Exception as e:
            logger.error(f"Error fetching emails: {e}")

        return emails

    async def _parse_email(self, msg) -> Dict:
        """メールメッセージをパース"""
        # 件名のデコード
        subject = ""
        if msg["Subject"]:
            subject, encoding = decode_header(msg["Subject"])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding or "utf-8")

        # 送信者情報
        sender = msg.get("From", "")
        sender_name = ""
        sender_email = ""

        if "<" in sender and ">" in sender:
            sender_name = sender.split("<")[0].strip()
            sender_email = sender.split("<")[1].replace(">", "").strip()
        else:
            sender_email = sender

        # 本文の抽出
        body_text = ""
        body_html = ""
        attachments = []

        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in content_disposition:
                # 添付ファイル処理
                filename = part.get_filename()
                if filename:
                    attachments.append(
                        {
                            "filename": filename,
                            "content_type": content_type,
                            "size": len(part.get_payload(decode=True)),
                        }
                    )
            elif content_type == "text/plain":
                body_text = part.get_payload(decode=True).decode(
                    "utf-8", errors="ignore"
                )
            elif content_type == "text/html":
                body_html = part.get_payload(decode=True).decode(
                    "utf-8", errors="ignore"
                )

        return {
            "subject": subject,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "body_text": body_text,
            "body_html": body_html,
            "attachments": attachments,
            "received_at": datetime.now(),
        }

    async def classify_email(self, email_data: Dict) -> EmailType:
        """AIを使用してメールを分類"""
        if not self.ai_client:
            logger.warning("AI client not initialized. Skipping email classification.")
            return EmailType.UNCLASSIFIED

        provider_name = self.ai_config.get("provider_name")
        model_classify = self.ai_config.get(
            "model_classify", "gpt-3.5-turbo"
        )  # Default for safety
        temperature = self.ai_config.get("temperature", 0.3)
        max_tokens_classify = self.ai_config.get(
            "max_tokens", 50
        )  # Use general max_tokens or a specific one

        prompt = f"""
        以下のメールを分析して、カテゴリーを判定してください。
        
        件名: {email_data['subject']}
        本文: {email_data['body_text'][:1000]}
        
        カテゴリー:
        1. project_related - 案件に関するメール（求人、プロジェクト募集など）
        2. engineer_related - 技術者に関するメール（履歴書、スキルシートなど）
        3. other - その他の重要なメール
        4. unclassified - 分類不能または無関係なメール
        
        カテゴリー名のみを回答してください。
        """

        messages = [
            {"role": "system", "content": "あなたはメール分類の専門家です。"},
            {"role": "user", "content": prompt},
        ]

        try:
            if provider_name == "openai":
                response = await self.ai_client.chat.completions.create(
                    model=model_classify,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens_classify,
                )
                category = response.choices[0].message.content.strip().lower()
            elif provider_name == "deepseek":
                if isinstance(self.ai_client, httpx.AsyncClient):
                    # DeepSeek API call (example, adjust path and payload as needed)
                    try:
                        response = await self.ai_client.post(
                            "/v1/chat/completions",  # Or specific DeepSeek endpoint path
                            json={
                                "model": model_classify,
                                "messages": messages,
                                "temperature": temperature,
                                "max_tokens": max_tokens_classify,
                            },
                        )
                        response.raise_for_status()  # Raise an exception for HTTP errors
                        data = response.json()
                        category = (
                            data["choices"][0]["message"]["content"].strip().lower()
                        )
                    except httpx.ReadTimeout as e:
                        logger.error(f"DeepSeek API timeout during classification: {e}")
                        return EmailType.UNCLASSIFIED
                    except httpx.HTTPStatusError as e:
                        logger.error(
                            f"DeepSeek API HTTP error during classification: {e}"
                        )
                        return EmailType.UNCLASSIFIED
                    except KeyError as e:
                        logger.error(
                            f"DeepSeek API response format error during classification: {e}"
                        )
                        return EmailType.UNCLASSIFIED
                else:  # Deepseek client not properly initialized as httpx.AsyncClient
                    logger.warning(
                        "DeepSeek client not an httpx.AsyncClient. Skipping classification."
                    )
                    return EmailType.UNCLASSIFIED
            else:
                logger.warning(
                    f"Unsupported AI provider for classification: {provider_name}"
                )
                return EmailType.UNCLASSIFIED

            # Enumに変換
            if "project" in category:
                return EmailType.PROJECT_RELATED
            elif "engineer" in category:
                return EmailType.ENGINEER_RELATED
            elif "other" in category:
                return EmailType.OTHER
            else:
                return EmailType.UNCLASSIFIED

        except Exception as e:
            logger.error(f"Error classifying email: {e}")
            return EmailType.UNCLASSIFIED

    async def extract_project_info(
        self, email_data: Dict
    ) -> Optional[ProjectStructured]:
        """メールから案件情報を抽出して構造化"""
        if not self.ai_client:
            logger.warning(
                "AI client not initialized. Skipping project info extraction."
            )
            return None

        provider_name = self.ai_config.get("provider_name")
        model_extract = self.ai_config.get(
            "model_extract", "gpt-4"
        )  # Default for safety
        temperature = self.ai_config.get("temperature", 0.3)
        max_tokens_extract = self.ai_config.get(
            "max_tokens", 2048
        )  # Use general max_tokens

        prompt = f"""
        以下のメールから案件情報を抽出して、必ずJSON形式で返してください。他の説明は不要です。

        件名: {email_data['subject']}
        本文: {email_data['body_text']}
        
        以下の形式で抽出してください：
        {{
            "title": "案件タイトル",
            "client_company": "クライアント企業名",
            "description": "案件概要",
            "skills": ["必要スキル1", "必要スキル2"],
            "location": "勤務地",
            "start_date": "開始日（YYYY-MM-DD形式、例：2024-06-01）",
            "duration": "期間",
            "budget": "予算/単価",
            "japanese_level": "日本語レベル",
            "work_type": "勤務形態",
            "experience": "必要経験"
        }}
        
        重要：
        - start_dateは必ずYYYY-MM-DD形式で返してください（例：2024-06-01）
        - 「2024年6月」のような表記は「2024-06-01」に変換してください
        - 具体的な日が不明な場合は月初（01日）にしてください
        - 情報が見つからない項目はnullにしてください
        - JSONのみを返してください
        """
        messages = [
            {
                "role": "system",
                "content": "あなたは案件情報抽出の専門家です。必ずJSONのみを返してください。日付は必ずYYYY-MM-DD形式で返してください。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            if provider_name == "openai":
                response = await self.ai_client.chat.completions.create(
                    model=model_extract,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens_extract,
                    # response_format パラメータを削除
                )
                raw_content = response.choices[0].message.content
                data = self._extract_json_from_text(raw_content)

            elif provider_name == "deepseek":
                if isinstance(self.ai_client, httpx.AsyncClient):
                    # DeepSeek API call (example, adjust path and payload as needed)
                    try:
                        logger.info(
                            "Sending request to DeepSeek API for project extraction..."
                        )
                        logger.debug(
                            f"Request payload: model={model_extract}, temperature={temperature}, max_tokens={max_tokens_extract}"
                        )

                        response = await self.ai_client.post(
                            "/v1/chat/completions",  # Or specific DeepSeek endpoint path
                            json={
                                "model": model_extract,
                                "messages": messages,
                                "temperature": temperature,
                                "max_tokens": max_tokens_extract,
                            },
                        )
                        response.raise_for_status()

                        logger.info(
                            f"DeepSeek API responded with status: {response.status_code}"
                        )

                        response_json = response.json()
                        logger.info("=== DeepSeek API Response ===")
                        logger.info(
                            f"Full response: {json.dumps(response_json, indent=2, ensure_ascii=False)}"
                        )

                        raw_response_content = response_json["choices"][0]["message"][
                            "content"
                        ]
                        logger.info("=== DeepSeek Raw Content ===")
                        logger.info(f"Raw content:\n{raw_response_content}")
                        logger.info("=== End Raw Content ===")

                        # 同时打印到控制台
                        print("\n" + "=" * 50)
                        print("DeepSeek API 返回内容:")
                        print("=" * 50)
                        print(raw_response_content)
                        print("=" * 50 + "\n")

                        data = self._extract_json_from_text(raw_response_content)
                        if data:
                            logger.info(
                                f"Successfully extracted JSON: {json.dumps(data, indent=2, ensure_ascii=False)}"
                            )
                            print(
                                f"✅ JSON解析成功: {json.dumps(data, indent=2, ensure_ascii=False)}"
                            )
                        else:
                            logger.error(
                                "Failed to extract JSON from DeepSeek response"
                            )
                            print("❌ JSON解析失败")

                    except httpx.ReadTimeout as e:
                        logger.error(f"DeepSeek API timeout error: {e}")
                        print(f"❌ DeepSeek API 超时错误: {e}")
                        return None
                    except httpx.HTTPStatusError as e:
                        logger.error(f"DeepSeek API HTTP error: {e}")
                        logger.error(f"Response text: {e.response.text}")
                        print(f"❌ DeepSeek API HTTP错误: {e}")
                        print(f"响应内容: {e.response.text}")
                        return None
                    except KeyError as e:
                        logger.error(f"DeepSeek API response format error: {e}")
                        logger.error(
                            f"Response: {response.json() if 'response' in locals() else 'No response'}"
                        )
                        print(f"❌ DeepSeek API 响应格式错误: {e}")
                        return None
                else:  # Deepseek client not properly initialized
                    logger.warning(
                        "DeepSeek client not an httpx.AsyncClient. Skipping project info extraction."
                    )
                    return None
            else:
                logger.warning(
                    f"Unsupported AI provider for project info extraction: {provider_name}"
                )
                return None

            if data:
                # 处理日期格式
                if data.get("start_date"):
                    normalized_date = self._parse_date_string(data["start_date"])
                    data["start_date"] = normalized_date

                return ProjectStructured(**data)
            else:
                logger.error("Failed to parse JSON from AI response for project info")
                return None

        except Exception as e:
            logger.error(f"Error extracting project info: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None

    async def extract_engineer_info(
        self, email_data: Dict
    ) -> Optional[EngineerStructured]:
        """メールから技術者情報を抽出して構造化"""
        if not self.ai_client:
            logger.warning(
                "AI client not initialized. Skipping engineer info extraction."
            )
            return None

        provider_name = self.ai_config.get("provider_name")
        model_extract = self.ai_config.get(
            "model_extract", "gpt-4"
        )  # Default for safety
        temperature = self.ai_config.get("temperature", 0.3)
        max_tokens_extract = self.ai_config.get(
            "max_tokens", 2048
        )  # Use general max_tokens

        prompt = f"""
        以下のメールから技術者情報を抽出して、必ずJSON形式で返してください。他の説明は不要です。
        
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
        
        情報が見つからない項目はnullにしてください。
        JSONのみを返してください。
        """
        messages = [
            {
                "role": "system",
                "content": "あなたは技術者情報抽出の専門家です。必ずJSONのみを返してください。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            if provider_name == "openai":
                response = await self.ai_client.chat.completions.create(
                    model=model_extract,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens_extract,
                    # response_format パラメータを削除
                )
                raw_content = response.choices[0].message.content
                data = self._extract_json_from_text(raw_content)

            elif provider_name == "deepseek":
                if isinstance(self.ai_client, httpx.AsyncClient):
                    # DeepSeek API call (example, adjust path and payload as needed)
                    try:
                        logger.info(
                            "Sending request to DeepSeek API for engineer extraction..."
                        )
                        logger.debug(
                            f"Request payload: model={model_extract}, temperature={temperature}, max_tokens={max_tokens_extract}"
                        )

                        response = await self.ai_client.post(
                            "/v1/chat/completions",  # Or specific DeepSeek endpoint path
                            json={
                                "model": model_extract,
                                "messages": messages,
                                "temperature": temperature,
                                "max_tokens": max_tokens_extract,
                            },
                        )
                        response.raise_for_status()

                        logger.info(
                            f"DeepSeek API responded with status: {response.status_code}"
                        )

                        response_json = response.json()
                        logger.info("=== DeepSeek API Response (Engineer) ===")
                        logger.info(
                            f"Full response: {json.dumps(response_json, indent=2, ensure_ascii=False)}"
                        )

                        raw_response_content = response_json["choices"][0]["message"][
                            "content"
                        ]
                        logger.info("=== DeepSeek Raw Content (Engineer) ===")
                        logger.info(f"Raw content:\n{raw_response_content}")
                        logger.info("=== End Raw Content ===")

                        # 同时打印到控制台
                        print("\n" + "=" * 50)
                        print("DeepSeek API 返回内容 (工程师信息):")
                        print("=" * 50)
                        print(raw_response_content)
                        print("=" * 50 + "\n")

                        data = self._extract_json_from_text(raw_response_content)
                        if data:
                            logger.info(
                                f"Successfully extracted JSON: {json.dumps(data, indent=2, ensure_ascii=False)}"
                            )
                            print(
                                f"✅ JSON解析成功: {json.dumps(data, indent=2, ensure_ascii=False)}"
                            )
                        else:
                            logger.error(
                                "Failed to extract JSON from DeepSeek response"
                            )
                            print("❌ JSON解析失败")

                    except httpx.ReadTimeout as e:
                        logger.error(f"DeepSeek API timeout error: {e}")
                        print(f"❌ DeepSeek API 超时错误: {e}")
                        return None
                    except httpx.HTTPStatusError as e:
                        logger.error(f"DeepSeek API HTTP error: {e}")
                        logger.error(f"Response text: {e.response.text}")
                        print(f"❌ DeepSeek API HTTP错误: {e}")
                        print(f"响应内容: {e.response.text}")
                        return None
                    except KeyError as e:
                        logger.error(f"DeepSeek API response format error: {e}")
                        logger.error(
                            f"Response: {response.json() if 'response' in locals() else 'No response'}"
                        )
                        print(f"❌ DeepSeek API 响应格式错误: {e}")
                        return None
                else:  # Deepseek client not properly initialized
                    logger.warning(
                        "DeepSeek client not an httpx.AsyncClient. Skipping engineer info extraction."
                    )
                    return None
            else:
                logger.warning(
                    f"Unsupported AI provider for engineer info extraction: {provider_name}"
                )
                return None

            if data:
                return EngineerStructured(**data)
            else:
                logger.error("Failed to parse JSON from AI response for engineer info")
                return None

        except Exception as e:
            logger.error(f"Error extracting engineer info: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None

    async def save_email_to_db(
        self,
        tenant_id: str,
        email_data: Dict,
        email_type: EmailType,
        extracted_data: Optional[Dict],
    ) -> str:
        """メールをデータベースに保存"""
        async with self.db_pool.acquire() as conn:
            # receive_emailsテーブルに保存
            email_id = await conn.fetchval(
                """
                INSERT INTO receive_emails (
                    tenant_id, subject, body_text, body_html,
                    sender_name, sender_email, email_type,
                    processing_status, ai_extracted_data,
                    received_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """,
                tenant_id,
                email_data["subject"],
                email_data["body_text"],
                email_data["body_html"],
                email_data["sender_name"],
                email_data["sender_email"],
                email_type.value,
                ProcessingStatus.PROCESSING.value,
                json.dumps(extracted_data) if extracted_data else "{}",
                email_data["received_at"],
            )

            return str(email_id)

    async def save_project(
        self,
        tenant_id: str,
        project_data: ProjectStructured,
        email_id: str,
        sender_email: str,
    ) -> Optional[str]:
        """案件情報をデータベースに保存"""
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                try:
                    # 日期处理
                    start_date_value = None
                    if project_data.start_date:
                        # 再次验证和转换日期格式
                        normalized_date = self._parse_date_string(
                            project_data.start_date
                        )
                        if normalized_date:
                            try:
                                start_date_value = datetime.strptime(
                                    normalized_date, "%Y-%m-%d"
                                ).date()
                                logger.info(
                                    f"Converted start_date to database format: {start_date_value}"
                                )
                            except ValueError as e:
                                logger.warning(
                                    f"Failed to convert normalized date {normalized_date} to date object: {e}"
                                )
                                start_date_value = None
                        else:
                            logger.warning(
                                f"Failed to normalize date: {project_data.start_date}"
                            )
                            start_date_value = None

                    # projectsテーブルに保存
                    project_id = await conn.fetchval(
                        """
                        INSERT INTO projects (
                            tenant_id, title, client_company, description,
                            skills, location, start_date, duration,
                            budget, japanese_level, work_type, experience,
                            source, ai_processed, status, partner_company,
                            manager_email, created_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, 
                            $7, $8, $9, $10, $11, $12,
                            'mail_import', true, '募集中', '他社',
                            $13, $14
                        )
                        RETURNING id
                    """,
                        tenant_id,
                        project_data.title,
                        project_data.client_company,
                        project_data.description,
                        project_data.skills,
                        project_data.location,
                        start_date_value,  # 使用处理后的日期值
                        project_data.duration,
                        project_data.budget,
                        project_data.japanese_level,
                        project_data.work_type,
                        project_data.experience,
                        sender_email,
                        datetime.now(),
                    )

                    # receive_emailsテーブルを更新
                    await conn.execute(
                        """
                        UPDATE receive_emails 
                        SET project_id = $1, 
                            processing_status = $2,
                            ai_extraction_status = 'completed'
                        WHERE id = $3
                    """,
                        project_id,
                        ProcessingStatus.PROCESSED.value,
                        email_id,
                    )

                    logger.info(f"Project saved successfully: {project_id}")
                    return str(project_id)

                except Exception as e:
                    logger.error(f"Error saving project: {e}")
                    await conn.execute(
                        """
                        UPDATE receive_emails 
                        SET processing_status = $1,
                            ai_extraction_status = 'failed',
                            processing_error = $2
                        WHERE id = $3
                    """,
                        ProcessingStatus.ERROR.value,
                        str(e),
                        email_id,
                    )
                    return None

    async def save_engineer(
        self,
        tenant_id: str,
        engineer_data: EngineerStructured,
        email_id: str,
        sender_email: str,
    ) -> Optional[str]:
        """技術者情報をデータベースに保存"""
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                try:
                    # engineersテーブルに保存
                    engineer_id = await conn.fetchval(
                        """
                        INSERT INTO engineers (
                            tenant_id, name, email, phone, skills,
                            experience, japanese_level, work_experience,
                            education, desired_rate_min, desired_rate_max,
                            company_type, source, current_status,
                            created_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                            '他社', 'mail', '提案中', $12
                        )
                        RETURNING id
                    """,
                        tenant_id,
                        engineer_data.name,
                        engineer_data.email or sender_email,
                        engineer_data.phone,
                        engineer_data.skills,
                        engineer_data.experience,
                        engineer_data.japanese_level,
                        engineer_data.work_experience,
                        engineer_data.education,
                        engineer_data.desired_rate_min,
                        engineer_data.desired_rate_max,
                        datetime.now(),
                    )

                    # receive_emailsテーブルを更新
                    await conn.execute(
                        """
                        UPDATE receive_emails 
                        SET engineer_id = $1, 
                            processing_status = $2,
                            ai_extraction_status = 'completed'
                        WHERE id = $3
                    """,
                        engineer_id,
                        ProcessingStatus.PROCESSED.value,
                        email_id,
                    )

                    logger.info(f"Engineer saved successfully: {engineer_id}")
                    return str(engineer_id)

                except Exception as e:
                    logger.error(f"Error saving engineer: {e}")
                    await conn.execute(
                        """
                        UPDATE receive_emails 
                        SET processing_status = $1,
                            ai_extraction_status = 'failed',
                            processing_error = $2
                        WHERE id = $3
                    """,
                        ProcessingStatus.ERROR.value,
                        str(e),
                        email_id,
                    )
                    return None

    async def process_emails_for_tenant(self, tenant_id: str):
        """特定テナントのメール処理を実行"""
        # SMTP設定を取得
        settings_list = await self.get_smtp_settings(tenant_id)

        if not settings_list:
            logger.warning(f"No SMTP settings found for tenant: {tenant_id}")
            return

        for settings in settings_list:
            try:
                # メールを取得
                emails = await self.fetch_emails(settings)
                logger.info(f"Fetched {len(emails)} new emails for tenant {tenant_id}")

                for email_data in emails:
                    # メールを分類
                    email_type = await self.classify_email(email_data)
                    logger.info(f"Email classified as: {email_type.value}")

                    # データベースに保存
                    email_id = await self.save_email_to_db(
                        tenant_id, email_data, email_type, None
                    )

                    # 案件関連の場合
                    if email_type == EmailType.PROJECT_RELATED:
                        project_data = await self.extract_project_info(email_data)
                        if project_data:
                            await self.save_project(
                                tenant_id,
                                project_data,
                                email_id,
                                email_data["sender_email"],
                            )

                    # 技術者関連の場合
                    elif email_type == EmailType.ENGINEER_RELATED:
                        engineer_data = await self.extract_engineer_info(email_data)
                        if engineer_data:
                            await self.save_engineer(
                                tenant_id,
                                engineer_data,
                                email_id,
                                email_data["sender_email"],
                            )

                    # その他の場合は処理済みとマーク
                    else:
                        async with self.db_pool.acquire() as conn:
                            await conn.execute(
                                """
                                UPDATE receive_emails 
                                SET processing_status = $1
                                WHERE id = $2
                            """,
                                ProcessingStatus.PROCESSED.value,
                                email_id,
                            )

            except Exception as e:
                logger.error(f"Error processing emails for settings {settings.id}: {e}")
                continue


# バッチ処理用のメイン関数
async def main():
    # データベース設定
    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", 5432),
        "database": os.getenv("DB_NAME", "ai_matching"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
    }

    # AI設定
    # Config.get_ai_config() will be used by the EmailProcessor constructor internally
    # For the main function, we can pass the result of Config.get_ai_config()
    # which now includes the provider_name and specific settings for that provider.
    active_ai_config = Config.get_ai_config()  # Gets config for the DEFAULT_AI_PROVIDER

    # プロセッサーの初期化
    processor = EmailProcessor(
        db_config=Config.get_db_config(), ai_config=active_ai_config
    )
    await processor.initialize()

    try:
        # すべてのアクティブなテナントを取得
        async with processor.db_pool.acquire() as conn:
            tenant_ids = await conn.fetch(
                """
                SELECT DISTINCT t.id 
                FROM tenants t
                INNER JOIN email_smtp_settings s ON s.tenant_id = t.id
                WHERE t.is_active = true AND s.is_active = true
            """
            )

        # 各テナントのメールを処理
        for row in tenant_ids:
            tenant_id = str(row["id"])
            logger.info(f"Processing emails for tenant: {tenant_id}")
            await processor.process_emails_for_tenant(tenant_id)

    except Exception as e:
        logger.error(f"Error in main processing: {e}")
    finally:
        await processor.close()


if __name__ == "__main__":
    # 定期実行用（cronやスケジューラーで実行）
    asyncio.run(main())
