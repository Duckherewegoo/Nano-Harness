"""
文件操作 Skill
==============
提供安全的文件操作能力（基于现代 pathlib 与 Pydantic 校验）。
"""
import logging
import os
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool, BaseTool
from pydantic import BaseModel, Field

from ..base import BaseSkill

logger = logging.getLogger(__name__)

# ================= 工具参数定义 (Agent 标准) =================

class ReadFileInput(BaseModel):
    file_path: str = Field(..., description="要读取的文件路径（相对于工作目录）")

class WriteFileInput(BaseModel):
    file_path: str = Field(..., description="要写入的文件路径")
    content: str = Field(..., description="要写入的文本内容")

class ListDirectoryInput(BaseModel):
    dir_path: str = Field(".", description="要列出的目录路径，默认为当前目录")
    show_hidden: bool = Field(False, description="是否显示以点开头的隐藏文件")

class SearchFilesInput(BaseModel):
    pattern: str = Field(..., description="搜索通配符，如 *.py 或 **/*.txt")
    dir_path: str = Field(".", description="搜索的起始目录")

class FileInfoInput(BaseModel):
    file_path: str = Field(..., description="要查询信息的文件或目录路径")

class CreateDirInput(BaseModel):
    dir_path: str = Field(..., description="要创建的目录路径")


# ================= 核心 Skill =================

