# src/email_classifier.py
"""邮件分类模块 - 改进版本，修复工程师邮件误分类问题"""

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
    """邮件分类器 - 改进版本"""

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
        elif provider_name in ["deepseek", "custom"]:
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
                logger.info(f"{provider_name.title()} client initialized")
            else:
                logger.error(f"{provider_name.title()} API key or base URL not found")

        self._init_classification_components()

    def _init_classification_components(self):
        """初始化分类器相关组件"""

        # 超强工程师指示符 - 出现这些几乎100%是工程师邮件
        self.ultra_strong_engineer_indicators = [
            r"要員.*?ご紹介",  # 要员介绍
            r"人材.*?ご紹介",  # 人才介绍
            r"技術者.*?ご紹介",  # 技术者介绍
            r"エンジニア.*?ご紹介",  # 工程师介绍
            r"【氏.*?名】",  # 姓名格式
            r"【年.*?齢】",  # 年龄格式
            r"【性.*?別】",  # 性别格式
            r"【最寄.*?駅】",  # 最近车站格式
            r"【実務経験】",  # 实务经验
            r"【営業.*?況】",  # 营业状况
            r"履歴書.*?添付",  # 简历附件
            r"職務経歴書.*?添付",  # 职务经历书附件
        ]

        # 超强项目指示符
        self.ultra_strong_project_indicators = [
            r"案件.*?募集",  # 案件募集
            r"プロジェクト.*?募集",  # 项目募集
            r"開発案件.*?ご紹介",  # 开发案件介绍
            r"【案件.*?名】",  # 案件名格式
            r"【プロジェクト.*?名】",  # 项目名格式
            r"参画.*?募集",  # 参与募集
            r"【必須.*?スキル】",  # 必需技能
            r"【歓迎.*?スキル】",  # 欢迎技能
            r"【勤務.*?地】",  # 工作地点
            r"応募.*?締切",  # 应募截止
        ]

        # 个人信息模式匹配（用于识别工程师介绍的格式特征）
        self.personal_info_patterns = [
            r"【?氏.*?名】?\s*[:：]\s*[\w\s\(\)（）]+",  # 姓名
            r"【?年.*?齢】?\s*[:：]\s*\d+.*?歳",  # 年龄
            r"【?性.*?別】?\s*[:：]\s*(男性|女性)",  # 性别
            r"【?最寄.*?駅】?\s*[:：]",  # 最近车站
            r"【?実務経験】?\s*[:：]\s*\d+.*?年",  # 实务经验
            r"【?日本.*?語】?\s*[:：].*(級|レベル)",  # 日语水平
            r"【?単.*?価】?\s*[:：]\s*\d+.*?万",  # 单价
            r"【?稼働.*?日?】?\s*[:：]",  # 可工作时间
            r"【?営業.*?況】?\s*[:：]",  # 营业状况
            r"【?対応.*?工程】?\s*[:：]",  # 对应工程
            r"【?スキル】?\s*[:：]",  # 技能
            r"【?備.*?考】?\s*[:：]",  # 备考
        ]

        # 项目信息模式匹配
        self.project_info_patterns = [
            r"【?案件.*?名】?\s*[:：]",  # 案件名
            r"【?クライアント】?\s*[:：]",  # 客户
            r"【?必須.*?スキル】?\s*[:：]",  # 必需技能
            r"【?歓迎.*?スキル】?\s*[:：]",  # 欢迎技能
            r"【?勤務.*?地】?\s*[:：]",  # 工作地点
            r"【?期.*?間】?\s*[:：]",  # 期间
            r"【?開始.*?日】?\s*[:：]",  # 开始日
            r"【?終了.*?日】?\s*[:：]",  # 结束日
            r"【?面談.*?回数】?\s*[:：]",  # 面谈回数
        ]

        # 改进后的关键词权重系统
        self.keywords = {
            "project_related": {
                "超高权重": [
                    "案件募集",
                    "プロジェクト募集",
                    "開発案件ご紹介",
                    "新規案件",
                    "緊急案件",
                    "案件詳細",
                    "参画募集",
                ],
                "高权重": [
                    "案件",
                    "プロジェクト",
                    "募集",
                    "参画",
                    "必須スキル",
                    "歓迎スキル",
                    "勤務地",
                    "常駐",
                    "クライアント",
                    "面談",
                    "応募",
                ],
                "中权重": [
                    "開発",
                    "設計",
                    "構築",
                    "保守",
                    "運用",
                    "テスト",
                    "要件定義",
                    "基本設計",
                    "詳細設計",
                ],
            },
            "engineer_related": {
                "超高权重": [
                    "要員ご紹介",
                    "人材ご紹介",
                    "技術者ご紹介",
                    "エンジニアご紹介",
                    "履歴書添付",
                    "職務経歴書添付",
                    "スキルシート添付",
                    "個人紹介",
                    "人材情報",
                    "技術者情報",
                ],
                "高权重": [
                    "エンジニア",
                    "技術者",
                    "開発者",
                    "プログラマー",
                    "履歴書",
                    "職務経歴",
                    "希望単価",
                    "稼働可能",
                    "営業状況",
                    "提案のみ",
                    "面談可能",
                ],
                "中权重": [
                    "経験年数",
                    "開発経験",
                    "業務経歴",
                    "資格",
                    "学歴",
                    "日本語レベル",
                    "コミュニケーション",
                    "真面目",
                    "責任感",
                ],
            },
        }

        # 排除关键词（垃圾邮件识别）
        self.exclusion_keywords = [
            "広告",
            "宣伝",
            "PR",
            "セール",
            "キャンペーン",
            "限定オファー",
            "今すぐクリック",
            "特別価格",
            "無料プレゼント",
            "副業",
        ]

        # 发件人域名模式
        self.sender_patterns = {
            "recruiting": ["recruit", "hr", "jinzai", "career", "agent"],
            "suspicious": ["noreply", "spam", "promo", "marketing", "no-reply"],
        }

    def analyze_email_structure(self, email_data: Dict) -> Dict:
        """分析邮件结构特征 - 这是关键的改进"""
        subject = email_data.get("subject", "")
        body_text = email_data.get("body_text", "")
        combined_text = f"{subject}\n{body_text}"

        analysis = {
            "ultra_engineer_score": 0,
            "ultra_project_score": 0,
            "personal_info_count": 0,
            "project_info_count": 0,
            "structure_type": "unknown",
            "confidence": 0.0,
            "indicators": [],
            "definitive_type": None,
        }

        # 检查超强工程师指示符
        for pattern in self.ultra_strong_engineer_indicators:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            if matches:
                analysis["ultra_engineer_score"] += len(matches) * 20  # 大幅提升分数
                analysis["indicators"].append(
                    f"超强工程师指示符: {pattern} (匹配{len(matches)}次)"
                )
                logger.info(f"检测到超强工程师指示符: {pattern}")

        # 检查超强项目指示符
        for pattern in self.ultra_strong_project_indicators:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            if matches:
                analysis["ultra_project_score"] += len(matches) * 20
                analysis["indicators"].append(
                    f"超强项目指示符: {pattern} (匹配{len(matches)}次)"
                )

        # 检查个人信息模式
        for pattern in self.personal_info_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            if matches:
                analysis["personal_info_count"] += len(matches)
                analysis["indicators"].append(f"个人信息: {pattern}")

        # 检查项目信息模式
        for pattern in self.project_info_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            if matches:
                analysis["project_info_count"] += len(matches)
                analysis["indicators"].append(f"项目信息: {pattern}")

        # 决定性判断逻辑
        if analysis["ultra_engineer_score"] >= 20:
            analysis["definitive_type"] = "engineer_related"
            analysis["confidence"] = 0.95
            analysis["structure_type"] = "definitive_engineer"
        elif analysis["ultra_project_score"] >= 20:
            analysis["definitive_type"] = "project_related"
            analysis["confidence"] = 0.95
            analysis["structure_type"] = "definitive_project"
        elif analysis["personal_info_count"] >= 4:  # 4个或以上个人信息项目
            analysis["definitive_type"] = "engineer_related"
            analysis["confidence"] = 0.90
            analysis["structure_type"] = "personal_profile"
        elif analysis["project_info_count"] >= 4:  # 4个或以上项目信息项目
            analysis["definitive_type"] = "project_related"
            analysis["confidence"] = 0.90
            analysis["structure_type"] = "project_description"

        return analysis

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
                "要員",
                "人材",
                "ご紹介",
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
        """计算关键词得分 - 改进版本"""
        if email_type not in self.keywords:
            return 0.0, []

        found_keywords = []
        score = 0.0
        text_lower = text.lower()

        keywords_dict = self.keywords[email_type]

        # 超高权重关键词 - 大幅提升权重
        for keyword in keywords_dict.get("超高权重", []):
            if keyword in text_lower:
                score += 25.0  # 从原来的3.0提升到25.0
                found_keywords.append(f"超高:{keyword}")

        # 高权重关键词
        for keyword in keywords_dict.get("高权重", []):
            if keyword in text_lower:
                score += 5.0  # 从原来的3.0提升到5.0
                found_keywords.append(f"高:{keyword}")

        # 中权重关键词
        for keyword in keywords_dict.get("中权重", []):
            if keyword in text_lower:
                score += 1.0
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
        """邮件分类主方法 - 改进版本"""
        try:
            logger.info(f"开始分类邮件: {email_data.get('subject', 'No Subject')}")

            # 1. 垃圾邮件检测
            if self.check_spam_indicators(email_data):
                logger.info("检测到垃圾邮件特征，分类为unclassified")
                return EmailType.UNCLASSIFIED

            # 2. 结构分析 - 这是关键改进
            structure_analysis = self.analyze_email_structure(email_data)
            logger.info(f"结构分析结果: {structure_analysis}")

            # 3. 决定性判断 - 如果结构分析已经确定类型，直接返回
            if structure_analysis["definitive_type"]:
                logger.info(
                    f"结构分析确定类型: {structure_analysis['definitive_type']}, "
                    f"置信度: {structure_analysis['confidence']:.2f}"
                )
                return EmailType(structure_analysis["definitive_type"])

            # 4. 附件分析
            attachment_analysis = self.analyze_attachments(email_data)
            if attachment_analysis["confidence"] > 0.8:
                logger.info(
                    f"强附件指标检测: {attachment_analysis['strong_type']}, "
                    f"置信度: {attachment_analysis['confidence']:.2f}"
                )
                return EmailType(attachment_analysis["strong_type"])

            # 5. 智能内容分析
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

            # 6. 综合评分 - 考虑结构分析的权重
            final_engineer_score = (
                engineer_score
                + structure_analysis["personal_info_count"] * 3  # 个人信息每项+3分
                + structure_analysis["ultra_engineer_score"] * 0.5  # 超强指示符额外加分
            )

            final_project_score = (
                project_score
                + structure_analysis["project_info_count"] * 3  # 项目信息每项+3分
                + structure_analysis["ultra_project_score"] * 0.5  # 超强指示符额外加分
            )

            # 发件人权重调整
            if sender_analysis["domain_type"] == "recruiting":
                final_engineer_score += 5.0

            logger.info(
                f"最终评分 - 工程师: {final_engineer_score:.1f}, 项目: {final_project_score:.1f}"
            )
            logger.info(f"工程师关键词: {engineer_keywords[:3]}")
            logger.info(f"项目关键词: {project_keywords[:3]}")

            # 7. 高置信度判断 - 提高判断阈值
            if (
                final_engineer_score > final_project_score + 5.0
                and final_engineer_score > 10.0
            ):
                confidence = min(0.95, 0.7 + final_engineer_score * 0.02)
                logger.info(
                    f"工程师分类确定: 分数差异足够大 ({final_engineer_score:.1f} vs {final_project_score:.1f})"
                )
                return EmailType.ENGINEER_RELATED

            if (
                final_project_score > final_engineer_score + 5.0
                and final_project_score > 10.0
            ):
                confidence = min(0.95, 0.7 + final_project_score * 0.02)
                logger.info(
                    f"项目分类确定: 分数差异足够大 ({final_project_score:.1f} vs {final_engineer_score:.1f})"
                )
                return EmailType.PROJECT_RELATED

            # 8. AI分析（当规则无法确定时）
            if self.ai_client:
                logger.info("调用AI进行分类")
                ai_result = await self._call_ai_classifier(
                    email_data, extracted_content, sender_analysis, structure_analysis
                )
                return ai_result

            # 9. 基础规则分类
            return self._fallback_classification(
                extracted_content,
                final_project_score,
                final_engineer_score,
                project_keywords,
                engineer_keywords,
            )

        except Exception as e:
            logger.error(f"邮件分类过程出错: {e}")
            return EmailType.UNCLASSIFIED

    async def _call_ai_classifier(
        self,
        email_data: Dict,
        extracted_content: str,
        sender_analysis: Dict,
        structure_analysis: Dict,
    ) -> EmailType:
        """调用AI进行分类 - 改进版本，支持自定义API"""
        provider_name = self.ai_config.get("provider_name")
        model_classify = self.ai_config.get("model_classify", "gpt-3.5-turbo")
        temperature = self.ai_config.get("temperature", 0.1)
        max_tokens = self.ai_config.get("max_tokens", 200)

        # 构建更精确的提示词，强调个人技术者介绍的识别
        prompt = f"""
あなたは日本のIT業界の専門メール分類システムです。以下のメールを正確に分類してください。

【メール内容】
件名: {email_data.get('subject', '')}
送信者: {email_data.get('sender_email', '')}
本文: {extracted_content[:1500]}

【構造分析情報】
- 個人情報項目数: {structure_analysis['personal_info_count']}
- プロジェクト情報項目数: {structure_analysis['project_info_count']}
- 超強工程師指示符分数: {structure_analysis['ultra_engineer_score']}
- 超強項目指示符分数: {structure_analysis['ultra_project_score']}

【重要な分類基準】
1. engineer_related（技術者関連）:
   ✓ 個人の技術者・エンジニアの紹介メール
   ✓ 「要員ご紹介」「人材ご紹介」「技術者ご紹介」の表現
   ✓ 【氏名】【年齢】【性別】【最寄駅】【実務経験】【単価】【稼働日】などの個人情報
   ✓ 履歴書・職務経歴書の送付や添付
   ✓ 個人のスキル、経験、人柄の紹介

2. project_related（案件関連）:
   ✓ IT案件・プロジェクトの募集
   ✓ 開発案件の詳細説明
   ✓ 【案件名】【必須スキル】【歓迎スキル】【勤務地】【期間】などの案件情報
   ✓ 参画者募集、応募締切の記載

3. other: 業界関連の重要メール（勉強会、サービス紹介等）
4. unclassified: 無関係またはspam

【特別注意事項】
- 「要員ご紹介」「人材ご紹介」は100%engineer_relatedです
- 【氏名】【年齢】などの個人情報フォーマットはengineer_relatedの強い指標です
- 技術スキルが記載されていても、個人の紹介文脈ならengineer_relatedです
- 募集文脈でなく紹介文脈かを重視してください

【出力形式】
{{"category": "カテゴリー名", "confidence": 0.0-1.0, "reasoning": "判定理由"}}

JSONのみで回答してください。
"""

        messages = [
            {
                "role": "system",
                "content": "あなたは高精度なメール分類の専門家です。個人の技術者紹介は必ずengineer_relatedに分類してください。「要員ご紹介」は100%engineer_relatedです。",
            },
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

            elif provider_name in ["deepseek", "custom"]:
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
                logger.info(f"AI推理: {reasoning}")

                if "engineer" in category_str:
                    return EmailType.ENGINEER_RELATED
                elif "project" in category_str:
                    return EmailType.PROJECT_RELATED
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

        if "engineer" in text_lower:
            return EmailType.ENGINEER_RELATED
        elif "project" in text_lower:
            return EmailType.PROJECT_RELATED
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
        """备用分类逻辑 - 改进版本"""
        logger.info(
            f"使用备用分类逻辑 - 项目得分: {project_score:.1f}, 工程师得分: {engineer_score:.1f}"
        )

        # 提高判断阈值，避免误分类
        if engineer_score > project_score and engineer_score > 3.0:
            logger.info(f"备用分类: engineer_related, 关键词: {engineer_keywords[:3]}")
            return EmailType.ENGINEER_RELATED
        elif project_score > engineer_score and project_score > 3.0:
            logger.info(f"备用分类: project_related, 关键词: {project_keywords[:3]}")
            return EmailType.PROJECT_RELATED
        elif any(
            word in content.lower() for word in ["説明会", "案内", "勉強会", "セミナー"]
        ):
            logger.info("备用分类: other")
            return EmailType.OTHER
        else:
            logger.info("备用分类: unclassified")
            return EmailType.UNCLASSIFIED

    async def _call_ai_classifier(
        self,
        email_data: Dict,
        extracted_content: str,
        sender_analysis: Dict,
        structure_analysis: Dict,
    ) -> EmailType:
        """调用AI进行分类 - 改进版本"""
        provider_name = self.ai_config.get("provider_name")
        model_classify = self.ai_config.get("model_classify", "gpt-3.5-turbo")
        temperature = self.ai_config.get("temperature", 0.1)
        max_tokens = self.ai_config.get("max_tokens", 200)

        # 构建更精确的提示词，强调个人技术者介绍的识别
        prompt = f"""
あなたは日本のIT業界の専門メール分類システムです。以下のメールを正確に分類してください。

【メール内容】
件名: {email_data.get('subject', '')}
送信者: {email_data.get('sender_email', '')}
本文: {extracted_content[:1500]}

【構造分析情報】
- 個人情報項目数: {structure_analysis['personal_info_count']}
- プロジェクト情報項目数: {structure_analysis['project_info_count']}
- 超強工程師指示符分数: {structure_analysis['ultra_engineer_score']}
- 超強項目指示符分数: {structure_analysis['ultra_project_score']}

【重要な分類基準】
1. engineer_related（技術者関連）:
   ✓ 個人の技術者・エンジニアの紹介メール
   ✓ 「要員ご紹介」「人材ご紹介」「技術者ご紹介」の表現
   ✓ 【氏名】【年齢】【性別】【最寄駅】【実務経験】【単価】【稼働日】などの個人情報
   ✓ 履歴書・職務経歴書の送付や添付
   ✓ 個人のスキル、経験、人柄の紹介

2. project_related（案件関連）:
   ✓ IT案件・プロジェクトの募集
   ✓ 開発案件の詳細説明
   ✓ 【案件名】【必須スキル】【歓迎スキル】【勤務地】【期間】などの案件情報
   ✓ 参画者募集、応募締切の記載

3. other: 業界関連の重要メール（勉強会、サービス紹介等）
4. unclassified: 無関係またはspam

【特別注意事項】
- 「要員ご紹介」「人材ご紹介」は100%engineer_relatedです
- 【氏名】【年齢】などの個人情報フォーマットはengineer_relatedの強い指標です
- 技術スキルが記載されていても、個人の紹介文脈ならengineer_relatedです
- 募集文脈でなく紹介文脈かを重視してください

【出力形式】
{{"category": "カテゴリー名", "confidence": 0.0-1.0, "reasoning": "判定理由"}}

JSONのみで回答してください。
"""

        messages = [
            {
                "role": "system",
                "content": "あなたは高精度なメール分類の専門家です。個人の技術者紹介は必ずengineer_relatedに分類してください。「要員ご紹介」は100%engineer_relatedです。",
            },
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
                logger.info(f"AI推理: {reasoning}")

                if "engineer" in category_str:
                    return EmailType.ENGINEER_RELATED
                elif "project" in category_str:
                    return EmailType.PROJECT_RELATED
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

        if "engineer" in text_lower:
            return EmailType.ENGINEER_RELATED
        elif "project" in text_lower:
            return EmailType.PROJECT_RELATED
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
        """备用分类逻辑 - 改进版本"""
        logger.info(
            f"使用备用分类逻辑 - 项目得分: {project_score:.1f}, 工程师得分: {engineer_score:.1f}"
        )

        # 提高判断阈值，避免误分类
        if engineer_score > project_score and engineer_score > 3.0:
            logger.info(f"备用分类: engineer_related, 关键词: {engineer_keywords[:3]}")
            return EmailType.ENGINEER_RELATED
        elif project_score > engineer_score and project_score > 3.0:
            logger.info(f"备用分类: project_related, 关键词: {project_keywords[:3]}")
            return EmailType.PROJECT_RELATED
        elif any(
            word in content.lower() for word in ["説明会", "案内", "勉強会", "セミナー"]
        ):
            logger.info("备用分类: other")
            return EmailType.OTHER
        else:
            logger.info("备用分类: unclassified")
            return EmailType.UNCLASSIFIED
