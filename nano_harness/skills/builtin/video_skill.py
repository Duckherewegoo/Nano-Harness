"""
视频处理 Skill
==============
将视频处理能力封装为标准的 Agent Skill。
"""
import logging
import os
from typing import Any

from langchain_core.tools import StructuredTool, BaseTool
from pydantic import BaseModel, Field

from ...multimodal.video import VideoProcessor
from ..base import BaseSkill

logger = logging.getLogger(__name__)

# ================= 定义工具的输入 Schema =================

class VideoPathInput(BaseModel):
    video_path: str = Field(..., description="视频文件的绝对或相对路径")

class ExtractFramesInput(BaseModel):
    video_path: str = Field(..., description="视频文件的绝对或相对路径")
    output_dir: str = Field(..., description="提取出的图片保存目录")
    frame_interval: float = Field(1.0, description="提取帧的时间间隔（秒），默认 1.0")
    max_frames: int = Field(100, description="最大提取帧数，默认 100")

class SummarizeVideoInput(BaseModel):
    video_path: str = Field(..., description="视频文件的绝对或相对路径")
    max_frames: int = Field(10, description="用于分析的视频关键帧数量，默认 10")

class ExtractAudioInput(BaseModel):
    video_path: str = Field(..., description="源视频文件路径")
    output_path: str = Field(..., description="提取出的音频文件保存路径（如 output.mp3）")


# ================= 核心 Skill =================

