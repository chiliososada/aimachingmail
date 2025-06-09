# src/database/project_repository.py
"""项目相关数据库操作"""

import logging
from datetime import datetime, date
from typing import Optional

from src.models.data_models import ProjectStructured
from src.database.database_manager import db_manager

logger = logging.getLogger(__name__)


class ProjectRepository:
    """项目数据库操作类"""

    async def save_project(
        self,
        tenant_id: str,
        project_data: ProjectStructured,
        sender_email: str,
    ) -> Optional[str]:
        """保存项目信息到数据库"""
        async with db_manager.get_transaction() as conn:
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

                logger.info(f"Project saved successfully: {project_id}")
                return str(project_id)

            except Exception as e:
                logger.error(f"Error saving project: {e}")
                raise

    async def get_project_by_id(self, project_id: str) -> Optional[dict]:
        """根据ID获取项目信息"""
        async with db_manager.get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM projects
                WHERE id = $1 AND deleted_at IS NULL
                """,
                project_id,
            )

            if row:
                return dict(row)
            return None

    async def update_project_status(self, project_id: str, status: str):
        """更新项目状态"""
        async with db_manager.get_connection() as conn:
            await conn.execute(
                """
                UPDATE projects 
                SET status = $1, updated_at = $2
                WHERE id = $3
                """,
                status,
                datetime.now(),
                project_id,
            )


# 全局项目仓库实例
project_repository = ProjectRepository()
