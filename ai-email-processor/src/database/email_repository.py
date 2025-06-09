# src/database/email_repository.py
"""邮件相关数据库操作"""

import json
import logging
from typing import List, Dict, Optional
from datetime import datetime

from src.models.data_models import EmailData, EmailType, ProcessingStatus, SMTPSettings
from src.database.database_manager import db_manager
from src.encryption_utils import decrypt, DecryptionError
from src.config import Config

logger = logging.getLogger(__name__)


class EmailRepository:
    """邮件数据库操作类"""

    async def get_smtp_settings(self, tenant_id: str) -> List[SMTPSettings]:
        """获取租户的SMTP设置"""
        async with db_manager.get_connection() as conn:
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

    async def save_email(
        self,
        tenant_id: str,
        email_data: EmailData,
        email_type: EmailType,
        extracted_data: Optional[Dict] = None,
    ) -> str:
        """保存邮件到数据库"""
        async with db_manager.get_connection() as conn:
            # 附件信息转换为JSON（不包含二进制内容）
            attachments_json = []
            for attachment in email_data.attachments:
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
                    received_at, attachments, recipient_to,
                    recipient_cc, recipient_bcc
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                RETURNING id
                """,
                tenant_id,
                email_data.subject,
                email_data.body_text,
                email_data.body_html,
                email_data.sender_name,
                email_data.sender_email,
                email_type.value,
                ProcessingStatus.PROCESSING.value,
                json.dumps(extracted_data) if extracted_data else "{}",
                email_data.received_at,
                json.dumps(attachments_json),
                email_data.recipient_to,
                email_data.recipient_cc,
                email_data.recipient_bcc,
            )

            return str(email_id)

    async def update_email_status(
        self,
        email_id: str,
        processing_status: ProcessingStatus,
        ai_extraction_status: str = "completed",
        project_id: Optional[str] = None,
        engineer_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """更新邮件处理状态"""
        async with db_manager.get_connection() as conn:
            update_fields = ["processing_status = $2", "ai_extraction_status = $3"]
            params = [email_id, processing_status.value, ai_extraction_status]
            param_index = 4

            if project_id:
                update_fields.append(f"project_id = ${param_index}")
                params.append(project_id)
                param_index += 1

            if engineer_id:
                update_fields.append(f"engineer_id = ${param_index}")
                params.append(engineer_id)
                param_index += 1

            if error_message:
                update_fields.append(f"processing_error = ${param_index}")
                params.append(error_message)
                param_index += 1

            query = f"""
                UPDATE receive_emails 
                SET {', '.join(update_fields)}
                WHERE id = $1
            """

            await conn.execute(query, *params)

    async def get_active_tenant_ids(self) -> List[str]:
        """获取所有活跃租户ID"""
        async with db_manager.get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT t.id 
                FROM tenants t
                INNER JOIN email_smtp_settings s ON s.tenant_id = t.id
                WHERE t.is_active = true AND s.is_active = true
                """
            )

            return [str(row["id"]) for row in rows]


# 全局邮件仓库实例
email_repository = EmailRepository()
