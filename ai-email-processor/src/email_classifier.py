# src/email_classifier.py
"""邮件分类模块"""

import re
import json
import logging
from typing import Dict, List, Tuple
from enum import Enum

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class EmailType(str, Enum):
    PROJECT_RELATED = "project_related"
    ENGINEER_RELATED = "engineer_related"
    OTHER = "other"
    UNCLASSIFIED = "unclassified"


class EmailClassifier:
    """邮件分类器"""

    def __init__(self, ai_config: Dict):
        self.ai_config = ai_config
        self.ai_client = None

        provider_name = ai_config.get("provider_name")
        api_key = ai_config.get("api_key")

        if provider_name == "openai":
            if api_key:
                self.ai_client = AsyncOpenAI(api_key=api_key)
            else:
                logger.error("OpenAI API key not found")
        elif provider_name == "deepseek":
            api_base_url = ai_config.get("api_base_url")
            timeout = ai_config.get("timeout", 120.0)
            if api_key and api_base_url:
                self.ai_client = httpx.AsyncClient(
                    base_url=api_base_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=timeout,
                )
                logger.info(f"DeepSeek client initialized")

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
            "resume_files": [],
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

        # 简历文件扩展名
        resume_extensions = [".docx", ".doc", ".pdf", ".xlsx", ".xls"]

        for attachment in attachments:
            filename = attachment.get("filename", "").lower()

            # 检查是否为简历文件
            is_resume_file = False
            for ext in resume_extensions:
                if filename.endswith(ext):
                    # 检查文件名是否包含简历相关关键词
                    for pattern in engineer_patterns:
                        if re.search(pattern, filename):
                            analysis["resume_files"].append(attachment)
                            is_resume_file = True
                            break

                    # 如果文件扩展名是简历格式，也可能是简历
                    if not is_resume_file and ext in [".docx", ".doc", ".pdf"]:
                        analysis["resume_files"].append(attachment)
                        is_resume_file = True

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

        # 如果有简历文件，强烈倾向于engineer_related
        if analysis["resume_files"]:
            analysis["confidence"] = 0.95
            analysis["strong_type"] = "engineer_related"
            logger.info(f"发现 {len(analysis['resume_files'])} 个可能的简历文件")

        return analysis

    def smart_content_extraction(self, email_data: Dict) -> str:
        """智能内容提取"""
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
        """邮件分类主方法"""
        try:
            # 1. 垃圾邮件检测
            if self.check_spam_indicators(email_data):
                logger.info("检测到垃圾邮件特征，分类为unclassified")
                return EmailType.UNCLASSIFIED

            # 2. 附件分析
            attachment_analysis = self.analyze_attachments(email_data)
            if attachment_analysis["confidence"] > 0.8:
                logger.info(
                    f"强附件指标检测: {attachment_analysis['strong_type']}, "
                    f"置信度: {attachment_analysis['confidence']:.2f}"
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