class FileSkill(BaseSkill):
    """
    文件操作 Skill
    带有严格的工作目录防越权和软链接保护。
    """
    
    name: str = "file"
    description: str = "文件和目录操作能力，包括文件读写、目录浏览、文件搜索等。"
    version: str = "1.1.0"
    author: str = "nano-harness"
    category: str = "system"
    tags: list[str] = ["file", "directory", "io", "filesystem"]
    
    def __init__(self, work_dir: str = "."):
        super().__init__()
        # 使用 Path 对象并 resolve() 解析所有软链接，获得真实的绝对路径
        self.work_dir = Path(work_dir).resolve()
    
    def get_tools(self) -> list[BaseTool]:
        """返回标准化的 LangChain 工具列表"""
        return [
            StructuredTool.from_function(
                func=self._safe_read_file,
                name="read_file",
                description="读取文本文件内容。禁止读取二进制文件（如图片/视频）。",
                args_schema=ReadFileInput,
            ),
            StructuredTool.from_function(
                func=self._safe_write_file,
                name="write_file",
                description="写入内容到文件（覆盖原内容），如果父目录不存在会自动创建。",
                args_schema=WriteFileInput,
            ),
            StructuredTool.from_function(
                func=self._safe_list_directory,
                name="list_directory",
                description="列出指定目录下的文件和子目录，包含大小信息。",
                args_schema=ListDirectoryInput,
            ),
            StructuredTool.from_function(
                func=self._safe_search_files,
                name="search_files",
                description="按通配符搜索文件（如 *.py），返回相对路径列表，最多返回 50 个结果。",
                args_schema=SearchFilesInput,
            ),
            StructuredTool.from_function(
                func=self._safe_get_file_info,
                name="get_file_info",
                description="获取文件或目录的详细属性（大小、创建时间、修改时间等）。",
                args_schema=FileInfoInput,
            ),
            StructuredTool.from_function(
                func=self._safe_create_directory,
                name="create_directory",
                description="创建一个或多个目录（类似 mkdir -p）。",
                args_schema=CreateDirInput,
            ),
        ]

    # ================= 安全包装器 =================

    def _safe_read_file(self, file_path: str) -> str:
        try:
            return self._read_file_internal(file_path)
        except Exception as e:
            return f"Error: 读取文件失败 ({str(e)})"

    def _safe_write_file(self, file_path: str, content: str) -> str:
        try:
            return self._write_file_internal(file_path, content)
        except Exception as e:
            return f"Error: 写入文件失败 ({str(e)})"

    def _safe_list_directory(self, dir_path: str = ".", show_hidden: bool = False) -> str:
        try:
            return self._list_dir_internal(dir_path, show_hidden)
        except Exception as e:
            return f"Error: 列出目录失败 ({str(e)})"

    def _safe_search_files(self, pattern: str, dir_path: str = ".") -> str:
        try:
            return self._search_files_internal(pattern, dir_path)
        except Exception as e:
            return f"Error: 搜索文件失败 ({str(e)})"

    def _safe_get_file_info(self, file_path: str) -> str:
        try:
            return self._get_info_internal(file_path)
        except Exception as e:
            return f"Error: 获取信息失败 ({str(e)})"

    def _safe_create_directory(self, dir_path: str) -> str:
        try:
            return self._create_dir_internal(dir_path)
        except Exception as e:
            return f"Error: 创建目录失败 ({str(e)})"

    # ================= 核心安全机制 =================

    def _get_safe_path(self, path_str: str) -> Path:
        """
        极其硬核的路径安全校验：
        1. 解析为绝对路径。
        2. resolve() 解决所有 `..` 和软链接（symlink）。
        3. 使用 is_relative_to 严格判断是否在工作区内。
        """
        # 拼接到工作目录下，然后 resolve()
        target_path = (self.work_dir / path_str).resolve()
        
        # Python 3.9+ 提供的严格父子目录判断
        if not target_path.is_relative_to(self.work_dir):
            raise ValueError(f"安全拦截：路径越权访问 ({path_str})")
            
        return target_path

    # ================= 具体业务实现 =================

    def _read_file_internal(self, file_path: str) -> str:
        path = self._get_safe_path(file_path)
        
        if not path.exists():
            return f"❌ 文件不存在：{file_path}"
        if path.is_dir():
            return f"❌ 这是一个目录，不是文件：{file_path}"
            
        # 限制最大读取 50KB，防止大文件撑爆大模型上下文
        file_size = path.stat().st_size
        if file_size > 50 * 1024:
            return f"❌ 拒绝读取：文件过大 ({file_size / 1024:.1f} KB)，仅支持读取 50KB 以下的文本文件。"

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            
        if not content.strip():
            return "文件内容为空。"
            
        return f"【文件内容：{file_path}】\n\n{content}"

    def _write_file_internal(self, file_path: str, content: str) -> str:
        path = self._get_safe_path(file_path)
        
        # 自动创建父目录
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            
        size = len(content.encode("utf-8"))
        return f"文件已成功写入：{file_path} ({size} 字节)"

    def _list_dir_internal(self, dir_path: str, show_hidden: bool) -> str:
        path = self._get_safe_path(dir_path)
        
        if not path.exists():
            return f"❌ 目录不存在：{dir_path}"
        if not path.is_dir():
            return f"❌ 这不是一个目录：{dir_path}"
            
        dirs = []
        files = []
        
        for entry in path.iterdir():
            if not show_hidden and entry.name.startswith("."):
                continue
                
            if entry.is_dir():
                dirs.append(f"📁 {entry.name}/")
            else:
                size_str = self._format_size(entry.stat().st_size)
                files.append(f"📄 {entry.name} ({size_str})")
                
        if not dirs and not files:
            return f"📂 目录为空：{dir_path}"
            
        result = [f"📂 目录内容：{dir_path}\n"]
        if dirs:
            result.append("【子目录】")
            result.extend(sorted(dirs))
            result.append("")
        if files:
            result.append("【文件】")
            result.extend(sorted(files))
            
        return "\n".join(result)

    def _search_files_internal(self, pattern: str, dir_path: str) -> str:
        path = self._get_safe_path(dir_path)
        
        # 使用 rglob 进行递归搜索
        if pattern.startswith("**/"):
            pattern = pattern[3:] # 剥离前缀，因为 rglob 默认就是递归
            
        results = list(path.rglob(pattern))
        # 只保留文件，且不超过 50 个
        valid_files = [r for r in results if r.is_file()][:50]
        
        if not valid_files:
            return f"🔍 未找到匹配 '{pattern}' 的文件。"
            
        lines = [f"🔍 搜索结果：找到 {len(valid_files)} 个文件"]
        for f in valid_files:
            # 返回相对工作区的路径，方便大模型后续操作
            rel_path = f.relative_to(self.work_dir)
            lines.append(f"- {rel_path}")
            
        if len(results) > 50:
            lines.append(f"... 结果已截断，仅显示前 50 个。")
            
        return "\n".join(lines)

    def _get_info_internal(self, file_path: str) -> str:
        path = self._get_safe_path(file_path)
        
        if not path.exists():
            return f"❌ 路径不存在：{file_path}"
            
        stat = path.stat()
        import datetime
        
        # 统一使用 datetime 转换时间
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        
        lines = [
            f"【文件信息：{file_path}】",
            f"类型：{'目录' if path.is_dir() else '文件'}",
            f"绝对路径：{path}",
            f"大小：{self._format_size(stat.st_size)}",
            f"最后修改：{mtime}"
        ]
        return "\n".join(lines)

    def _create_dir_internal(self, dir_path: str) -> str:
        path = self._get_safe_path(dir_path)
        if path.exists():
            return f"ℹ️ 目录已存在：{dir_path}"
            
        path.mkdir(parents=True, exist_ok=True)
        return f"目录创建成功：{dir_path}"

    # ================= 辅助方法 =================

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.1f} MB"
