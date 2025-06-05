# src/email_processor.py
"""主要邮件处理模块 - 重构版（修复Pydantic验证错误和数据库约束问题）"""

import os
import json
import imaplib
import email
import base64
from email.header import decode_header
from datetime import datetime, date
import asyncio
import logging
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

import asyncpg
from openai import AsyncOpenAI
import httpx
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

from src.encryption_utils import decrypt, DecryptionError
from src.config import Config
from src.email_classifier import EmailClassifier, EmailType
from src.attachment_processor import AttachmentProcessor, ResumeData
from src.no_auth_processor import NoAuthCustomAPIProcessor

# ロギング設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 環境変数の読み込み
load_dotenv()


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
    partner_company: Optional[str] = None
    description: Optional[str] = None
    detail_description: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    key_technologies: Optional[str] = None
    location: Optional[str] = None
    work_type: Optional[str] = None
    start_date: Optional[str] = None
    duration: Optional[str] = None
    application_deadline: Optional[str] = None
    budget: Optional[str] = None
    desired_budget: Optional[str] = None
    japanese_level: Optional[str] = None
    experience: Optional[str] = None
    foreigner_accepted: Optional[bool] = False
    freelancer_accepted: Optional[bool] = False
    interview_count: Optional[str] = "1"
    processes: List[str] = Field(default_factory=list)
    max_candidates: Optional[int] = 5
    manager_name: Optional[str] = None
    manager_email: Optional[str] = None


