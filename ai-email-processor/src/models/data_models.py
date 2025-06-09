# src/models/data_models.py
"""数据模型定义 - Pydantic模型"""

from datetime import datetime, date
from typing import List, Dict, Optional
from enum import Enum
from pydantic import BaseModel, Field, field_validator
import re
import logging

logger = logging.getLogger(__name__)


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    ERROR = "error"


class EmailType(str, Enum):
    PROJECT_RELATED = "project_related"
    ENGINEER_RELATED = "engineer_related"
    OTHER = "other"
    UNCLASSIFIED = "unclassified"


class SMTPSettings(BaseModel):
    """SMTP设置数据模型"""

    id: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    security_protocol: str
    from_email: str
    from_name: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = 993


class ProjectStructured(BaseModel):
    """构造化项目数据模型"""

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

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        """标题验证器"""
        if not v or v is None:
            return "案件名不明"
        return str(v)

    @field_validator("interview_count")
    @classmethod
    def validate_interview_count(cls, v):
        """面试回数验证器"""
        if v is None:
            return "1"
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str):
            return v
        return str(v)

    @field_validator("processes")
    @classmethod
    def validate_processes(cls, v):
        """工程列表验证器"""
        if v is None:
            return []
        if isinstance(v, list):
            return [str(item) for item in v if item is not None]
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return []

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, v):
        """技能列表验证器"""
        if v is None:
            return []
        if isinstance(v, list):
            return [str(item) for item in v if item is not None]
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return []

    @field_validator("max_candidates")
    @classmethod
    def validate_max_candidates(cls, v):
        """最大候选人数验证器"""
        if v is None:
            return 5
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return 5
        return 5

    @field_validator("foreigner_accepted", "freelancer_accepted")
    @classmethod
    def validate_boolean_fields(cls, v):
        """布尔字段验证器"""
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "yes", "可能", "可", "ok", "対応可能", "はい")
        return False

    @field_validator(
        "client_company",
        "partner_company",
        "description",
        "detail_description",
        "key_technologies",
        "location",
        "work_type",
        "start_date",
        "duration",
        "application_deadline",
        "budget",
        "desired_budget",
        "japanese_level",
        "experience",
        "manager_name",
        "manager_email",
    )
    @classmethod
    def validate_optional_string_fields(cls, v):
        """可选字符串字段验证器"""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return str(v)
        return str(v)


class EngineerStructured(BaseModel):
    """构造化工程师数据模型"""

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
        """姓名验证器"""
        if not v or v is None:
            return "名前不明"
        return str(v)

    @field_validator("experience")
    @classmethod
    def validate_experience(cls, v):
        """经验验证器"""
        if not v or v is None:
            return "不明"
        return str(v)

    @field_validator("age")
    @classmethod
    def validate_age(cls, v):
        """年龄字段验证器"""
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
        """电话号码验证器"""
        if v is None:
            return None
        return str(v)

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v):
        """性别验证器"""
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
        """语言水平验证器"""
        if v is None:
            return None

        v_str = str(v).lower()

        # 语言水平映射规则
        mappings = {
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
            logger.warning(f"无法识别的语言水平: '{v}'，默认设为日常会話レベル")
            return "日常会話レベル"

    @field_validator("current_status")
    @classmethod
    def validate_current_status(cls, v):
        """状态验证器"""
        if v is None:
            return "提案中"

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

        return "提案中"

    @field_validator(
        "preferred_work_style",
        "preferred_locations",
        "certifications",
        "skills",
        "technical_keywords",
    )
    @classmethod
    def validate_list_fields(cls, v):
        """列表字段验证器"""
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
        """单价验证器"""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str):
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


class EmailData(BaseModel):
    """邮件数据模型"""

    subject: str
    sender_name: str
    sender_email: str
    body_text: str
    body_html: str
    attachments: List[Dict] = Field(default_factory=list)
    received_at: datetime

    # 额外的邮件元数据
    recipient_to: List[str] = Field(default_factory=list)
    recipient_cc: List[str] = Field(default_factory=list)
    recipient_bcc: List[str] = Field(default_factory=list)


class AttachmentInfo(BaseModel):
    """附件信息模型"""

    filename: str
    original_filename: str
    content_type: str
    size: int
    content: bytes = Field(exclude=True)  # 在序列化时排除二进制内容

    class Config:
        arbitrary_types_allowed = True  # 允许bytes类型


class EmailProcessingResult(BaseModel):
    """邮件处理结果模型"""

    email_id: str
    email_type: EmailType
    processing_status: ProcessingStatus
    project_id: Optional[str] = None
    engineer_ids: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    ai_extracted_data: Optional[Dict] = None
