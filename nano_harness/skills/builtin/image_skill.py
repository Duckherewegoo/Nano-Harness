"""
图片处理 Skill
==============
将图像处理能力封装为标准的 Agent Skill。
"""
import logging
from typing import Any

from langchain_core.tools import StructuredTool, BaseTool
from pydantic import BaseModel, Field

from ...multimodal.image import ImageProcessor
from ..base import BaseSkill

logger = logging.getLogger(__name__)

# ================= 定义工具的输入 Schema =================

class ImagePathInput(BaseModel):
    image_path: str = Field(
        ..., 
        description="图片文件的绝对路径、相对路径或网络 URL"
    )

# ================= 核心 Skill =================

class ImageSkill(BaseSkill):
    """
    图片处理 Skill
    提供图片理解、分析、OCR 等能力。
    """
    
    name: str = "image"
    description: str = "图片理解和分析能力，包括图片描述、文字识别(OCR)、图像特征分析等"
    version: str = "1.1.0"
    author: str = "nano-harness"
    category: str = "multimodal"
    tags: list[str] = ["image", "vision", "ocr", "multimodal"]

    def __init__(self, image_processor: ImageProcessor | None = None):
        super().__init__()
        self._processor = image_processor

    @property
    def processor(self) -> ImageProcessor:
        """延迟加载 ImageProcessor，防止在缺少多模态依赖时导致整个注册中心崩溃"""
        if self._processor is None:
            self._processor = ImageProcessor()
        return self._processor

    def initialize(self, context: dict | None = None):
        """标准生命周期钩子：加载底层依赖"""
        super().initialize(context)
        # 触发一次加载，尽早发现 opencv / tesseract 等依赖是否缺失
        _ = self.processor

    def get_tools(self) -> list[BaseTool]:
        """返回标准化的 LangChain 工具列表"""
        return [
            StructuredTool.from_function(
                func=self._safe_describe_image,
                name="describe_image",
                description="描述图片内容。输入图片路径或URL，返回图片的文字描述，可识别物体、场景、人物。",
                args_schema=ImagePathInput,
            ),
            StructuredTool.from_function(
                func=self._safe_extract_text,
                name="extract_text_from_image",
                description="从图片中提取文字（OCR）。识别图片中的文字内容，支持中英文。",
                args_schema=ImagePathInput,
            ),
            StructuredTool.from_function(
                func=self._safe_analyze_image,
                name="analyze_image",
                description="综合分析图片。返回内容描述、文字提取、颜色分析、尺寸信息等全面数据。",
                args_schema=ImagePathInput,
            ),
            StructuredTool.from_function(
                func=self._safe_get_info,
                name="get_image_info",
                description="获取图片基本信息。返回尺寸、格式、大小、色彩模式等元数据，不消耗大模型 Token。",
                args_schema=ImagePathInput,
            ),
        ]

    # ================= 安全包装器 =================

    def _safe_describe_image(self, image_path: str) -> str:
        try:
            return self.processor.describe(image_path)
        except Exception as e:
            logger.error(f"[ImageSkill] 图片描述失败: {e}", exc_info=True)
            return f"Error: 无法描述图片 ({str(e)})"

    def _safe_extract_text(self, image_path: str) -> str:
        try:
            text = self.processor.extract_text(image_path)
            if not text or not text.strip():
                return "图片中未检测到清晰的文字。"
            return text
        except Exception as e:
            logger.error(f"[ImageSkill] OCR 识别失败: {e}", exc_info=True)
            return f"Error: OCR 识别失败 ({str(e)})"

    def _safe_analyze_image(self, image_path: str) -> str:
        try:
            return self._analyze_image_internal(image_path)
        except Exception as e:
            logger.error(f"[ImageSkill] 图片综合分析失败: {e}", exc_info=True)
            return f"Error: 分析图片失败 ({str(e)})"

    def _safe_get_info(self, image_path: str) -> str:
        try:
            return self._get_info_internal(image_path)
        except Exception as e:
            logger.error(f"[ImageSkill] 获取图片信息失败: {e}", exc_info=True)
            return f"Error: 获取图片信息失败 ({str(e)})"

    # ================= 具体业务实现 =================

    def _analyze_image_internal(self, image_path: str) -> str:
        result = self.processor.analyze(image_path)
        
        lines = ["【图片综合分析】"]
        
        # 1. 内容描述
        desc = result.get("description", "无描述")
        lines.append(f"\n📝 内容描述：\n{desc}")
        
        # 2. 文字识别
        text = result.get("text_detected")
        if text and str(text).strip():
            lines.append(f"\n📄 检测到的文字：\n{text}")
            
        # 3. 颜色分析
        colors = result.get("colors")
        if colors and isinstance(colors, list):
            lines.append(f"\n🎨 主要颜色：{', '.join(colors[:5])}")
            
        # 4. 图片质量与元数据
        quality = result.get("quality", {})
        if quality:
            lines.append("\n📐 图片信息：")
            if "width" in quality and "height" in quality:
                lines.append(f"   - 尺寸：{quality['width']} x {quality['height']}")
            if "format" in quality:
                lines.append(f"   - 格式：{quality['format']}")
            if "mode" in quality:
                lines.append(f"   - 色彩模式：{quality['mode']}")
        
        return "\n".join(lines)

    def _get_info_internal(self, image_path: str) -> str:
        info = self.processor.get_image_info(image_path)
        
        if "error" in info:
            return f"❌ 获取图片信息失败：{info['error']}"
        
        lines = ["【图片元数据】"]
        lines.append(f"路径：{info.get('path', 'N/A')}")
        lines.append(f"尺寸：{info.get('width', '?')} x {info.get('height', '?')} 像素")
        lines.append(f"格式：{info.get('format', 'N/A')}")
        lines.append(f"色彩模式：{info.get('mode', 'N/A')}")
        
        if info.get("size_bytes"):
            size_kb = info["size_bytes"] / 1024
            if size_kb > 1024:
                lines.append(f"文件大小：{size_kb / 1024:.2f} MB")
            else:
                lines.append(f"文件大小：{size_kb:.2f} KB")
        
        return "\n".join(lines)