class EngineerStructured(BaseModel):
    """構造化された技術者データ - 完全修复版本，支持数据库约束"""

    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    nationality: Optional[str] = None
    nearest_station: Optional[str] = None
    education: Optional[str] = None
    arrival_year_japan: Optional[str] = None
    certifications: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    technical_keywords: List[str] = Field(default_factory=list)
    experience: str = ""
    work_scope: Optional[str] = None
    work_experience: Optional[str] = None
    japanese_level: Optional[str] = None
    english_level: Optional[str] = None
    availability: Optional[str] = None
    current_status: Optional[str] = "提案中"
    preferred_work_style: List[str] = Field(default_factory=list)
    preferred_locations: List[str] = Field(default_factory=list)
    desired_rate_min: Optional[int] = None
    desired_rate_max: Optional[int] = None
    overtime_available: Optional[bool] = False
    business_trip_available: Optional[bool] = False
    self_promotion: Optional[str] = None
    remarks: Optional[str] = None
    recommendation: Optional[str] = None
    source_filename: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """姓名验证器 - 确保不为空"""
        if not v or v is None:
            return "名前不明"
        return str(v)

    @field_validator("experience")
    @classmethod
    def validate_experience(cls, v):
        """经验验证器 - 确保不为空"""
        if not v or v is None:
            return "不明"
        return str(v)

    @field_validator("age")
    @classmethod
    def validate_age(cls, v):
        """年龄字段验证器 - 将数字转换为字符串"""
        if v is None:
            return None
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str):
            return v
        return str(v)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        """电话号码验证器 - 将数字转换为字符串"""
        if v is None:
            return None
        return str(v)

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v):
        """性别验证器 - 映射到数据库允许值"""
        if v is None:
            return None

        v_str = str(v).lower()

        if any(word in v_str for word in ["男", "male", "m"]):
            return "男性"
        elif any(word in v_str for word in ["女", "female", "f"]):
            return "女性"
        else:
            return "回答しない"

    @field_validator("japanese_level", "english_level")
    @classmethod
    def validate_language_level(cls, v):
        """语言水平验证器 - 标准化为数据库允许的值"""
        if v is None:
            return None

        v_str = str(v).lower()

        # 语言水平映射规则
        mappings = {
            # N级别和数字等级映射
            "n1": "ネイティブレベル",
            "n2": "ビジネスレベル",
            "n3": "日常会話レベル",
            "n4": "日常会話レベル",
            "n5": "日常会話レベル",
            "1級": "ネイティブレベル",
            "2級": "ビジネスレベル",
            "3級": "日常会話レベル",
            "4級": "日常会話レベル",
            "5級": "日常会話レベル",
            # 流暢度描述映射
            "ネイティブ": "ネイティブレベル",
            "native": "ネイティブレベル",
            "ほぼ流暢": "ビジネスレベル",
            "流暢": "ビジネスレベル",
            "fluent": "ビジネスレベル",
            "ビジネス": "ビジネスレベル",
            "business": "ビジネスレベル",
            "日常会話": "日常会話レベル",
            "conversational": "日常会話レベル",
            "基本": "日常会話レベル",
            "basic": "日常会話レベル",
            "初級": "日常会話レベル",
            "中級": "日常会話レベル",
            "上級": "ビジネスレベル",
            "advanced": "ビジネスレベル",
            "不問": "不問",
            "問わない": "不問",
            "なし": "不問",
            "none": "不問",
        }

        # 尝试直接映射
        for key, mapped_value in mappings.items():
            if key in v_str:
                logger.info(f"语言水平映射: '{v}' -> '{mapped_value}'")
                return mapped_value

        # 如果包含数字，尝试提取等级
        import re

        numbers = re.findall(r"[1-5]", v_str)
        if numbers:
            level = int(numbers[0])
            if level == 1:
                return "ネイティブレベル"
            elif level == 2:
                return "ビジネスレベル"
            else:
                return "日常会話レベル"

        # 默认映射策略
        if any(
            word in v_str
            for word in ["上級", "高級", "1級", "n1", "ネイティブ", "native"]
        ):
            return "ネイティブレベル"
        elif any(
            word in v_str
            for word in ["ビジネス", "business", "2級", "n2", "流暢", "fluent"]
        ):
            return "ビジネスレベル"
        elif any(
            word in v_str
            for word in ["会話", "conversational", "3級", "4級", "n3", "n4"]
        ):
            return "日常会話レベル"
        elif any(word in v_str for word in ["不問", "問わない", "なし", "none"]):
            return "不問"
        else:
            # 如果无法识别，默认设为日常会话级
            logger.warning(f"无法识别的语言水平: '{v}'，默认设为日常会話レベル")
            return "日常会話レベル"

    @field_validator("current_status")
    @classmethod
    def validate_current_status(cls, v):
        """状态验证器 - 确保值在允许范围内"""
        if v is None:
            return "提案中"  # 默认状态

        # 数据库允许的状态值
        allowed_statuses = [
            "提案中",
            "事前面談",
            "面談",
            "結果待ち",
            "契約中",
            "営業終了",
            "アーカイブ",
        ]

        v_str = str(v)
        if v_str in allowed_statuses:
            return v_str

        # 状态映射
        status_mappings = {
            "新規": "提案中",
            "提案": "提案中",
            "面接": "面談",
            "面接中": "面談",
            "結果": "結果待ち",
            "契約": "契約中",
            "終了": "営業終了",
            "完了": "営業終了",
        }

        for key, mapped_status in status_mappings.items():
            if key in v_str:
                return mapped_status

        # 默认返回"提案中"
        return "提案中"

    @field_validator("preferred_work_style")
    @classmethod
    def validate_preferred_work_style(cls, v):
        """希望勤务形态验证器"""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return []

    @field_validator("preferred_locations")
    @classmethod
    def validate_preferred_locations(cls, v):
        """希望勤务地验证器"""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return []

    @field_validator("certifications")
    @classmethod
    def validate_certifications(cls, v):
        """资格验证器"""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return []

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, v):
        """技能验证器"""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return []

    @field_validator("technical_keywords")
    @classmethod
    def validate_technical_keywords(cls, v):
        """技术关键词验证器"""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return []

    @field_validator("desired_rate_min", "desired_rate_max")
    @classmethod
    def validate_rate(cls, v):
        """单价验证器 - 处理字符串数字"""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            # 尝试从字符串中提取数字
            import re

            numbers = re.findall(r"\d+", v)
            if numbers:
                return int(numbers[0])
            return None
        return None

    @field_validator("overtime_available", "business_trip_available")
    @classmethod
    def validate_boolean(cls, v):
        """布尔值验证器"""
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "yes", "可能", "可", "ok", "対応可能", "はい")
        return False


