# src/attachment_processor.py
"""附件处理模块 - 专门处理简历附件解析"""

import os
import io
import json
import logging
import re
from typing import List, Dict, Optional
import base64

try:
    import docx

    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logging.warning("python-docx not installed. Word document processing disabled.")

try:
    import PyPDF2

    PDF_AVAILABLE = True
except ImportError:
    try:
        import pdfplumber

        PDF_AVAILABLE = True
        PDF_LIBRARY = "pdfplumber"
    except ImportError:
        PDF_AVAILABLE = False
        logging.warning(
            "Neither PyPDF2 nor pdfplumber installed. PDF processing disabled."
        )
    else:
        PDF_LIBRARY = "pdfplumber"
else:
    PDF_LIBRARY = "PyPDF2"

try:
    import openpyxl

    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    logging.warning("openpyxl not installed. Excel document processing disabled.")

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ResumeData(BaseModel):
    """简历数据模型"""

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


class AttachmentProcessor:
    """附件处理器"""

    def __init__(self, ai_config: Dict):
        self.ai_config = ai_config
        self.ai_client = None

        provider_name = ai_config.get("provider_name")
        api_key = ai_config.get("api_key")

        if provider_name == "openai":
            if api_key:
                self.ai_client = AsyncOpenAI(api_key=api_key)
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
                logger.info("AttachmentProcessor AI client initialized")

    def extract_text_from_docx(self, file_content: bytes) -> str:
        """从Word文档提取文本"""
        if not DOCX_AVAILABLE:
            logger.error("python-docx not available for Word document processing")
            return ""

        try:
            doc = docx.Document(io.BytesIO(file_content))
            full_text = []

            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    full_text.append(paragraph.text.strip())

            # 处理表格中的文本
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            full_text.append(cell.text.strip())

            text = "\n".join(full_text)
            logger.info(f"从Word文档提取了 {len(text)} 字符的文本")
            return text

        except Exception as e:
            logger.error(f"Word文档解析失败: {e}")
            return ""

    def extract_text_from_pdf(self, file_content: bytes) -> str:
        """从PDF文件提取文本"""
        if not PDF_AVAILABLE:
            logger.error("PDF processing library not available")
            return ""

        try:
            if PDF_LIBRARY == "pdfplumber":
                import pdfplumber

                full_text = []
                with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            full_text.append(text)

                text = "\n".join(full_text)
                logger.info(f"从PDF文档提取了 {len(text)} 字符的文本")
                return text

            else:  # PyPDF2
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                full_text = []

                for page in pdf_reader.pages:
                    text = page.extract_text()
                    if text:
                        full_text.append(text)

                text = "\n".join(full_text)
                logger.info(f"从PDF文档提取了 {len(text)} 字符的文本")
                return text

        except Exception as e:
            logger.error(f"PDF文档解析失败: {e}")
            return ""

    def extract_text_from_excel(self, file_content: bytes) -> str:
        """从Excel文件提取文本"""
        if not EXCEL_AVAILABLE:
            logger.error("openpyxl not available for Excel document processing")
            return ""

        try:
            workbook = openpyxl.load_workbook(io.BytesIO(file_content))
            full_text = []

            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                sheet_text = []

                for row in sheet.iter_rows(values_only=True):
                    row_text = []
                    for cell in row:
                        if cell is not None and str(cell).strip():
                            row_text.append(str(cell).strip())
                    if row_text:
                        sheet_text.append(" | ".join(row_text))

                if sheet_text:
                    full_text.append(f"=== {sheet_name} ===")
                    full_text.extend(sheet_text)

            text = "\n".join(full_text)
            logger.info(f"从Excel文档提取了 {len(text)} 字符的文本")
            return text

        except Exception as e:
            logger.error(f"Excel文档解析失败: {e}")
            return ""

    def extract_text_from_attachment(self, attachment: Dict) -> str:
        """根据附件类型提取文本内容"""
        filename = attachment.get("filename", "").lower()
        file_content = attachment.get("content", b"")

        if not file_content:
            logger.warning(f"附件 {filename} 没有内容")
            return ""

        # 如果内容是base64编码的字符串，先解码
        if isinstance(file_content, str):
            try:
                file_content = base64.b64decode(file_content)
            except Exception as e:
                logger.error(f"Base64解码失败: {e}")
                return ""

        # 根据文件扩展名选择解析方法
        if filename.endswith((".docx", ".doc")):
            return self.extract_text_from_docx(file_content)
        elif filename.endswith(".pdf"):
            return self.extract_text_from_pdf(file_content)
        elif filename.endswith((".xlsx", ".xls")):
            return self.extract_text_from_excel(file_content)
        else:
            logger.warning(f"不支持的文件类型: {filename}")
            return ""

    def _extract_json_from_text(self, text: str) -> Optional[Dict]:
        """从AI响应文本中提取JSON"""
        try:
            # 尝试直接解析
            result = json.loads(text.strip())
            return result
        except json.JSONDecodeError:
            # 尝试查找JSON块
            json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
            matches = re.findall(json_pattern, text, re.DOTALL)

            for match in matches:
                try:
                    result = json.loads(match)
                    return result
                except json.JSONDecodeError:
                    continue

            # 尝试复杂的JSON提取
            start_idx = text.find("{")
            if start_idx != -1:
                brace_count = 0
                for i, char in enumerate(text[start_idx:], start_idx):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            try:
                                extracted = text[start_idx : i + 1]
                                result = json.loads(extracted)
                                return result
                            except json.JSONDecodeError:
                                break

            logger.warning(f"无法从文本中提取JSON: {text[:200]}...")
            return None

    async def extract_resume_data_with_ai(
        self, resume_text: str, filename: str = ""
    ) -> Optional[ResumeData]:
        """使用AI从简历文本中提取结构化数据"""
        if not self.ai_client:
            logger.warning(
                "AI client not initialized. Skipping resume data extraction."
            )
            return None

        if not resume_text.strip():
            logger.warning("简历文本为空，跳过提取")
            return None

        provider_name = self.ai_config.get("provider_name")
        model_extract = self.ai_config.get("model_extract", "gpt-4")
        temperature = self.ai_config.get("temperature", 0.3)
        max_tokens_extract = self.ai_config.get("max_tokens", 2048)

        # 限制文本长度，避免超出AI模型限制
        if len(resume_text) > 4000:
            resume_text = resume_text[:4000] + "..."

        prompt = f"""
以下は履歴書・職務経歴書の内容です。この情報から技術者の詳細情報を抽出して、必ずJSON形式で返してください。

【ファイル名】: {filename}
【履歴書内容】:
{resume_text}

以下の形式で抽出してください：
{{
    "name": "技術者名（必須）",
    "email": "メールアドレス",
    "phone": "電話番号",
    "gender": "性別（男性/女性/回答しない）",
    "age": "年齢",
    "nationality": "国籍",
    "nearest_station": "最寄り駅",
    "education": "学歴・最終学歴",
    "arrival_year_japan": "来日年度",
    "certifications": ["資格1", "資格2"],
    "skills": ["プログラミング言語1", "プログラミング言語2", "技術スキル1"],
    "technical_keywords": ["Java", "Python", "AWS", "React"],
    "experience": "総経験年数（例：5年）",
    "work_scope": "作業範囲・得意分野",
    "work_experience": "職務経歴の詳細",
    "japanese_level": "日本語レベル（不問/日常会話レベル/ビジネスレベル/ネイティブレベル）",
    "english_level": "英語レベル（不問/日常会話レベル/ビジネスレベル/ネイティブレベル）",
    "availability": "稼働可能時期",
    "preferred_work_style": ["常駐", "リモート", "ハイブリッド"],
    "preferred_locations": ["東京", "大阪"],
    "desired_rate_min": 希望単価下限（数値のみ、万円単位）,
    "desired_rate_max": 希望単価上限（数値のみ、万円単位）,
    "overtime_available": 残業対応可能（true/false）,
    "business_trip_available": 出張対応可能（true/false）,
    "self_promotion": "自己PR・アピールポイント",
    "remarks": "備考・その他",
    "recommendation": "推薦コメント",
    "source_filename": "{filename}"
}}

重要な指示：
1. nameフィールドは必須です。見つからない場合は"名前不明"としてください
2. 情報が見つからない項目はnullにしてください
3. desired_rate_min/maxは数値のみを返してください（万円表記は除く）
4. skillsには具体的な技術名を含めてください
5. technical_keywordsには技術関連のキーワードを抽出してください
6. JSONのみを返してください、他の説明は不要です
"""

        messages = [
            {
                "role": "system",
                "content": "あなたは履歴書・職務経歴書から情報を抽出する専門家です。必ずJSONのみを返してください。",
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
                        logger.info(f"发送简历解析请求到DeepSeek API: {filename}")

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

                        response_json = response.json()
                        raw_response_content = response_json["choices"][0]["message"][
                            "content"
                        ]

                        logger.info(f"=== DeepSeek 简历解析响应 ({filename}) ===")
                        logger.info(f"Raw content:\n{raw_response_content}")

                        data = self._extract_json_from_text(raw_response_content)
                        if data:
                            logger.info(f"成功解析简历JSON: {filename}")
                        else:
                            logger.error(f"JSON解析失败: {filename}")

                    except Exception as e:
                        logger.error(f"DeepSeek API error for resume {filename}: {e}")
                        return None
                else:
                    logger.warning(
                        "DeepSeek client not available for resume extraction"
                    )
                    return None
            else:
                logger.warning(
                    f"Unsupported AI provider for resume extraction: {provider_name}"
                )
                return None

            if data:
                # 确保name字段存在
                if not data.get("name"):
                    data["name"] = "名前不明"

                # 确保experience字段存在
                if not data.get("experience"):
                    data["experience"] = "不明"

                return ResumeData(**data)
            else:
                logger.error(
                    f"Failed to parse JSON from AI response for resume: {filename}"
                )
                return None

        except Exception as e:
            logger.error(f"Error extracting resume data from {filename}: {e}")
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None

    async def process_resume_attachments(
        self, attachments: List[Dict]
    ) -> List[ResumeData]:
        """处理所有简历附件，返回提取的简历数据列表"""
        resume_data_list = []

        # 过滤出可能的简历文件
        resume_files = []
        resume_extensions = [".docx", ".doc", ".pdf", ".xlsx", ".xls"]
        engineer_patterns = [
            r"履歴書",
            r"職務経歴",
            r"スキルシート",
            r"resume",
            r"cv",
            r"profile",
        ]

        for attachment in attachments:
            filename = attachment.get("filename", "").lower()

            # 检查文件扩展名
            has_resume_extension = any(
                filename.endswith(ext) for ext in resume_extensions
            )

            # 检查文件名关键词
            has_resume_keyword = any(
                re.search(pattern, filename) for pattern in engineer_patterns
            )

            if has_resume_extension or has_resume_keyword:
                resume_files.append(attachment)
                logger.info(f"发现可能的简历文件: {filename}")

        if not resume_files:
            logger.info("未发现简历附件")
            return resume_data_list

        logger.info(f"开始处理 {len(resume_files)} 个简历文件")

        for attachment in resume_files:
            filename = attachment.get("filename", "")
            logger.info(f"正在处理简历文件: {filename}")

            try:
                # 提取文本内容
                resume_text = self.extract_text_from_attachment(attachment)

                if not resume_text.strip():
                    logger.warning(f"无法从文件 {filename} 中提取文本内容")
                    continue

                logger.info(f"从 {filename} 提取了 {len(resume_text)} 字符的文本")

                # 使用AI提取结构化数据
                resume_data = await self.extract_resume_data_with_ai(
                    resume_text, filename
                )

                if resume_data:
                    resume_data_list.append(resume_data)
                    logger.info(f"成功提取简历数据: {resume_data.name} ({filename})")
                else:
                    logger.error(f"无法从 {filename} 提取简历数据")

            except Exception as e:
                logger.error(f"处理简历文件 {filename} 时出错: {e}")
                continue

        logger.info(f"简历处理完成，成功提取 {len(resume_data_list)} 份简历数据")
        return resume_data_list

    def has_resume_attachments(self, attachments: List[Dict]) -> bool:
        """检查是否包含简历附件"""
        if not attachments:
            return False

        resume_extensions = [".docx", ".doc", ".pdf", ".xlsx", ".xls"]
        engineer_patterns = [
            r"履歴書",
            r"職務経歴",
            r"スキルシート",
            r"resume",
            r"cv",
            r"profile",
        ]

        for attachment in attachments:
            filename = attachment.get("filename", "").lower()

            # 检查文件扩展名
            has_resume_extension = any(
                filename.endswith(ext) for ext in resume_extensions
            )

            # 检查文件名关键词
            has_resume_keyword = any(
                re.search(pattern, filename) for pattern in engineer_patterns
            )

            if has_resume_extension or has_resume_keyword:
                return True

        return False
