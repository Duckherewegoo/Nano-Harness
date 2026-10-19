"""
内置 Skill 包
==============
系统内置的常用 Skill。

包含：
- BashSkill: 执行 Shell 命令（带用户确认）
- ImageSkill: 图像处理能力（依赖 opencv/PIL）
- VideoSkill: 视频处理能力（依赖 opencv/ffmpeg）
- AudioSkill: 音频处理能力（依赖 pydub/ffmpeg）
- FileSkill: 文件操作能力
"""

from typing import TYPE_CHECKING

# 仅在类型检查（如 IDE 补全）时导入，运行时绝对不加载
if TYPE_CHECKING:
    from .audio_skill import AudioSkill
    from .bash_skill import BashSkill
    from .file_skill import FileSkill
    from .image_skill import ImageSkill
    from .video_skill import VideoSkill


def __getattr__(name: str):
    """
    PEP 562 惰性加载：只有真正用到某个 Skill 时，才去导入它对应的模块。
    这样可以避免只想要轻量级 BashSkill 时，被迫加载 OpenCV 或 PyTorch。
    """
    if name == "AudioSkill":
        from .audio_skill import AudioSkill
        return AudioSkill
    elif name == "BashSkill":
        from .bash_skill import BashSkill
        return BashSkill
    elif name == "FileSkill":
        from .file_skill import FileSkill
        return FileSkill
    elif name == "ImageSkill":
        from .image_skill import ImageSkill
        return ImageSkill
    elif name == "VideoSkill":
        from .video_skill import VideoSkill
        return VideoSkill
        
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AudioSkill",
    "BashSkill",
    "FileSkill",
    "ImageSkill",
    "VideoSkill",
]
