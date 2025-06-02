# src/email_processor.py
import os
import json
import imaplib
import email
from email.header import decode_header
from datetime import datetime
import asyncio
import logging
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import asyncpg
from openai import AsyncOpenAI
import httpx
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from src.encryption_utils import decrypt, DecryptionError
from src.config import Config

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


@dataclass
class ClassificationResult:
    """分类结果包含置信度和详细信息"""

    email_type: EmailType
    confidence: float
    reasoning: str
    keywords_found: List[str]
    method: str = "improved"


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
        self.ai_client: Optional[AsyncOpenAI | httpx.AsyncClient] = None

        provider_name = self.ai_config.get("provider_name")
        api_key = self.ai_config.get("api_key")

        if provider_name == "openai":
            if api_key:
                self.ai_client = AsyncOpenAI(api_key=api_key)
            else:
                logger.error(
                    "OpenAI API key not found in config. OpenAI client not initialized."
                )
        elif provider_name == "deepseek":
            api_base_url = self.ai_config.get("api_base_url")
            timeout = self.ai_config.get("timeout", 120.0)
            if api_key and api_base_url:
                self.ai_client = httpx.AsyncClient(
                    base_url=api_base_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=timeout,
                )
                logger.info(
                    f"DeepSeek client initialized with base URL: {api_base_url}, timeout: {timeout}s"
                )
            else:
                logger.warning(
                    "DeepSeek API key or base URL not found. DeepSeek client not initialized."
                )
        else:
            logger.error(
                f"Unsupported AI provider: {provider_name}. No AI client initialized."
            )

        # 初始化改进的分类器组件
        self._init_classification_components()

    def _init_classification_components(self):
        """初始化分类器相关组件"""
        # 关键词词典
        self.keywords = {
            "project_related": {
                "高权重": [
                    "案件",
                    "プロジェクト",
                    "開発案件",
                    "求人",
                    "募集",
                    "参画",
                    "Java開発",
                    "Python開発",
                    "システム開発",
                    "WEB開発",
                    "単価",
                    "稼働",
                    "常駐",
                    "リモート",
                    "フリーランス",
                    "必須スキル",
                    "歓迎スキル",
                    "経験年数",
                    "即日開始",
                ],
                "中权重": [
                    "技術",
                    "スキル",
                    "経験",
                    "開発",
                    "設計",
                    "構築",
                    "保守",
                    "運用",
                    "テスト",
                    "データベース",
                    "API",
                    "クラウド",
                    "インフラ",
                    "セキュリティ",
                ],
            },
            "engineer_related": {
                "高权重": [
                    "エンジニア",
                    "技術者",
                    "開発者",
                    "プログラマー",
                    "履歴書",
                    "職務経歴書",
                    "スキルシート",
                    "経歴書",
                    "自己紹介",
                    "プロフィール",
                    "ポートフォリオ",
                    "希望単価",
                    "稼働可能",
                    "参画希望",
                ],
                "中权重": [
                    "経験年数",
                    "開発経験",
                    "プロジェクト経験",
                    "業務経歴",
                    "得意分野",
                    "専門分野",
                    "資格",
                    "認定",
                    "学歴",
                ],
            },
        }

        # 排除关键词
        self.exclusion_keywords = [
            "広告",
            "宣伝",
            "PR",
            "セール",
            "キャンペーン",
            "限定オファー",
            "今すぐクリック",
            "特別価格",
            "無料",
            "プレゼント",
        ]

        # 发件人域名模式
        self.sender_patterns = {
            "recruiting": ["recruit", "hr", "jinzai", "career", "agent"],
            "suspicious": ["noreply", "spam", "promo", "marketing", "no-reply"],
        }

    async def initialize(self):
        """初期化処理"""
        self.db_pool = await asyncpg.create_pool(**self.db_config)
        logger.info("Database pool created successfully")

    async def close(self):
        """クリーンアップ処理"""
        if self.db_pool:
            await self.db_pool.close()

    def _extract_json_from_text(self, text: str) -> Optional[Dict]:
        """テキストからJSON部分を抽出する"""
        logger.debug(f"Attempting to extract JSON from text: {text[:500]}...")

        try:
            result = json.loads(text.strip())
            logger.debug("Direct JSON parsing successful")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"Direct JSON parsing failed: {e}")
            json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
            matches = re.findall(json_pattern, text, re.DOTALL)

            logger.debug(f"Found {len(matches)} potential JSON matches")

            for i, match in enumerate(matches):
                logger.debug(f"Trying match {i+1}: {match[:100]}...")
                try:
                    result = json.loads(match)
                    logger.debug(f"Match {i+1} parsed successfully")
                    return result
                except json.JSONDecodeError:
                    logger.debug(f"Match {i+1} failed to parse")
                    continue

            start_idx = text.find("{")
            if start_idx != -1:
                logger.debug(
                    f"Trying complex JSON extraction starting at position {start_idx}"
                )
                brace_count = 0
                for i, char in enumerate(text[start_idx:], start_idx):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            try:
                                extracted = text[start_idx : i + 1]
                                logger.debug(
                                    f"Extracted complex JSON: {extracted[:100]}..."
                                )
                                result = json.loads(extracted)
                                logger.debug("Complex JSON extraction successful")
                                return result
                            except json.JSONDecodeError:
                                logger.debug("Complex JSON extraction failed")
                                break

            logger.warning(f"Could not extract JSON from text: {text[:200]}...")
            return None

    def _parse_date_string(self, date_str: str) -> Optional[str]:
        """日期字符串解析和标准化"""
        if not date_str or date_str.strip() == "":
            return None

        date_str = date_str.strip()

        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                return date_str
            except ValueError:
                logger.warning(f"Invalid standard date format: {date_str}")
                return None

        try:
            match = re.match(r"(\d{4})年(\d{1,2})月?(?:(\d{1,2})日?)?", date_str)
            if match:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3)) if match.group(3) else 1

                if 1 <= month <= 12 and 1 <= day <= 31:
                    formatted_date = f"{year:04d}-{month:02d}-{day:02d}"
                    try:
                        datetime.strptime(formatted_date, "%Y-%m-%d")
                        logger.info(
                            f"Converted date '{date_str}' to '{formatted_date}'"
                        )
                        return formatted_date
                    except ValueError:
                        logger.warning(f"Invalid converted date: {formatted_date}")
                        return None

            match = re.match(r"(\d{4})[/-](\d{1,2})(?:[/-](\d{1,2}))?", date_str)
            if match:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3)) if match.group(3) else 1

                if 1 <= month <= 12 and 1 <= day <= 31:
                    formatted_date = f"{year:04d}-{month:02d}-{day:02d}"
                    try:
                        datetime.strptime(formatted_date, "%Y-%m-%d")
                        logger.info(
                            f"Converted date '{date_str}' to '{formatted_date}'"
                        )
                        return formatted_date
                    except ValueError:
                        logger.warning(f"Invalid converted date: {formatted_date}")
                        return None

            logger.warning(f"Unable to parse date format: {date_str}")
            return None

        except Exception as e:
            logger.error(f"Error parsing date '{date_str}': {e}")
            return None

    # ===============================
    # 改进的邮件分类相关方法
    # ===============================

    def analyze_sender_info(self, email_data: Dict) -> Dict:
        """分析发件人信息"""
        sender_email = email_data.get("sender_email", "").lower()
        sender_name = email_data.get("sender_name", "").lower()

        analysis = {"domain_type": "unknown", "confidence": 0.0, "indicators": []}

        if "@" in sender_email:
            domain = sender_email.split("@")[1]

            # 检查招聘相关域名
            for pattern in self.sender_patterns["recruiting"]:
                if pattern in domain or pattern in sender_name:
                    analysis["domain_type"] = "recruiting"
                    analysis["confidence"] = 0.7
                    analysis["indicators"].append(f"recruiting_domain:{pattern}")
                    break

            # 检查可疑域名
            for pattern in self.sender_patterns["suspicious"]:
                if pattern in domain:
                    analysis["domain_type"] = "suspicious"
                    analysis["confidence"] = 0.8
                    analysis["indicators"].append(f"suspicious_domain:{pattern}")
                    break

        return analysis

    def analyze_attachments(self, email_data: Dict) -> Dict:
        """分析附件信息"""
        attachments = email_data.get("attachments", [])

        analysis = {
            "total_count": len(attachments),
            "engineer_indicators": [],
            "project_indicators": [],
            "confidence": 0.0,
            "strong_type": None,
        }

        if not attachments:
            return analysis

        engineer_patterns = [
            r"履歴書",
            r"職務経歴",
            r"スキルシート",
            r"resume",
            r"cv",
            r"profile",
        ]
        project_patterns = [r"案件", r"project", r"proposal", r"詳細", r"仕様", r"要件"]

        for attachment in attachments:
            filename = attachment.get("filename", "").lower()

            # 检查工程师相关附件
            for pattern in engineer_patterns:
                if re.search(pattern, filename):
                    analysis["engineer_indicators"].append(filename)
                    analysis["confidence"] = 0.9
                    analysis["strong_type"] = "engineer_related"

            # 检查项目相关附件
            for pattern in project_patterns:
                if re.search(pattern, filename):
                    analysis["project_indicators"].append(filename)
                    if analysis["confidence"] < 0.8:
                        analysis["confidence"] = 0.8
                        analysis["strong_type"] = "project_related"

        return analysis

    def smart_content_extraction(self, email_data: Dict) -> str:
        """智能内容提取 - 不限于1000字符"""
        subject = email_data.get("subject", "")
        body_text = email_data.get("body_text", "")
        body_html = email_data.get("body_html", "")

        # 如果没有纯文本，尝试从HTML提取
        if not body_text and body_html:
            body_text = re.sub(r"<[^>]+>", "", body_html)

        # 智能截取策略
        if len(body_text) <= 2000:
            extracted_content = body_text
        else:
            head_part = body_text[:800]

            # 查找包含关键词的重要段落
            important_keywords = [
                "案件",
                "プロジェクト",
                "開発",
                "必須スキル",
                "単価",
                "期間",
                "場所",
                "エンジニア",
                "履歴書",
                "経験",
                "希望",
                "技術者",
                "スキル",
                "資格",
            ]

            important_parts = []
            lines = body_text.split("\n")

            for i, line in enumerate(lines):
                line_score = sum(1 for keyword in important_keywords if keyword in line)
                if line_score >= 2:
                    start_idx = max(0, i - 1)
                    end_idx = min(len(lines), i + 2)
                    context = "\n".join(lines[start_idx:end_idx])
                    important_parts.append(context)

            tail_part = body_text[-300:] if len(body_text) > 300 else ""

            extracted_content = head_part
            if important_parts:
                extracted_content += "\n\n【重要段落】\n" + "\n".join(
                    important_parts[:2]
                )
            if tail_part:
                extracted_content += "\n\n【末尾部分】\n" + tail_part

        return extracted_content

    def calculate_keyword_score(
        self, text: str, email_type: str
    ) -> Tuple[float, List[str]]:
        """计算关键词得分"""
        if email_type not in self.keywords:
            return 0.0, []

        found_keywords = []
        score = 0.0
        text_lower = text.lower()

        keywords_dict = self.keywords[email_type]

        # 高权重关键词
        for keyword in keywords_dict["高权重"]:
            if keyword in text_lower:
                score += 3.0
                found_keywords.append(f"高:{keyword}")

        # 中权重关键词
        for keyword in keywords_dict["中权重"]:
            if keyword in text_lower:
                score += 1.5
                found_keywords.append(f"中:{keyword}")

        return score, found_keywords

    def check_spam_indicators(self, email_data: Dict) -> bool:
        """检查垃圾邮件指标"""
        subject = email_data.get("subject", "").lower()
        body_text = email_data.get("body_text", "").lower()
        sender_email = email_data.get("sender_email", "").lower()

        combined_text = f"{subject} {body_text}"

        spam_count = sum(
            1 for keyword in self.exclusion_keywords if keyword in combined_text
        )
        sender_suspicious = any(
            pattern in sender_email for pattern in self.sender_patterns["suspicious"]
        )

        return spam_count >= 2 or sender_suspicious

    async def classify_email(self, email_data: Dict) -> EmailType:
        """改进的邮件分类方法"""
        try:
            # 1. 垃圾邮件检测
            if self.check_spam_indicators(email_data):
                logger.info("检测到垃圾邮件特征，分类为unclassified")
                return EmailType.UNCLASSIFIED

            # 2. 附件分析
            attachment_analysis = self.analyze_attachments(email_data)
            if attachment_analysis["confidence"] > 0.8:
                logger.info(
                    f"强附件指标检测: {attachment_analysis['strong_type']}, 置信度: {attachment_analysis['confidence']:.2f}"
                )
                return EmailType(attachment_analysis["strong_type"])

            # 3. 智能内容分析
            extracted_content = self.smart_content_extraction(email_data)

            # 关键词分析
            project_score, project_keywords = self.calculate_keyword_score(
                extracted_content, "project_related"
            )
            engineer_score, engineer_keywords = self.calculate_keyword_score(
                extracted_content, "engineer_related"
            )

            # 发件人分析
            sender_analysis = self.analyze_sender_info(email_data)

            # 4. 高置信度关键词判断
            if project_score > engineer_score + 2.0 and project_score > 4.0:
                confidence = min(0.9, 0.7 + project_score * 0.03)
                if sender_analysis["domain_type"] == "recruiting":
                    confidence = min(0.95, confidence + 0.1)

                logger.info(
                    f"项目关键词高分: {project_score}, 置信度: {confidence:.2f}"
                )
                logger.debug(f"关键词: {project_keywords[:5]}")
                return EmailType.PROJECT_RELATED

            if engineer_score > project_score + 2.0 and engineer_score > 4.0:
                confidence = min(0.9, 0.7 + engineer_score * 0.03)
                logger.info(
                    f"工程师关键词高分: {engineer_score}, 置信度: {confidence:.2f}"
                )
                logger.debug(f"关键词: {engineer_keywords[:5]}")
                return EmailType.ENGINEER_RELATED

            # 5. AI分析（如果关键词分析不够明确）
            if self.ai_client:
                ai_result = await self._call_ai_classifier(
                    email_data, extracted_content, sender_analysis
                )

                # 调整置信度
                if sender_analysis["confidence"] > 0.5:
                    logger.debug(
                        f"发件人分析提升置信度: {sender_analysis['domain_type']}"
                    )

                return ai_result

            # 6. 基础规则分类
            return self._fallback_classification(
                extracted_content,
                project_score,
                engineer_score,
                project_keywords,
                engineer_keywords,
            )

        except Exception as e:
            logger.error(f"邮件分类过程出错: {e}")
            return EmailType.UNCLASSIFIED

    async def _call_ai_classifier(
        self, email_data: Dict, extracted_content: str, sender_analysis: Dict
    ) -> EmailType:
        """调用AI进行分类"""
        provider_name = self.ai_config.get("provider_name")
        model_classify = self.ai_config.get("model_classify", "gpt-3.5-turbo")
        temperature = self.ai_config.get("temperature", 0.1)
        max_tokens = self.ai_config.get("max_tokens", 200)

        # 构建增强提示词
        prompt = f"""
あなたは日本のIT業界の専門家です。以下のメール情報を分析してカテゴリーを判定してください。

【メール内容】
件名: {email_data.get('subject', '')}
送信者: {email_data.get('sender_email', '')}
本文: {extracted_content[:1500]}

【発信者分析】
タイプ: {sender_analysis['domain_type']}
信頼度: {sender_analysis['confidence']:.2f}

【分類基準】
1. project_related: IT案件・プロジェクトの募集、技術要件や単価の記載
2. engineer_related: エンジニア個人の紹介、履歴書送付、スキルアピール  
3. other: 業界関連の重要メール（勉強会、サービス紹介等）
4. unclassified: 無関係または spam

【出力形式】
{{"category": "カテゴリー名", "confidence": 0.0-1.0, "reasoning": "判定理由"}}

JSON形式のみで回答してください。
"""

        messages = [
            {"role": "system", "content": "あなたは高精度なメール分類の専門家です。"},
            {"role": "user", "content": prompt},
        ]

        try:
            if provider_name == "openai":
                response = await self.ai_client.chat.completions.create(
                    model=model_classify,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content.strip()

            elif provider_name == "deepseek":
                response = await self.ai_client.post(
                    "/v1/chat/completions",
                    json={
                        "model": model_classify,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
            else:
                raise ValueError(f"Unsupported AI provider: {provider_name}")

            # 解析AI响应
            try:
                json_match = re.search(r"\{.*\}", content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = json.loads(content)

                # 转换为EmailType
                category_str = result.get("category", "unclassified")
                confidence = float(result.get("confidence", 0.5))
                reasoning = result.get("reasoning", "AI分析结果")

                logger.info(f"AI分类结果: {category_str}, 置信度: {confidence:.2f}")
                logger.debug(f"AI推理: {reasoning}")

                if "project" in category_str:
                    return EmailType.PROJECT_RELATED
                elif "engineer" in category_str:
                    return EmailType.ENGINEER_RELATED
                elif "other" in category_str:
                    return EmailType.OTHER
                else:
                    return EmailType.UNCLASSIFIED

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"AI响应解析失败: {e}, 内容: {content}")
                return self._extract_category_from_text(content)

        except Exception as e:
            logger.error(f"AI分类调用失败: {e}")
            return EmailType.UNCLASSIFIED

    def _extract_category_from_text(self, text: str) -> EmailType:
        """从文本中提取分类信息（AI返回非JSON时的备用方法）"""
        text_lower = text.lower()

        if "project" in text_lower:
            return EmailType.PROJECT_RELATED
        elif "engineer" in text_lower:
            return EmailType.ENGINEER_RELATED
        elif "other" in text_lower:
            return EmailType.OTHER
        else:
            return EmailType.UNCLASSIFIED

    def _fallback_classification(
        self,
        content: str,
        project_score: float,
        engineer_score: float,
        project_keywords: List[str],
        engineer_keywords: List[str],
    ) -> EmailType:
        """备用分类逻辑"""
        logger.info(
            f"使用备用分类逻辑 - 项目得分: {project_score}, 工程师得分: {engineer_score}"
        )

        if project_score > engineer_score and project_score > 1.0:
            logger.debug(f"备用分类: project_related, 关键词: {project_keywords[:3]}")
            return EmailType.PROJECT_RELATED
        elif engineer_score > 1.0:
            logger.debug(f"备用分类: engineer_related, 关键词: {engineer_keywords[:3]}")
            return EmailType.ENGINEER_RELATED
        elif any(
            word in content.lower() for word in ["説明会", "案内", "勉強会", "技術"]
        ):
            logger.debug("备用分类: other")
            return EmailType.OTHER
        else:
            logger.debug("备用分类: unclassified")
            return EmailType.UNCLASSIFIED

    # ===============================
    # 其他现有方法保持不变
    # ===============================

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
                decrypted_password = None
                try:
                    if row["smtp_password_encrypted"]:
                        password_data = row["smtp_password_encrypted"]

                        # 处理PostgreSQL BYTEA字段类型转换
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
                                f"Unexpected password data type {type(password_data)} for SMTP setting {row['id']}"
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

    # 其他方法（extract_project_info, extract_engineer_info, save_email_to_db 等）保持不变
    # 为了简洁起见，这里不重复贴出所有方法，但实际使用时需要保留所有现有方法

    async def extract_project_info(
        self, email_data: Dict
    ) -> Optional[ProjectStructured]:
        """メールから案件情報を抽出して構造化"""
        if not self.ai_client:
            logger.warning(
                "AI client not initialized. Skipping project info extraction."
            )
            return None

        provider_name = self.ai_config.get("provider_name")
        model_extract = self.ai_config.get("model_extract", "gpt-4")
        temperature = self.ai_config.get("temperature", 0.3)
        max_tokens_extract = self.ai_config.get("max_tokens", 2048)

        # 使用智能内容提取
        extracted_content = self.smart_content_extraction(email_data)

        prompt = f"""
        以下のメールから案件情報を抽出して、必ずJSON形式で返してください。他の説明は不要です。

        件名: {email_data['subject']}
        本文: {extracted_content}
        
        以下の形式で抽出してください：
        {{
            "title": "案件タイトル",
            "client_company": "クライアント企業名",
            "description": "案件概要",
            "skills": ["必要スキル1", "必要スキル2"],
            "location": "勤務地",
            "start_date": "開始日（YYYY-MM-DD形式、例：2024-06-01）",
            "duration": "期間",
            "budget": "予算/単価",
            "japanese_level": "日本語レベル",
            "work_type": "勤務形態",
            "experience": "必要経験"
        }}
        
        重要：
        - start_dateは必ずYYYY-MM-DD形式で返してください（例：2024-06-01）
        - 「2024年6月」のような表記は「2024-06-01」に変換してください
        - 具体的な日が不明な場合は月初（01日）にしてください
        - 情報が見つからない項目はnullにしてください
        - JSONのみを返してください
        """
        messages = [
            {
                "role": "system",
                "content": "あなたは案件情報抽出の専門家です。必ずJSONのみを返してください。日付は必ずYYYY-MM-DD形式で返してください。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            if provider_name == "openai":
                response = await self.ai_client.chat.completions.create(
                    model=model_extract,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens_extract,
                )
                raw_content = response.choices[0].message.content
                data = self._extract_json_from_text(raw_content)

            elif provider_name == "deepseek":
                if isinstance(self.ai_client, httpx.AsyncClient):
                    try:
                        logger.info(
                            "Sending request to DeepSeek API for project extraction..."
                        )
                        logger.debug(
                            f"Request payload: model={model_extract}, temperature={temperature}, max_tokens={max_tokens_extract}"
                        )

                        response = await self.ai_client.post(
                            "/v1/chat/completions",
                            json={
                                "model": model_extract,
                                "messages": messages,
                                "temperature": temperature,
                                "max_tokens": max_tokens_extract,
                            },
                        )
                        response.raise_for_status()

                        logger.info(
                            f"DeepSeek API responded with status: {response.status_code}"
                        )

                        response_json = response.json()
                        logger.info("=== DeepSeek API Response ===")
                        logger.info(
                            f"Full response: {json.dumps(response_json, indent=2, ensure_ascii=False)}"
                        )

                        raw_response_content = response_json["choices"][0]["message"][
                            "content"
                        ]
                        logger.info("=== DeepSeek Raw Content ===")
                        logger.info(f"Raw content:\n{raw_response_content}")
                        logger.info("=== End Raw Content ===")

                        print("\n" + "=" * 50)
                        print("DeepSeek API 返回内容:")
                        print("=" * 50)
                        print(raw_response_content)
                        print("=" * 50 + "\n")

                        data = self._extract_json_from_text(raw_response_content)
                        if data:
                            logger.info(
                                f"Successfully extracted JSON: {json.dumps(data, indent=2, ensure_ascii=False)}"
                            )
                            print(
                                f"✅ JSON解析成功: {json.dumps(data, indent=2, ensure_ascii=False)}"
                            )
                        else:
                            logger.error(
                                "Failed to extract JSON from DeepSeek response"
                            )
                            print("❌ JSON解析失败")

                    except httpx.ReadTimeout as e:
                        logger.error(f"DeepSeek API timeout error: {e}")
                        print(f"❌ DeepSeek API 超时错误: {e}")
                        return None
                    except httpx.HTTPStatusError as e:
                        logger.error(f"DeepSeek API HTTP error: {e}")
                        logger.error(f"Response text: {e.response.text}")
                        print(f"❌ DeepSeek API HTTP错误: {e}")
                        print(f"响应内容: {e.response.text}")
                        return None
                    except KeyError as e:
                        logger.error(f"DeepSeek API response format error: {e}")
                        logger.error(
                            f"Response: {response.json() if 'response' in locals() else 'No response'}"
                        )
                        print(f"❌ DeepSeek API 响应格式错误: {e}")
                        return None
                else:
                    logger.warning(
                        "DeepSeek client not an httpx.AsyncClient. Skipping project info extraction."
                    )
                    return None
            else:
                logger.warning(
                    f"Unsupported AI provider for project info extraction: {provider_name}"
                )
                return None

            if data:
                # 处理日期格式
                if data.get("start_date"):
                    normalized_date = self._parse_date_string(data["start_date"])
                    data["start_date"] = normalized_date

                return ProjectStructured(**data)
            else:
                logger.error("Failed to parse JSON from AI response for project info")
                return None

        except Exception as e:
            logger.error(f"Error extracting project info: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None

    async def extract_engineer_info(
        self, email_data: Dict
    ) -> Optional[EngineerStructured]:
        """メールから技術者情報を抽出して構造化"""
        if not self.ai_client:
            logger.warning(
                "AI client not initialized. Skipping engineer info extraction."
            )
            return None

        provider_name = self.ai_config.get("provider_name")
        model_extract = self.ai_config.get("model_extract", "gpt-4")
        temperature = self.ai_config.get("temperature", 0.3)
        max_tokens_extract = self.ai_config.get("max_tokens", 2048)

        # 使用智能内容提取
        extracted_content = self.smart_content_extraction(email_data)

        prompt = f"""
        以下のメールから技術者情報を抽出して、必ずJSON形式で返してください。他の説明は不要です。
        
        件名: {email_data['subject']}
        本文: {extracted_content}
        
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
        JSONのみを返してください。
        """
        messages = [
            {
                "role": "system",
                "content": "あなたは技術者情報抽出の専門家です。必ずJSONのみを返してください。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            if provider_name == "openai":
                response = await self.ai_client.chat.completions.create(
                    model=model_extract,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens_extract,
                )
                raw_content = response.choices[0].message.content
                data = self._extract_json_from_text(raw_content)

            elif provider_name == "deepseek":
                if isinstance(self.ai_client, httpx.AsyncClient):
                    try:
                        logger.info(
                            "Sending request to DeepSeek API for engineer extraction..."
                        )
                        logger.debug(
                            f"Request payload: model={model_extract}, temperature={temperature}, max_tokens={max_tokens_extract}"
                        )

                        response = await self.ai_client.post(
                            "/v1/chat/completions",
                            json={
                                "model": model_extract,
                                "messages": messages,
                                "temperature": temperature,
                                "max_tokens": max_tokens_extract,
                            },
                        )
                        response.raise_for_status()

                        logger.info(
                            f"DeepSeek API responded with status: {response.status_code}"
                        )

                        response_json = response.json()
                        logger.info("=== DeepSeek API Response (Engineer) ===")
                        logger.info(
                            f"Full response: {json.dumps(response_json, indent=2, ensure_ascii=False)}"
                        )

                        raw_response_content = response_json["choices"][0]["message"][
                            "content"
                        ]
                        logger.info("=== DeepSeek Raw Content (Engineer) ===")
                        logger.info(f"Raw content:\n{raw_response_content}")
                        logger.info("=== End Raw Content ===")

                        print("\n" + "=" * 50)
                        print("DeepSeek API 返回内容 (工程师信息):")
                        print("=" * 50)
                        print(raw_response_content)
                        print("=" * 50 + "\n")

                        data = self._extract_json_from_text(raw_response_content)
                        if data:
                            logger.info(
                                f"Successfully extracted JSON: {json.dumps(data, indent=2, ensure_ascii=False)}"
                            )
                            print(
                                f"✅ JSON解析成功: {json.dumps(data, indent=2, ensure_ascii=False)}"
                            )
                        else:
                            logger.error(
                                "Failed to extract JSON from DeepSeek response"
                            )
                            print("❌ JSON解析失败")

                    except httpx.ReadTimeout as e:
                        logger.error(f"DeepSeek API timeout error: {e}")
                        print(f"❌ DeepSeek API 超时错误: {e}")
                        return None
                    except httpx.HTTPStatusError as e:
                        logger.error(f"DeepSeek API HTTP error: {e}")
                        logger.error(f"Response text: {e.response.text}")
                        print(f"❌ DeepSeek API HTTP错误: {e}")
                        print(f"响应内容: {e.response.text}")
                        return None
                    except KeyError as e:
                        logger.error(f"DeepSeek API response format error: {e}")
                        logger.error(
                            f"Response: {response.json() if 'response' in locals() else 'No response'}"
                        )
                        print(f"❌ DeepSeek API 响应格式错误: {e}")
                        return None
                else:
                    logger.warning(
                        "DeepSeek client not an httpx.AsyncClient. Skipping engineer info extraction."
                    )
                    return None
            else:
                logger.warning(
                    f"Unsupported AI provider for engineer info extraction: {provider_name}"
                )
                return None

            if data:
                return EngineerStructured(**data)
            else:
                logger.error("Failed to parse JSON from AI response for engineer info")
                return None

        except Exception as e:
            logger.error(f"Error extracting engineer info: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
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
            async with conn.transaction():
                try:
                    start_date_value = None
                    if project_data.start_date:
                        normalized_date = self._parse_date_string(
                            project_data.start_date
                        )
                        if normalized_date:
                            try:
                                start_date_value = datetime.strptime(
                                    normalized_date, "%Y-%m-%d"
                                ).date()
                                logger.info(
                                    f"Converted start_date to database format: {start_date_value}"
                                )
                            except ValueError as e:
                                logger.warning(
                                    f"Failed to convert normalized date {normalized_date} to date object: {e}"
                                )
                                start_date_value = None
                        else:
                            logger.warning(
                                f"Failed to normalize date: {project_data.start_date}"
                            )
                            start_date_value = None

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
                            $7, $8, $9, $10, $11, $12,
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
                        start_date_value,
                        project_data.duration,
                        project_data.budget,
                        project_data.japanese_level,
                        project_data.work_type,
                        project_data.experience,
                        sender_email,
                        datetime.now(),
                    )

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
            async with conn.transaction():
                try:
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
        settings_list = await self.get_smtp_settings(tenant_id)

        if not settings_list:
            logger.warning(f"No SMTP settings found for tenant: {tenant_id}")
            return

        for settings in settings_list:
            try:
                emails = await self.fetch_emails(settings)
                logger.info(f"Fetched {len(emails)} new emails for tenant {tenant_id}")

                for email_data in emails:
                    # 使用改进的分类方法
                    email_type = await self.classify_email(email_data)
                    logger.info(f"Email classified as: {email_type.value}")

                    email_id = await self.save_email_to_db(
                        tenant_id, email_data, email_type, None
                    )

                    if email_type == EmailType.PROJECT_RELATED:
                        project_data = await self.extract_project_info(email_data)
                        if project_data:
                            await self.save_project(
                                tenant_id,
                                project_data,
                                email_id,
                                email_data["sender_email"],
                            )

                    elif email_type == EmailType.ENGINEER_RELATED:
                        engineer_data = await self.extract_engineer_info(email_data)
                        if engineer_data:
                            await self.save_engineer(
                                tenant_id,
                                engineer_data,
                                email_id,
                                email_data["sender_email"],
                            )

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
    """バッチ処理用のメイン関数"""
    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", 5432),
        "database": os.getenv("DB_NAME", "ai_matching"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
    }

    active_ai_config = Config.get_ai_config()

    processor = EmailProcessor(
        db_config=Config.get_db_config(), ai_config=active_ai_config
    )
    await processor.initialize()

    try:
        async with processor.db_pool.acquire() as conn:
            tenant_ids = await conn.fetch(
                """
                SELECT DISTINCT t.id 
                FROM tenants t
                INNER JOIN email_smtp_settings s ON s.tenant_id = t.id
                WHERE t.is_active = true AND s.is_active = true
            """
            )

        for row in tenant_ids:
            tenant_id = str(row["id"])
            logger.info(f"Processing emails for tenant: {tenant_id}")
            await processor.process_emails_for_tenant(tenant_id)

    except Exception as e:
        logger.error(f"Error in main processing: {e}")
    finally:
        await processor.close()


if __name__ == "__main__":
    asyncio.run(main())