class EmailProcessor:
    def __init__(self, db_config: Dict, ai_config: Dict):
        self.db_config = db_config
        self.ai_config = ai_config
        self.db_pool: Optional[asyncpg.Pool] = None
        self.ai_client: Optional[
            AsyncOpenAI | httpx.AsyncClient | NoAuthCustomAPIProcessor
        ] = None

        # 初始化分类器和附件处理器
        self.classifier = EmailClassifier(ai_config)
        self.attachment_processor = AttachmentProcessor(ai_config)

        provider_name = self.ai_config.get("provider_name")
        api_key = self.ai_config.get("api_key")
        api_base_url = self.ai_config.get("api_base_url")
        require_auth = self.ai_config.get("require_auth", True)

        if provider_name == "openai":
            if api_key:
                self.ai_client = AsyncOpenAI(api_key=api_key)
            else:
                logger.error("OpenAI API key not found in config")
        elif provider_name == "deepseek":
            timeout = self.ai_config.get("timeout", 120.0)
            if api_key and api_base_url:
                self.ai_client = httpx.AsyncClient(
                    base_url=api_base_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=timeout,
                )
                logger.info("DeepSeek client initialized")
            else:
                logger.error("DeepSeek API key or base URL not found")
        elif provider_name == "custom":
            timeout = self.ai_config.get("timeout", 120.0)
            default_model = self.ai_config.get("default_model", "default")

            if api_base_url:
                if require_auth and api_key:
                    # 需要认证的自定义API
                    self.ai_client = httpx.AsyncClient(
                        base_url=api_base_url,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        timeout=timeout,
                    )
                    logger.info("Custom API client initialized (with auth)")
                elif not require_auth:
                    # 无需认证的自定义API
                    self.ai_client = NoAuthCustomAPIProcessor(
                        api_base_url=api_base_url,
                        default_model=default_model,
                        timeout=timeout,
                    )
                    logger.info("Custom API client initialized (no auth)")
                else:
                    logger.error("Custom API requires auth but no API key provided")
            else:
                logger.error("Custom API base URL not found")

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

            logger.warning(f"Could not extract JSON from text: {text[:200]}...")
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
                decrypted_password = None
                try:
                    if row["smtp_password_encrypted"]:
                        password_data = row["smtp_password_encrypted"]

                        # 处理text类型字段
                        if isinstance(password_data, str):
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
                            decrypted_password = decrypt(
                                password_data, Config.ENCRYPTION_KEY
                            )
                        else:
                            logger.error(
                                f"Unexpected password data type {type(password_data)}"
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
                    try:
                        # 🔧 修复：正确解码文件名
                        decoded_filename = ""
                        if filename:
                            # 解码可能编码的文件名
                            try:
                                decoded_parts = decode_header(filename)
                                for part_content, part_encoding in decoded_parts:
                                    if isinstance(part_content, bytes):
                                        if part_encoding:
                                            decoded_filename += part_content.decode(
                                                part_encoding
                                            )
                                        else:
                                            # 尝试常见编码
                                            for encoding in [
                                                "utf-8",
                                                "gbk",
                                                "shift_jis",
                                                "iso-2022-jp",
                                            ]:
                                                try:
                                                    decoded_filename += (
                                                        part_content.decode(encoding)
                                                    )
                                                    break
                                                except UnicodeDecodeError:
                                                    continue
                                            else:
                                                # 如果所有编码都失败，使用errors='replace'
                                                decoded_filename += part_content.decode(
                                                    "utf-8", errors="replace"
                                                )
                                    else:
                                        decoded_filename += str(part_content)
                            except Exception as decode_error:
                                logger.warning(
                                    f"文件名解码失败: {filename}, 错误: {decode_error}"
                                )
                                decoded_filename = filename  # 使用原始文件名作为后备

                        # 添付ファイルの内容を取得
                        file_content = part.get_payload(decode=True)
                        attachment_data = {
                            "filename": decoded_filename,  # 🔧 使用解码后的文件名
                            "original_filename": filename,  # 保留原始文件名用于调试
                            "content_type": content_type,
                            "size": len(file_content) if file_content else 0,
                            "content": file_content,  # バイナリ内容を保存
                        }
                        attachments.append(attachment_data)

                        # 🔧 改进日志，显示解码前后的文件名
                        logger.info(
                            f"添付ファイル取得: {decoded_filename} "
                            f"(原始: {filename if filename != decoded_filename else '同じ'}) "
                            f"({len(file_content)} bytes)"
                        )

                    except Exception as e:
                        logger.error(f"添付ファイル処理エラー {filename}: {e}")

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
        model_extract = self.ai_config.get("model_extract", "gpt-4")
        temperature = self.ai_config.get("temperature", 0.3)
        max_tokens_extract = self.ai_config.get("max_tokens", 2048)

        # 使用分类器的智能内容提取
        extracted_content = self.classifier.smart_content_extraction(email_data)

        prompt = f"""
            以下のメールから案件情報を抽出して、必ずJSON形式で返してください。他の説明は不要です。

            件名: {email_data['subject']}
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
                "foreigner_accepted": "外国人受入可能（true/false）",
                "freelancer_accepted": "フリーランス受入可能（true/false）",
                "interview_count": "面接回数",
                "processes": ["工程1", "工程2"],
                "max_candidates": "最大候補者数",
                "manager_name": "担当者名",
                "manager_email": "担当者メール"
            }}
            
            重要：
            - start_dateは必ずYYYY-MM-DD形式で返してください
            - 開始日が即日・すぐ等の場合は現在の日付を使用してください
            - 情報が見つからない項目はnullにしてください
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
            if provider_name == "openai":
                response = await self.ai_client.chat.completions.create(
                    model=model_extract,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens_extract,
                )
                raw_content = response.choices[0].message.content
                data = self._extract_json_from_text(raw_content)

            elif provider_name in ["deepseek", "custom"]:
                if isinstance(self.ai_client, httpx.AsyncClient):
                    response = await self.ai_client.post(
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

            if data:
                # 处理日期格式，如果没有开始日期，默认为当前日期
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

                return ProjectStructured(**data)

        except Exception as e:
            logger.error(f"Error extracting project info: {e}")
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
            # 添付ファイル情報をJSONとして保存（バイナリ内容は除く）
            attachments_json = []
            for attachment in email_data.get("attachments", []):
                attachment_info = {
                    "filename": attachment.get("filename"),
                    "content_type": attachment.get("content_type"),
                    "size": attachment.get("size"),
                }
                attachments_json.append(attachment_info)

            email_id = await conn.fetchval(
                """
                    INSERT INTO receive_emails (
                        tenant_id, subject, body_text, body_html,
                        sender_name, sender_email, email_type,
                        processing_status, ai_extracted_data,
                        received_at, attachments
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
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
                json.dumps(attachments_json),
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
                    # 处理开始日期
                    start_date_value = None
                    if project_data.start_date:
                        try:
                            start_date_value = datetime.strptime(
                                project_data.start_date, "%Y-%m-%d"
                            ).date()
                        except ValueError:
                            start_date_value = date.today()
                    else:
                        start_date_value = date.today()

                    # 处理应募截止日期
                    application_deadline_value = None
                    if project_data.application_deadline:
                        try:
                            application_deadline_value = datetime.strptime(
                                project_data.application_deadline, "%Y-%m-%d"
                            ).date()
                        except ValueError:
                            pass

                    project_id = await conn.fetchval(
                        """
                            INSERT INTO projects (
                                tenant_id, title, client_company, partner_company,
                                description, detail_description, skills, key_technologies,
                                location, work_type, start_date, duration,
                                application_deadline, budget, desired_budget,
                                japanese_level, experience, foreigner_accepted,
                                freelancer_accepted, interview_count, processes,
                                max_candidates, manager_name, manager_email,
                                company_type, source, ai_processed, status, 
                                created_at, registered_at
                            ) VALUES (
                                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                                $13, $14, $15, $16, $17, $18, $19, $20, $21, $22,
                                $23, $24, '他社', 'mail_import', true, '募集中',
                                $25, $25
                            )
                            RETURNING id
                        """,
                        tenant_id,
                        project_data.title,
                        project_data.client_company,
                        project_data.partner_company,
                        project_data.description,
                        project_data.detail_description,
                        project_data.skills or [],
                        project_data.key_technologies,
                        project_data.location,
                        project_data.work_type,
                        start_date_value,
                        project_data.duration,
                        application_deadline_value,
                        project_data.budget,
                        project_data.desired_budget,
                        project_data.japanese_level,
                        project_data.experience,
                        project_data.foreigner_accepted or False,
                        project_data.freelancer_accepted or False,
                        project_data.interview_count or "1",
                        project_data.processes or [],
                        project_data.max_candidates or 5,
                        project_data.manager_name,
                        project_data.manager_email or sender_email,
                        datetime.now(),
                    )

                    await conn.execute(
                        """
                            UPDATE receive_emails 
                            SET project_id = $1, processing_status = $2, ai_extraction_status = 'completed'
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
                            SET processing_status = $1, ai_extraction_status = 'failed', processing_error = $2
                            WHERE id = $3
                        """,
                        ProcessingStatus.ERROR.value,
                        str(e),
                        email_id,
                    )
                    return None

    async def save_engineer_from_resume(
        self, tenant_id: str, resume_data: ResumeData, email_id: str, sender_email: str
    ) -> Optional[str]:
        """简历数据保存为工程师信息"""
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                try:
                    engineer_id = await conn.fetchval(
                        """
                            INSERT INTO engineers (
                                tenant_id, name, email, phone, gender, age,
                                nationality, nearest_station, education,
                                arrival_year_japan, certifications, skills,
                                technical_keywords, experience, work_scope,
                                work_experience, japanese_level, english_level,
                                availability, preferred_work_style, preferred_locations,
                                desired_rate_min, desired_rate_max, overtime_available,
                                business_trip_available, self_promotion, remarks,
                                recommendation, company_type, source, current_status,
                                resume_text, created_at
                            ) VALUES (
                                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                                $13, $14, $15, $16, $17, $18, $19, $20, $21, $22,
                                $23, $24, $25, $26, $27, $28, '他社', 'mail', '提案中',
                                $29, $30
                            )
                            RETURNING id
                        """,
                        tenant_id,
                        resume_data.name,
                        resume_data.email or sender_email,
                        resume_data.phone,
                        resume_data.gender,
                        resume_data.age,
                        resume_data.nationality,
                        resume_data.nearest_station,
                        resume_data.education,
                        resume_data.arrival_year_japan,
                        resume_data.certifications or [],
                        resume_data.skills or [],
                        resume_data.technical_keywords or [],
                        resume_data.experience,
                        resume_data.work_scope,
                        resume_data.work_experience,
                        resume_data.japanese_level,
                        resume_data.english_level,
                        resume_data.availability,
                        resume_data.preferred_work_style or [],
                        resume_data.preferred_locations or [],
                        resume_data.desired_rate_min,
                        resume_data.desired_rate_max,
                        resume_data.overtime_available or False,
                        resume_data.business_trip_available or False,
                        resume_data.self_promotion,
                        resume_data.remarks,
                        resume_data.recommendation,
                        f"从简历文件提取: {resume_data.source_filename}",
                        datetime.now(),
                    )

                    logger.info(
                        f"Engineer from resume saved successfully: {engineer_id} ({resume_data.name})"
                    )
                    return str(engineer_id)

                except Exception as e:
                    logger.error(
                        f"Error saving engineer from resume {resume_data.name}: {e}"
                    )
                    return None

    async def extract_engineer_info(
        self, email_data: Dict
    ) -> Optional[EngineerStructured]:
        """メールから技術者情報を抽出（邮件本文）- 改进版本，使用标准化提示词"""
        if not self.ai_client:
            return None

        provider_name = self.ai_config.get("provider_name")
        model_extract = self.ai_config.get("model_extract", "gpt-4")
        temperature = self.ai_config.get("temperature", 0.3)
        max_tokens_extract = self.ai_config.get("max_tokens", 2048)

        extracted_content = self.classifier.smart_content_extraction(email_data)

        # 使用改进的提示词，明确数据库约束
        prompt = f"""
            以下のメールから技術者情報を抽出して、必ずJSON形式で返してください。

            件名: {email_data.get('subject', '')}
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

            言語レベル変換例：
            - "日本語1級", "N1", "流暢", "ほぼ流暢" → "ネイティブレベル"
            - "日本語2級", "N2", "ビジネス" → "ビジネスレベル"  
            - "日本語3級", "N3", "会話", "基本" → "日常会話レベル"
            - 不明・記載なし → "不問"

            例：
            {{
                "name": "燕",
                "age": "27",
                "gender": "男性",
                "japanese_level": "ビジネスレベル",
                "english_level": "不問",
                "skills": ["Java", "Spring Boot", "JavaScript"],
                "preferred_work_style": [],
                "preferred_locations": [],
                "desired_rate_min": 48,
                "desired_rate_max": null,
                "overtime_available": false,
                "business_trip_available": false
            }}
            """

        messages = [
            {
                "role": "system",
                "content": "あなたは技術者情報抽出の専門家です。データベース制約を厳密に守り、必ずJSONのみを返してください。",
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
                )
                raw_content = response.choices[0].message.content
                data = self._extract_json_from_text(raw_content)

            elif provider_name in ["deepseek", "custom"]:
                if isinstance(self.ai_client, httpx.AsyncClient):
                    response = await self.ai_client.post(
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

            if data:
                logger.info(f"AI提取的原始数据: {data}")
                # 使用更新的验证器创建EngineerStructured实例
                engineer_data = EngineerStructured(**data)
                logger.info(f"成功提取并验证工程师数据: {engineer_data.name}")
                return engineer_data

        except Exception as e:
            logger.error(f"Error extracting engineer info: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None

    async def save_engineer(
        self,
        tenant_id: str,
        engineer_data: EngineerStructured,
        email_id: str,
        sender_email: str,
    ) -> Optional[str]:
        """技術者情報をデータベースに保存（邮件正文提取）"""
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                try:
                    engineer_id = await conn.fetchval(
                        """
                            INSERT INTO engineers (
                                tenant_id, name, email, phone, gender, age,
                                nationality, nearest_station, education,
                                arrival_year_japan, certifications, skills,
                                technical_keywords, experience, work_scope,
                                work_experience, japanese_level, english_level,
                                availability, preferred_work_style, preferred_locations,
                                desired_rate_min, desired_rate_max, overtime_available,
                                business_trip_available, self_promotion, remarks,
                                recommendation, company_type, source, current_status,
                                created_at
                            ) VALUES (
                                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                                $13, $14, $15, $16, $17, $18, $19, $20, $21, $22,
                                $23, $24, $25, $26, $27, $28, '他社', 'mail', $29,
                                $30
                            )
                            RETURNING id
                        """,
                        tenant_id,
                        engineer_data.name,
                        engineer_data.email or sender_email,
                        engineer_data.phone,
                        engineer_data.gender,
                        engineer_data.age,
                        engineer_data.nationality,
                        engineer_data.nearest_station,
                        engineer_data.education,
                        engineer_data.arrival_year_japan,
                        engineer_data.certifications or [],
                        engineer_data.skills or [],
                        engineer_data.technical_keywords or [],
                        engineer_data.experience,
                        engineer_data.work_scope,
                        engineer_data.work_experience,
                        engineer_data.japanese_level,
                        engineer_data.english_level,
                        engineer_data.availability,
                        engineer_data.preferred_work_style or [],
                        engineer_data.preferred_locations or [],
                        engineer_data.desired_rate_min,
                        engineer_data.desired_rate_max,
                        engineer_data.overtime_available or False,
                        engineer_data.business_trip_available or False,
                        engineer_data.self_promotion,
                        engineer_data.remarks,
                        engineer_data.recommendation,
                        engineer_data.current_status or "提案中",
                        datetime.now(),
                    )

                    await conn.execute(
                        """
                            UPDATE receive_emails 
                            SET engineer_id = $1, processing_status = $2, ai_extraction_status = 'completed'
                            WHERE id = $3
                        """,
                        engineer_id,
                        ProcessingStatus.PROCESSED.value,
                        email_id,
                    )

                    logger.info(
                        f"Engineer saved successfully: {engineer_id} ({engineer_data.name})"
                    )
                    return str(engineer_id)

                except Exception as e:
                    logger.error(f"Error saving engineer: {e}")
                    await conn.execute(
                        """
                            UPDATE receive_emails 
                            SET processing_status = $1, ai_extraction_status = 'failed', processing_error = $2
                            WHERE id = $3
                        """,
                        ProcessingStatus.ERROR.value,
                        str(e),
                        email_id,
                    )
                    return None

    async def process_emails_for_tenant(self, tenant_id: str):
        """特定テナントのメール処理を実行"""
        settings_list = await self.get_smtp_settings(tenant_id)

        if not settings_list:
            logger.warning(f"No SMTP settings found for tenant: {tenant_id}")
            return

        for settings in settings_list:
            try:
                emails = await self.fetch_emails(settings)
                logger.info(f"Fetched {len(emails)} new emails for tenant {tenant_id}")

                for email_data in emails:
                    # 使用分类器进行邮件分类
                    email_type = await self.classifier.classify_email(email_data)
                    logger.info(f"Email classified as: {email_type.value}")

                    email_id = await self.save_email_to_db(
                        tenant_id, email_data, email_type, None
                    )

                    if email_type == EmailType.PROJECT_RELATED:
                        project_data = await self.extract_project_info(email_data)
                        if project_data:
                            await self.save_project(
                                tenant_id,
                                project_data,
                                email_id,
                                email_data["sender_email"],
                            )

                    elif email_type == EmailType.ENGINEER_RELATED:
                        # 检查是否有简历附件
                        attachments = email_data.get("attachments", [])
                        has_resume_attachments = (
                            self.attachment_processor.has_resume_attachments(
                                attachments
                            )
                        )

                        if has_resume_attachments:
                            logger.info(f"发现简历附件，开始处理...")
                            # 处理简历附件
                            resume_data_list = await self.attachment_processor.process_resume_attachments(
                                attachments
                            )

                            if resume_data_list:
                                logger.info(
                                    f"成功提取 {len(resume_data_list)} 份简历数据"
                                )
                                engineer_ids = []

                                # 保存每个简历数据
                                for resume_data in resume_data_list:
                                    engineer_id = await self.save_engineer_from_resume(
                                        tenant_id,
                                        resume_data,
                                        email_id,
                                        email_data["sender_email"],
                                    )
                                    if engineer_id:
                                        engineer_ids.append(engineer_id)

                                # 更新邮件状态
                                if engineer_ids:
                                    async with self.db_pool.acquire() as conn:
                                        await conn.execute(
                                            """
                                                UPDATE receive_emails 
                                                SET engineer_id = $1, processing_status = $2, ai_extraction_status = 'completed'
                                                WHERE id = $3
                                            """,
                                            engineer_ids[0],  # 使用第一个工程师ID
                                            ProcessingStatus.PROCESSED.value,
                                            email_id,
                                        )

                                logger.info(
                                    f"保存了 {len(engineer_ids)} 个工程师记录从简历附件"
                                )
                                continue
                            else:
                                logger.warning("简历附件处理失败，尝试从邮件正文提取")

                        # 如果没有简历附件或处理失败，从邮件正文提取
                        engineer_data = await self.extract_engineer_info(email_data)
                        if engineer_data:
                            await self.save_engineer(
                                tenant_id,
                                engineer_data,
                                email_id,
                                email_data["sender_email"],
                            )

                    else:
                        # OTHER或UNCLASSIFIED类型的邮件，只标记为已处理
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
    """バッチ処理用のメイン関数"""
    active_ai_config = Config.get_ai_config()

    processor = EmailProcessor(
        db_config=Config.get_db_config(), ai_config=active_ai_config
    )
    await processor.initialize()

    try:
        async with processor.db_pool.acquire() as conn:
            tenant_ids = await conn.fetch(
                """
                SELECT DISTINCT t.id 
                FROM tenants t
                INNER JOIN email_smtp_settings s ON s.tenant_id = t.id
                WHERE t.is_active = true AND s.is_active = true
            """
            )

        for row in tenant_ids:
            tenant_id = str(row["id"])
            logger.info(f"Processing emails for tenant: {tenant_id}")
            await processor.process_emails_for_tenant(tenant_id)

    except Exception as e:
        logger.error(f"Error in main processing: {e}")
    finally:
        await processor.close()


if __name__ == "__main__":
    asyncio.run(main())
