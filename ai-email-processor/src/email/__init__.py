# src/email/__init__.py
"""邮件处理包"""

from .email_fetcher import EmailFetcher, email_fetcher
from .email_parser import EmailParser, email_parser

__all__ = ["EmailFetcher", "email_fetcher", "EmailParser", "email_parser"]
