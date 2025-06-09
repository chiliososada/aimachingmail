# src/__init__.py
"""AI Email Processor Package - 重构版本 - 修复导入路径"""

__version__ = "2.0.0"
__author__ = "AI Matching System"

# 主要组件导入
from .email_processor import EmailProcessor, main
from .models.data_models import (
    EmailType,
    ProcessingStatus,
    EmailData,
    ProjectStructured,
    EngineerStructured,
    SMTPSettings,
    EmailProcessingResult,
)
from .config import Config
from .email_classifier import EmailClassifier


# 服务组件导入（延迟导入以避免循环依赖）
def get_email_processing_service():
    from .services.email_processing_service import EmailProcessingService

    return EmailProcessingService


def get_ai_client_manager():
    from .ai_services.ai_client_manager import AIClientManager

    return AIClientManager


def get_extraction_service():
    from .ai_services.extraction_service import ExtractionService

    return ExtractionService


def get_database_manager():
    from .database.database_manager import DatabaseManager

    return DatabaseManager


def get_email_fetcher():
    from .email.email_fetcher import EmailFetcher

    return EmailFetcher


def get_email_parser():
    from .email.email_parser import EmailParser

    return EmailParser


# 数据库仓库导入（延迟导入）
def get_email_repository():
    from .database.email_repository import EmailRepository

    return EmailRepository


def get_project_repository():
    from .database.project_repository import ProjectRepository

    return ProjectRepository


def get_engineer_repository():
    from .database.engineer_repository import EngineerRepository

    return EngineerRepository


__all__ = [
    # 主要组件
    "EmailProcessor",
    "main",
    "Config",
    "EmailClassifier",
    # 数据模型
    "EmailType",
    "ProcessingStatus",
    "EmailData",
    "ProjectStructured",
    "EngineerStructured",
    "SMTPSettings",
    "EmailProcessingResult",
    # 服务组件获取函数
    "get_email_processing_service",
    "get_ai_client_manager",
    "get_extraction_service",
    "get_database_manager",
    "get_email_fetcher",
    "get_email_parser",
    # 数据库仓库获取函数
    "get_email_repository",
    "get_project_repository",
    "get_engineer_repository",
]
