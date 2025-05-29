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

import asyncpg
from openai import AsyncOpenAI
import httpx
from pydantic import BaseModel, Field
from dotenv import load_dotenv

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
        self.ai_config = ai_config
        self.db_pool: Optional[asyncpg.Pool] = None
        self.openai_client = AsyncOpenAI(api_key=ai_config.get("openai_api_key"))

    async def initialize(self):
        """初期化処理"""
        self.db_pool = await asyncpg.create_pool(**self.db_config)
        logger.info("Database pool created successfully")

    async def close(self):
        """クリーンアップ処理"""
        if self.db_pool:
            await self.db_pool.close()

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
                # 実際のシステムでは暗号化されたパスワードを復号化する必要があります
                settings.append(
                    SMTPSettings(
                        id=str(row["id"]),
                        smtp_host=row["smtp_host"],
                        smtp_port=row["smtp_port"],
                        smtp_username=row["smtp_username"],
                        smtp_password=row["smtp_password_encrypted"],  # 要復号化
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

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたはメール分類の専門家です。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=50,
            )

            category = response.choices[0].message.content.strip().lower()

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
            "start_date": "開始日",
            "duration": "期間",
            "budget": "予算/単価",
            "japanese_level": "日本語レベル",
            "work_type": "勤務形態",
            "experience": "必要経験"
        }}
        
        情報が見つからない項目はnullにしてください。
        """

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "あなたは案件情報抽出の専門家です。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            data = json.loads(response.choices[0].message.content)
            return ProjectStructured(**data)

        except Exception as e:
            logger.error(f"Error extracting project info: {e}")
            return None

    async def extract_engineer_info(
        self, email_data: Dict
    ) -> Optional[EngineerStructured]:
        """メールから技術者情報を抽出して構造化"""
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
        
        情報が見つからない項目はnullにしてください。
        """

        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "あなたは技術者情報抽出の専門家です。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            data = json.loads(response.choices[0].message.content)
            return EngineerStructured(**data)

        except Exception as e:
            logger.error(f"Error extracting engineer info: {e}")
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
            try:
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
                        $7::date, $8, $9, $10, $11, $12,
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
                    (
                        datetime.strptime(project_data.start_date, "%Y-%m-%d").date()
                        if project_data.start_date
                        else None
                    ),
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
    ai_config = {
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY"),  # DeepSeek使用時
    }

    # プロセッサーの初期化
    processor = EmailProcessor(db_config, ai_config)
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
