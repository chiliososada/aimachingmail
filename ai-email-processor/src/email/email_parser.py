# src/email/email_parser.py
"""邮件解析器 - 负责解析邮件内容和附件"""

import logging
from datetime import datetime
from email.header import decode_header
from typing import Dict, List

from src.models.data_models import EmailData, AttachmentInfo

logger = logging.getLogger(__name__)


class EmailParser:
    """邮件解析器"""

    async def parse_email(self, msg) -> Dict:
        """解析邮件消息"""
        try:
            # 解析邮件头信息
            subject = self._decode_header(msg.get("Subject", ""))
            sender_name, sender_email = self._parse_sender(msg.get("From", ""))

            # 解析收件人信息
            recipient_to = self._parse_recipients(msg.get("To", ""))
            recipient_cc = self._parse_recipients(msg.get("Cc", ""))
            recipient_bcc = self._parse_recipients(msg.get("Bcc", ""))

            # 解析邮件正文和附件
            body_text, body_html, attachments = await self._parse_content(msg)

            # 创建EmailData对象
            email_data = EmailData(
                subject=subject,
                sender_name=sender_name,
                sender_email=sender_email,
                body_text=body_text,
                body_html=body_html,
                attachments=attachments,
                received_at=datetime.now(),
                recipient_to=recipient_to,
                recipient_cc=recipient_cc,
                recipient_bcc=recipient_bcc,
            )

            # 转换为字典返回（保持向后兼容）
            return email_data.model_dump()

        except Exception as e:
            logger.error(f"Error parsing email: {e}")
            # 返回最小化的邮件数据
            return {
                "subject": "Parse Error",
                "sender_name": "",
                "sender_email": "",
                "body_text": "",
                "body_html": "",
                "attachments": [],
                "received_at": datetime.now(),
                "recipient_to": [],
                "recipient_cc": [],
                "recipient_bcc": [],
            }

    def _decode_header(self, header_value: str) -> str:
        """解码邮件头部"""
        if not header_value:
            return ""

        try:
            decoded_parts = decode_header(header_value)
            result = ""

            for part_content, part_encoding in decoded_parts:
                if isinstance(part_content, bytes):
                    if part_encoding:
                        result += part_content.decode(part_encoding)
                    else:
                        # 尝试常见编码
                        for encoding in ["utf-8", "gbk", "shift_jis", "iso-2022-jp"]:
                            try:
                                result += part_content.decode(encoding)
                                break
                            except UnicodeDecodeError:
                                continue
                        else:
                            # 如果所有编码都失败，使用errors='replace'
                            result += part_content.decode("utf-8", errors="replace")
                else:
                    result += str(part_content)

            return result

        except Exception as e:
            logger.warning(f"Header decode failed for '{header_value}': {e}")
            return str(header_value)

    def _parse_sender(self, sender_field: str) -> tuple[str, str]:
        """解析发件人信息"""
        sender_name = ""
        sender_email = ""

        try:
            if "<" in sender_field and ">" in sender_field:
                sender_name = sender_field.split("<")[0].strip()
                sender_email = sender_field.split("<")[1].replace(">", "").strip()
                # 解码发件人姓名
                sender_name = self._decode_header(sender_name)
            else:
                sender_email = sender_field.strip()

        except Exception as e:
            logger.warning(f"Error parsing sender '{sender_field}': {e}")
            sender_email = sender_field

        return sender_name, sender_email

    def _parse_recipients(self, recipients_field: str) -> List[str]:
        """解析收件人列表"""
        if not recipients_field:
            return []

        try:
            # 简单的分割处理，可以根据需要扩展
            recipients = [email.strip() for email in recipients_field.split(",")]
            return [self._decode_header(recipient) for recipient in recipients]
        except Exception as e:
            logger.warning(f"Error parsing recipients '{recipients_field}': {e}")
            return [recipients_field]

    async def _parse_content(self, msg) -> tuple[str, str, List[Dict]]:
        """解析邮件内容和附件"""
        body_text = ""
        body_html = ""
        attachments = []

        try:
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    # 处理附件
                    attachment = await self._parse_attachment(part)
                    if attachment:
                        attachments.append(attachment)

                elif content_type == "text/plain" and not body_text:
                    # 处理纯文本内容
                    body_text = self._decode_content(part)

                elif content_type == "text/html" and not body_html:
                    # 处理HTML内容
                    body_html = self._decode_content(part)

        except Exception as e:
            logger.error(f"Error parsing email content: {e}")

        return body_text, body_html, attachments

    def _decode_content(self, part) -> str:
        """解码邮件内容部分"""
        try:
            payload = part.get_payload(decode=True)
            if payload:
                # 尝试多种编码
                for encoding in ["utf-8", "gbk", "shift_jis", "iso-2022-jp", "cp932"]:
                    try:
                        return payload.decode(encoding)
                    except UnicodeDecodeError:
                        continue

                # 如果所有编码都失败，使用utf-8并忽略错误
                return payload.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Error decoding content: {e}")

        return ""

    async def _parse_attachment(self, part) -> Dict:
        """解析附件"""
        try:
            filename = part.get_filename()
            if not filename:
                return None

            # 解码文件名
            decoded_filename = self._decode_header(filename)

            # 获取附件内容
            file_content = part.get_payload(decode=True)
            if not file_content:
                return None

            # 创建附件信息
            attachment_info = {
                "filename": decoded_filename,
                "original_filename": filename,
                "content_type": part.get_content_type(),
                "size": len(file_content),
                "content": file_content,  # 二进制内容
            }

            logger.info(
                f"Parsed attachment: {decoded_filename} "
                f"({'same' if filename == decoded_filename else f'original: {filename}'}) "
                f"({len(file_content)} bytes)"
            )

            return attachment_info

        except Exception as e:
            logger.error(f"Error parsing attachment: {e}")
            return None


# 全局邮件解析器实例
email_parser = EmailParser()
