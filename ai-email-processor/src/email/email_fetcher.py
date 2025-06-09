# src/email/email_fetcher.py
"""邮件获取器 - 负责从IMAP服务器获取邮件"""

import imaplib
import email
import logging
from typing import List

from src.models.data_models import SMTPSettings
from src.email.email_parser import EmailParser

logger = logging.getLogger(__name__)


class EmailFetcher:
    """邮件获取器"""

    def __init__(self):
        self.email_parser = EmailParser()

    async def fetch_emails(self, settings: SMTPSettings) -> List[dict]:
        """从邮件服务器获取新邮件"""
        emails = []

        try:
            # IMAP连接
            if settings.security_protocol == "SSL":
                mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
            else:
                mail = imaplib.IMAP4(settings.imap_host, settings.imap_port)

            mail.login(settings.smtp_username, settings.smtp_password)
            mail.select("INBOX")

            # 搜索未读邮件
            _, messages = mail.search(None, "UNSEEN")

            logger.info(
                f"Found {len(messages[0].split()) if messages[0] else 0} unread emails"
            )

            for msg_num in messages[0].split():
                try:
                    _, msg = mail.fetch(msg_num, "(RFC822)")

                    for response in msg:
                        if isinstance(response, tuple):
                            email_message = email.message_from_bytes(response[1])

                            # 解析邮件内容
                            email_data = await self.email_parser.parse_email(
                                email_message
                            )
                            emails.append(email_data)

                            # 标记为已读
                            mail.store(msg_num, "+FLAGS", "\\Seen")

                            logger.info(
                                f"Successfully fetched email: {email_data.get('subject', 'No Subject')}"
                            )

                except Exception as e:
                    logger.error(f"Error processing email {msg_num}: {e}")
                    continue

            mail.logout()
            logger.info(
                f"Successfully fetched {len(emails)} emails from {settings.imap_host}"
            )

        except Exception as e:
            logger.error(f"Error fetching emails from {settings.imap_host}: {e}")

        return emails

    async def test_connection(self, settings: SMTPSettings) -> bool:
        """测试IMAP连接"""
        try:
            if settings.security_protocol == "SSL":
                mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
            else:
                mail = imaplib.IMAP4(settings.imap_host, settings.imap_port)

            mail.login(settings.smtp_username, settings.smtp_password)
            mail.select("INBOX")
            mail.logout()

            logger.info(f"IMAP connection test successful for {settings.imap_host}")
            return True

        except Exception as e:
            logger.error(f"IMAP connection test failed for {settings.imap_host}: {e}")
            return False


# 全局邮件获取器实例
email_fetcher = EmailFetcher()