class VideoSkill(BaseSkill):
    """
    视频处理 Skill
    提供视频信息查询、帧提取、摘要分析、音频轨道提取等能力。
    """
    
    name: str = "video"
    description: str = "视频处理和分析能力，包括视频属性查询、帧提取、视频内容摘要等"
    version: str = "1.1.0"
    author: str = "nano-harness"
    category: str = "multimodal"
    tags: list[str] = ["video", "multimedia", "frames", "summary"]

    def __init__(self, video_processor: VideoProcessor | None = None):
        super().__init__()
        self._processor = video_processor

    @property
    def processor(self) -> VideoProcessor:
        """延迟加载 VideoProcessor，防止在缺少多模态依赖时导致整个注册中心崩溃"""
        if self._processor is None:
            self._processor = VideoProcessor()
        return self._processor

    def initialize(self, context: dict | None = None):
        """标准生命周期钩子：加载底层依赖"""
        super().initialize(context)
        # 触发一次加载，尽早发现 opencv / ffmpeg 等依赖是否缺失
        _ = self.processor

    def get_tools(self) -> list[BaseTool]:
        """返回标准化的 LangChain 工具列表"""
        return [
            StructuredTool.from_function(
                func=self._safe_get_video_info,
                name="get_video_info",
                description="获取视频基本信息（时长、分辨率、帧率、编码格式等）。不消耗大量 Token。",
                args_schema=VideoPathInput,
            ),
            StructuredTool.from_function(
                func=self._safe_extract_frames,
                name="extract_video_frames",
                description="按指定时间间隔提取视频帧，并保存为图片文件。注意：这可能会产生大量图片。",
                args_schema=ExtractFramesInput,
            ),
            StructuredTool.from_function(
                func=self._safe_summarize,
                name="summarize_video",
                description="视频内容摘要。自动提取关键帧，分析并生成视频内容的文字摘要。",
                args_schema=SummarizeVideoInput,
            ),
            StructuredTool.from_function(
                func=self._safe_extract_audio,
                name="extract_audio_from_video",
                description="从视频中剥离音频轨道，并保存为独立的音频文件（如 mp3/wav）。",
                args_schema=ExtractAudioInput,
            ),
        ]

    # ================= 安全包装器 =================

    def _safe_get_video_info(self, video_path: str) -> str:
        try:
            return self._get_video_info_internal(video_path)
        except Exception as e:
            logger.error(f"[VideoSkill] 获取视频信息失败: {e}", exc_info=True)
            return f"Error: 获取视频信息失败 ({str(e)})"

    def _safe_extract_frames(self, video_path: str, output_dir: str, frame_interval: float = 1.0, max_frames: int = 100) -> str:
        try:
            return self._extract_frames_internal(video_path, output_dir, frame_interval, max_frames)
        except Exception as e:
            logger.error(f"[VideoSkill] 提取视频帧失败: {e}", exc_info=True)
            return f"Error: 提取视频帧失败 ({str(e)})"

    def _safe_summarize(self, video_path: str, max_frames: int = 10) -> str:
        try:
            return self._summarize_internal(video_path, max_frames)
        except Exception as e:
            logger.error(f"[VideoSkill] 视频摘要失败: {e}", exc_info=True)
            return f"Error: 视频摘要失败 ({str(e)})"

    def _safe_extract_audio(self, video_path: str, output_path: str) -> str:
        try:
            success = self.processor.extract_audio(video_path, output_path)
            if success:
                return f"音频提取成功，保存至：{output_path}"
            return "❌ 音频提取失败，请检查 FFmpeg 是否可用以及视频是否包含音频轨道。"
        except Exception as e:
            logger.error(f"[VideoSkill] 提取音频失败: {e}", exc_info=True)
            return f"Error: 提取音频失败 ({str(e)})"

    # ================= 具体业务实现 =================

    def _get_video_info_internal(self, video_path: str) -> str:
        if not os.path.exists(video_path):
            return f"❌ 视频文件不存在：{video_path}"

        info = self.processor.get_info(video_path)
        
        if not info.get("exists"):
            return f"❌ 无法读取视频信息，可能格式不受支持：{video_path}"
        
        lines = ["【视频信息】", f"文件：{info.get('path', 'N/A')}"]
        
        if info.get("file_size"):
            lines.append(f"大小：{info['file_size'] / (1024 * 1024):.2f} MB")
        
        if info.get("duration"):
            duration = info["duration"]
            lines.append(f"时长：{int(duration // 60)}分{int(duration % 60)}秒 ({duration:.1f}秒)")
        
        if info.get("width") and info.get("height"):
            lines.append(f"分辨率：{info['width']} x {info['height']}")
        
        if info.get("fps"):
            lines.append(f"帧率：{info['fps']:.2f} fps")
        
        if info.get("video_codec"):
            lines.append(f"视频编码：{info['video_codec']}")
        
        if info.get("audio_codec"):
            lines.append(f"音频编码：{info['audio_codec']}")
            if info.get("sample_rate"):
                lines.append(f"采样率：{info['sample_rate']} Hz")
            if info.get("channels"):
                lines.append(f"声道数：{info['channels']}")
        
        return "\n".join(lines)

    def _extract_frames_internal(self, video_path: str, output_dir: str, frame_interval: float, max_frames: int) -> str:
        if not os.path.exists(video_path):
            return f"❌ 视频文件不存在：{video_path}"

        os.makedirs(output_dir, exist_ok=True)

        frames = self.processor.extract_frames(
            video_path, output_dir,
            frame_interval=frame_interval,
            max_frames=max_frames,
        )
        
        if not frames:
            return "❌ 提取帧失败，请检查 OpenCV 是否可用或视频文件是否损坏。"
        
        lines = [f"成功提取 {len(frames)} 帧", f"输出目录：{output_dir}", ""]
        lines.append("前 5 帧预览：")
        for i, frame in enumerate(frames[:5]):
            lines.append(f"  {i+1}. {os.path.basename(frame)}")
        
        if len(frames) > 5:
            lines.append(f"  ... 还有 {len(frames) - 5} 帧（不再列出）")
        
        return "\n".join(lines)

    def _summarize_internal(self, video_path: str, max_frames: int) -> str:
        if not os.path.exists(video_path):
            return f"❌ 视频文件不存在：{video_path}"

        result = self.processor.summarize(video_path, max_frames=max_frames)
        
        lines = ["【视频摘要】"]
        
        info = result.get("video_info", {})
        if info.get("duration"):
            lines.append(f"视频时长：{info['duration']:.1f} 秒")
        if info.get("width") and info.get("height"):
            lines.append(f"分辨率：{info['width']} x {info['height']}")
        
        key_frames = result.get("key_frames", [])
        lines.append(f"提取关键帧：{len(key_frames)} 帧")
        
        summary = result.get("summary")
        if summary:
            lines.append("\n📝 内容摘要：")
            lines.append(summary.strip())
        else:
            lines.append("\n⚠️ 未能生成摘要，可能是多模态模型未配置或视频无有效画面。")
        
        return "\n".join(lines)
