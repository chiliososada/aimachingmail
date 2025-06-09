# src/database/engineer_repository.py
"""工程师相关数据库操作"""

import logging
from datetime import datetime
from typing import Optional, List

from src.models.data_models import EngineerStructured
from src.attachment_processor import ResumeData
from src.database.database_manager import db_manager

logger = logging.getLogger(__name__)


class EngineerRepository:
    """工程师数据库操作类"""

    async def save_engineer(
        self,
        tenant_id: str,
        engineer_data: EngineerStructured,
        sender_email: str,
    ) -> Optional[str]:
        """保存工程师信息到数据库（从邮件正文提取）"""
        async with db_manager.get_transaction() as conn:
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

                logger.info(
                    f"Engineer saved successfully: {engineer_id} ({engineer_data.name})"
                )
                return str(engineer_id)

            except Exception as e:
                logger.error(f"Error saving engineer: {e}")
                raise

    async def save_engineer_from_resume(
        self,
        tenant_id: str,
        resume_data: ResumeData,
        sender_email: str,
    ) -> Optional[str]:
        """保存工程师信息到数据库（从简历附件提取）"""
        async with db_manager.get_transaction() as conn:
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
                raise

    async def get_engineer_by_id(self, engineer_id: str) -> Optional[dict]:
        """根据ID获取工程师信息"""
        async with db_manager.get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM engineers
                WHERE id = $1 AND deleted_at IS NULL
                """,
                engineer_id,
            )

            if row:
                return dict(row)
            return None

    async def update_engineer_status(self, engineer_id: str, status: str):
        """更新工程师状态"""
        async with db_manager.get_connection() as conn:
            await conn.execute(
                """
                UPDATE engineers 
                SET current_status = $1, updated_at = $2
                WHERE id = $3
                """,
                status,
                datetime.now(),
                engineer_id,
            )

    async def search_engineers(
        self,
        tenant_id: str,
        skills: List[str] = None,
        japanese_level: str = None,
        limit: int = 10,
    ) -> List[dict]:
        """搜索工程师"""
        async with db_manager.get_connection() as conn:
            query = """
                SELECT id, name, email, skills, japanese_level, experience, current_status
                FROM engineers
                WHERE tenant_id = $1 AND deleted_at IS NULL AND is_active = true
            """
            params = [tenant_id]
            param_index = 2

            if skills:
                query += f" AND skills && ${param_index}"
                params.append(skills)
                param_index += 1

            if japanese_level:
                query += f" AND japanese_level = ${param_index}"
                params.append(japanese_level)
                param_index += 1

            query += f" ORDER BY created_at DESC LIMIT ${param_index}"
            params.append(limit)

            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]


# 全局工程师仓库实例
engineer_repository = EngineerRepository()
