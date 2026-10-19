"""
音频处理 Skill
==============
将音频处理能力封装为标准的 Agent Skill。
"""
import logging
from typing import Any, Type
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool, BaseTool

from ...multimodal.audio import AudioProcessor
from ..base import BaseSkill

logger = logging.getLogger(__name__)

# ================= 定义工具的输入 Schema (极高标准) =================

class AudioInfoInput(BaseModel):
    audio_path: str = Field(..., description="音频文件的绝对或相对路径")

class TranscribeInput(BaseModel):
    audio_path: str = Field(..., description="音频文件的绝对或相对路径")
    language: str = Field("auto", description="语言代码，默认 auto 自动检测，如 zh, en")

class ConvertInput(BaseModel):
    input_path: str = Field(..., description="输入音频文件路径")
    output_path: str = Field(..., description="输出音频文件路径")
    format: str = Field("mp3", description="目标格式，如 mp3, wav, flac")

# ================= 核心 Skill 定义 =================

class AudioSkill(BaseSkill):
    """
    音频处理Skill
    提供音频信息查询、语音转文字、音频分析、格式转换等能力。
    """
    
    name: str = "audio"
    description: str = "音频处理和分析能力，包括语音转文字(STT)、音频信息查询、特征分析等"
    version: str = "1.1.0"
    author: str = "nano-harness"
    category: str = "multimodal"
    tags: list[str] = ["audio", "speech", "stt", "multimedia", "transcription"]

    def __init__(self, audio_processor: AudioProcessor | None = None):
        super().__init__()
        self._processor = audio_processor

    @property
    def processor(self) -> AudioProcessor:
        """延迟加载 AudioProcessor，防止在缺少依赖时导致整个注册中心崩溃"""
        if self._processor is None:
            self._processor = AudioProcessor()
        return self._processor

    def initialize(self, context: dict | None = None):
        """标准生命周期钩子：加载底层依赖"""
        super().initialize(context)
        # 触发一次加载，尽早发现 ffmpeg 等依赖是否缺失
        _ = self.processor 

    def get_tools(self) -> list[BaseTool]:
        """返回标准化的 LangChain 工具列表"""
        return [
            StructuredTool.from_function(
                func=self._safe_get_audio_info,
                name="get_audio_info",
                description="获取音频的基本信息（时长、采样率、声道数、编码格式等）。",
                args_schema=AudioInfoInput,
            ),
            StructuredTool.from_function(
                func=self._safe_transcribe_audio,
                name="transcribe_audio",
                description="语音转文字（STT）。将音频中的语音内容转录为文字，支持中英文。",
                args_schema=TranscribeInput,
            ),
            StructuredTool.from_function(
                func=self._safe_analyze_audio,
                name="analyze_audio",
                description="综合分析音频。返回基本信息、语音转录以及音频能量/过零率等特征。",
                args_schema=AudioInfoInput,
            ),
            StructuredTool.from_function(
                func=self._safe_convert_audio_format,
                name="convert_audio_format",
                description="转换音频格式（mp3/wav/flac/ogg等）。需要系统已安装 ffmpeg。",
                args_schema=ConvertInput,
            ),
        ]

    # ===== 安全包装器（防御大模型幻觉与底层崩溃） =====

    def _safe_get_audio_info(self, audio_path: str) -> str:
        try:
            return self._get_audio_info(audio_path)
        except Exception as e:
            logger.error(f"[AudioSkill] 获取音频信息失败: {e}", exc_info=True)
            return f"Error: 获取音频信息失败 ({str(e)})"

    def _safe_transcribe_audio(self, audio_path: str, language: str = "auto") -> str:
        try:
            return self._transcribe_audio(audio_path, language)
        except Exception as e:
            logger.error(f"[AudioSkill] 语音转录失败: {e}", exc_info=True)
            return f"Error: 语音转录失败 ({str(e)})"

    def _safe_analyze_audio(self, audio_path: str) -> str:
        try:
            return self._analyze_audio(audio_path)
        except Exception as e:
            logger.error(f"[AudioSkill] 音频分析失败: {e}", exc_info=True)
            return f"Error: 音频分析失败 ({str(e)})"

    def _safe_convert_audio_format(self, input_path: str, output_path: str, format: str = "mp3") -> str:
        try:
            return self._convert_audio_format(input_path, output_path, format)
        except Exception as e:
            logger.error(f"[AudioSkill] 音频格式转换失败: {e}", exc_info=True)
            return f"Error: 格式转换失败 ({str(e)})"

    # ===== 具体业务实现 =====

    def _get_audio_info(self, audio_path: str) -> str:
        info = self.processor.get_info(audio_path)
        
        if not info.get("exists"):
            return f"❌ 音频文件不存在：{audio_path}"
        
        lines = ["【音频信息】", f"文件：{info.get('path', 'N/A')}"]
        
        if info.get("file_size"):
            lines.append(f"大小：{info['file_size'] / (1024 * 1024):.2f} MB")
        
        if info.get("duration"):
            duration = info["duration"]
            lines.append(f"时长：{int(duration // 60)}分{int(duration % 60)}秒 ({duration:.1f}秒)")
        
        if info.get("sample_rate"):
            lines.append(f"采样率：{info['sample_rate']} Hz")
        
        if info.get("channels"):
            ch_name = {1: "单声道", 2: "立体声"}.get(info["channels"], f"{info['channels']}声道")
            lines.append(f"声道：{ch_name}")
        
        if info.get("codec"):
            lines.append(f"编码：{info['codec']}")
        
        if info.get("bit_rate"):
            lines.append(f"比特率：{info['bit_rate'] // 1000} kbps")
        
        return "\n".join(lines)

    def _transcribe_audio(self, audio_path: str, language: str = "auto") -> str:
        result = self.processor.transcribe(audio_path, language=language)
        
        if not result.get("success"):
            return f"❌ 语音转录失败：{result.get('error', '未知错误')}"
        
        lines = ["【语音转录结果】"]
        
        if result.get("language"):
            lines.append(f"检测语言：{result['language']}")
        
        lines.append("\n转录内容：")
        lines.append(result.get("text", ""))
        
        # 修复语法错误：补全了闭合括号
        if result.get("segments"):
            segments = result["segments"]
            lines.append(f"\n共 {len(segments)} 个语音片段")
        
        return "\n".join(lines)

    def _analyze_audio(self, audio_path: str) -> str:
        result = self.processor.analyze(audio_path)
        lines = ["【音频分析报告】"]
        
        info = result.get("info", {})
        if info.get("duration"):
            lines.append(f"时长：{info['duration']:.1f} 秒")
        if info.get("sample_rate"):
            lines.append(f"采样率：{info['sample_rate']} Hz")
        if info.get("channels"):
            lines.append(f"声道数：{info['channels']}")
        
        if result.get("transcription"):
            trans = result["transcription"]
            if trans.get("success"):
                lines.append("\n📝 语音内容：")
                text = trans.get("text", "")
                lines.append(text[:500] + ("... (内容已截断)" if len(text) > 500 else ""))
        
        features = result.get("features", {})
        if features:
            lines.append("\n📊 音频特征：")
            if "rms_energy" in features:
                lines.append(f"   - 平均能量：{features['rms_energy']:.4f}")
            if "zero_crossing_rate" in features:
                lines.append(f"   - 过零率：{features['zero_crossing_rate']:.4f}")
            if "spectral_centroid" in features:
                lines.append(f"   - 频谱质心：{features['spectral_centroid']:.1f} Hz")
        
        return "\n".join(lines)

    def _convert_audio_format(self, input_path: str, output_path: str, format: str = "mp3") -> str:
        success = self.processor.convert_format(input_path, output_path, format=format)
        if success:
            return f"格式转换成功，保存到：{output_path}"
        return "❌ 格式转换失败，请检查 ffmpeg 或 pydub 是否可用。"
