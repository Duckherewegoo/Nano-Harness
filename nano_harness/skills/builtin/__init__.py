"""
内置 Skill 包
==============
系统内置的常用Skill。

包含：
- BashSkill: 执行Shell命令（带用户确认）
- ImageSkill: 图像处理能力
- VideoSkill: 视频处理能力
- AudioSkill: 音频处理能力
- FileSkill: 文件操作能力
"""

from .audio_skill import AudioSkill
from .bash_skill import BashSkill
from .file_skill import FileSkill
from .image_skill import ImageSkill
from .video_skill import VideoSkill

__all__ = [
    "AudioSkill",
    "BashSkill",
    "FileSkill",
    "ImageSkill",
    "VideoSkill",
]
