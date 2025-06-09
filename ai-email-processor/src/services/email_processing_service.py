# src/services/email_processing_service.py
"""邮件处理服务 - 业务流程协调"""

import logging
from typing import List

from src.models.data_models import (
    EmailData,
    EmailType,
    ProcessingStatus,
    EmailProcessingResult,
)
from src.email_classifier import EmailClassifier
from src.ai_services.extraction_service import extraction_service
from src.attachment_processor import AttachmentProcessor
from src.database.email_repository import email_repository
from src.database.project_repository import project_repository
from src.database.engineer_repository import engineer_repository
from src.email.email_fetcher import email_fetcher
from src.config import Config

logger = logging.getLogger(__name__)


class EmailProcessingService:
    """邮件处理服务 - 协调整个邮件处理流程"""

    def __init__(self):
        # 获取各服务的AI配置
        classification_config = Config.get_ai_config_for_service("classification")
        attachment_config = Config.get_ai_config_for_service("attachment")

        # 初始化各个服务组件
        self.classifier = EmailClassifier(classification_config)
        self.extraction_service = extraction_service
        self.attachment_processor = AttachmentProcessor(attachment_config)

        # 数据库服务
        self.email_repo = email_repository
        self.project_repo = project_repository
        self.engineer_repo = engineer_repository

        # 邮件获取服务
        self.email_fetcher = email_fetcher

        logger.info("EmailProcessingService initialized with separated AI services")

    async def process_emails_for_tenant(
        self, tenant_id: str
    ) -> List[EmailProcessingResult]:
        """处理指定租户的邮件"""
        results = []

        # 获取租户的SMTP设置
        settings_list = await self.email_repo.get_smtp_settings(tenant_id)

        if not settings_list:
            logger.warning(f"No SMTP settings found for tenant: {tenant_id}")
            return results

        for settings in settings_list:
            try:
                # 获取新邮件
                emails = await self.email_fetcher.fetch_emails(settings)
                logger.info(f"Fetched {len(emails)} new emails for tenant {tenant_id}")

                for email_data_dict in emails:
                    try:
                        # 转换为EmailData对象
                        email_data = EmailData(**email_data_dict)

                        # 处理单个邮件
                        result = await self.process_single_email(tenant_id, email_data)
                        results.append(result)

                    except Exception as e:
                        logger.error(f"Error processing individual email: {e}")
                        # 创建错误结果
                        error_result = EmailProcessingResult(
                            email_id="error",
                            email_type=EmailType.UNCLASSIFIED,
                            processing_status=ProcessingStatus.ERROR,
                            error_message=str(e),
                        )
                        results.append(error_result)
                        continue

            except Exception as e:
                logger.error(f"Error processing emails for settings {settings.id}: {e}")
                continue

        return results

    async def process_single_email(
        self, tenant_id: str, email_data: EmailData
    ) -> EmailProcessingResult:
        """处理单个邮件"""
        email_id = None

        try:
            # 1. 邮件分类
            email_type = await self.classifier.classify_email(email_data.model_dump())
            logger.info(f"Email classified as: {email_type.value}")

            # 2. 保存邮件到数据库
            email_id = await self.email_repo.save_email(
                tenant_id=tenant_id, email_data=email_data, email_type=email_type
            )

            # 3. 根据邮件类型进行不同处理
            if email_type == EmailType.PROJECT_RELATED:
                return await self._process_project_email(
                    tenant_id, email_data, email_id
                )

            elif email_type == EmailType.ENGINEER_RELATED:
                return await self._process_engineer_email(
                    tenant_id, email_data, email_id
                )

            else:
                # OTHER或UNCLASSIFIED类型，只标记为已处理
                await self.email_repo.update_email_status(
                    email_id=email_id, processing_status=ProcessingStatus.PROCESSED
                )

                return EmailProcessingResult(
                    email_id=email_id,
                    email_type=email_type,
                    processing_status=ProcessingStatus.PROCESSED,
                )

        except Exception as e:
            logger.error(f"Error processing email {email_data.subject}: {e}")

            # 更新邮件状态为错误
            if email_id:
                await self.email_repo.update_email_status(
                    email_id=email_id,
                    processing_status=ProcessingStatus.ERROR,
                    error_message=str(e),
                )

            return EmailProcessingResult(
                email_id=email_id or "error",
                email_type=EmailType.UNCLASSIFIED,
                processing_status=ProcessingStatus.ERROR,
                error_message=str(e),
            )

    async def _process_project_email(
        self, tenant_id: str, email_data: EmailData, email_id: str
    ) -> EmailProcessingResult:
        """处理项目相关邮件"""
        try:
            # 提取项目信息
            extracted_content = self.classifier.smart_content_extraction(
                email_data.model_dump()
            )
            project_data = await self.extraction_service.extract_project_info(
                email_data, extracted_content
            )

            if project_data:
                # 保存项目信息
                project_id = await self.project_repo.save_project(
                    tenant_id=tenant_id,
                    project_data=project_data,
                    sender_email=email_data.sender_email,
                )

                if project_id:
                    # 更新邮件状态
                    await self.email_repo.update_email_status(
                        email_id=email_id,
                        processing_status=ProcessingStatus.PROCESSED,
                        project_id=project_id,
                    )

                    return EmailProcessingResult(
                        email_id=email_id,
                        email_type=EmailType.PROJECT_RELATED,
                        processing_status=ProcessingStatus.PROCESSED,
                        project_id=project_id,
                        ai_extracted_data=project_data.model_dump(),
                    )

            # 项目信息提取失败
            await self.email_repo.update_email_status(
                email_id=email_id,
                processing_status=ProcessingStatus.ERROR,
                ai_extraction_status="failed",
                error_message="Failed to extract project information",
            )

            return EmailProcessingResult(
                email_id=email_id,
                email_type=EmailType.PROJECT_RELATED,
                processing_status=ProcessingStatus.ERROR,
                error_message="Failed to extract project information",
            )

        except Exception as e:
            logger.error(f"Error processing project email: {e}")
            raise

    async def _process_engineer_email(
        self, tenant_id: str, email_data: EmailData, email_id: str
    ) -> EmailProcessingResult:
        """处理工程师相关邮件"""
        try:
            engineer_ids = []

            # 检查是否有简历附件
            attachments = email_data.attachments
            has_resume_attachments = self.attachment_processor.has_resume_attachments(
                attachments
            )

            if has_resume_attachments:
                logger.info("发现简历附件，开始处理...")

                # 处理简历附件
                resume_data_list = (
                    await self.attachment_processor.process_resume_attachments(
                        attachments
                    )
                )

                if resume_data_list:
                    logger.info(f"成功提取 {len(resume_data_list)} 份简历数据")

                    # 保存每个简历数据
                    for resume_data in resume_data_list:
                        engineer_id = (
                            await self.engineer_repo.save_engineer_from_resume(
                                tenant_id=tenant_id,
                                resume_data=resume_data,
                                sender_email=email_data.sender_email,
                            )
                        )
                        if engineer_id:
                            engineer_ids.append(engineer_id)

                    if engineer_ids:
                        # 更新邮件状态
                        await self.email_repo.update_email_status(
                            email_id=email_id,
                            processing_status=ProcessingStatus.PROCESSED,
                            engineer_id=engineer_ids[0],  # 使用第一个工程师ID
                        )

                        return EmailProcessingResult(
                            email_id=email_id,
                            email_type=EmailType.ENGINEER_RELATED,
                            processing_status=ProcessingStatus.PROCESSED,
                            engineer_ids=engineer_ids,
                        )
                else:
                    logger.warning("简历附件处理失败，尝试从邮件正文提取")

            # 如果没有简历附件或处理失败，从邮件正文提取
            extracted_content = self.classifier.smart_content_extraction(
                email_data.model_dump()
            )
            engineer_data = await self.extraction_service.extract_engineer_info(
                email_data, extracted_content
            )

            if engineer_data:
                # 保存工程师信息
                engineer_id = await self.engineer_repo.save_engineer(
                    tenant_id=tenant_id,
                    engineer_data=engineer_data,
                    sender_email=email_data.sender_email,
                )

                if engineer_id:
                    # 更新邮件状态
                    await self.email_repo.update_email_status(
                        email_id=email_id,
                        processing_status=ProcessingStatus.PROCESSED,
                        engineer_id=engineer_id,
                    )

                    return EmailProcessingResult(
                        email_id=email_id,
                        email_type=EmailType.ENGINEER_RELATED,
                        processing_status=ProcessingStatus.PROCESSED,
                        engineer_ids=[engineer_id],
                        ai_extracted_data=engineer_data.model_dump(),
                    )

            # 工程师信息提取失败
            await self.email_repo.update_email_status(
                email_id=email_id,
                processing_status=ProcessingStatus.ERROR,
                ai_extraction_status="failed",
                error_message="Failed to extract engineer information",
            )

            return EmailProcessingResult(
                email_id=email_id,
                email_type=EmailType.ENGINEER_RELATED,
                processing_status=ProcessingStatus.ERROR,
                error_message="Failed to extract engineer information",
            )

        except Exception as e:
            logger.error(f"Error processing engineer email: {e}")
            raise


# 全局邮件处理服务实例
email_processing_service = EmailProcessingService()
