"""
PDF转Markdown模块
使用marker-pdf进行高质量学术论文转换
功能：
- 调用marker将PDF转为Markdown
- 保留公式、表格、引用结构
- 处理转换失败的情况
"""

import subprocess
import os
from pathlib import Path
from typing import Optional, Tuple, Dict
import logging
import shutil

logger = logging.getLogger(__name__)


class PDFConverter:
    """PDF转Markdown转换器"""

    def __init__(self, config: Dict):
        """
        初始化转换器

        Args:
            config: 配置字典
        """
        self.pdf_dir = Path(config.get("paths", {}).get("pdfs", "./data/pdfs"))
        self.md_dir = Path(config.get("paths", {}).get("markdown", "./data/markdown"))

        # 确保目录存在
        self.md_dir.mkdir(parents=True, exist_ok=True)

        # 检查marker是否安装
        self._check_marker_installed()

    def _check_marker_installed(self):
        """检查marker-pdf是否已安装"""
        if not shutil.which("marker_single"):
            logger.warning(
                "marker-pdf未安装或不在PATH中。"
                "请运行: pip install marker-pdf"
            )

    def convert(self, pdf_path: Path, output_dir: Optional[Path] = None,
                use_fallback: bool = True) -> Tuple[bool, Optional[Path]]:
        """
        将PDF转换为Markdown

        Args:
            pdf_path: PDF文件路径
            output_dir: 输出目录，默认使用配置的markdown目录
            use_fallback: 如果marker失败，是否使用PyMuPDF备用方案

        Returns:
            (成功标志, markdown文件路径)
        """
        if not pdf_path.exists():
            logger.error(f"PDF文件不存在: {pdf_path}")
            return False, None

        if output_dir is None:
            output_dir = self.md_dir

        output_dir.mkdir(parents=True, exist_ok=True)

        # 输出文件名
        output_name = pdf_path.stem
        output_path = output_dir / f"{output_name}.md"

        # 如果已存在且跳过
        if output_path.exists():
            logger.info(f"Markdown已存在: {output_path}")
            return True, output_path

        # 首先尝试使用marker
        success, md_path = self._convert_with_marker(pdf_path, output_dir, output_name)

        if success:
            return True, md_path

        # marker失败，尝试备用方案
        if use_fallback:
            logger.info("尝试使用PyMuPDF备用转换...")
            success = convert_pdf_to_markdown_fallback(pdf_path, output_path)
            if success:
                return True, output_path

        return False, None

    def _convert_with_marker(self, pdf_path: Path, output_dir: Path,
                              output_name: str) -> Tuple[bool, Optional[Path]]:
        """使用marker转换"""
        try:
            logger.info(f"使用marker转换PDF: {pdf_path}")

            # 使用marker_single命令行工具
            cmd = [
                "marker_single",
                str(pdf_path),
                "--output_dir", str(output_dir),
                "--output_format", "markdown"
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10分钟超时
            )

            if result.returncode != 0:
                logger.error(f"marker转换失败: {result.stderr}")
                return False, None

            # marker输出文件名格式: {output_dir}/{pdf_name}/{pdf_name}.md
            possible_output = output_dir / output_name / f"{output_name}.md"
            if possible_output.exists():
                # 移动到目标位置
                final_path = output_dir / f"{output_name}.md"
                possible_output.rename(final_path)
                # 删除临时目录
                temp_dir = output_dir / output_name
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                logger.info(f"marker转换完成: {final_path}")
                return True, final_path

            # 检查其他可能的输出位置
            for f in output_dir.rglob("*.md"):
                if output_name in f.name:
                    logger.info(f"marker转换完成: {f}")
                    return True, f

            logger.error(f"找不到marker输出文件")
            return False, None

        except subprocess.TimeoutExpired:
            logger.error(f"marker转换超时: {pdf_path}")
            return False, None
        except Exception as e:
            logger.error(f"marker转换异常: {e}")
            return False, None

    def convert_batch(self, pdf_paths: list) -> dict:
        """
        批量转换PDF

        Args:
            pdf_paths: PDF文件路径列表

        Returns:
            {pdf_path: markdown_path} 字典
        """
        results = {}
        for pdf_path in pdf_paths:
            success, md_path = self.convert(Path(pdf_path))
            if success and md_path:
                results[str(pdf_path)] = md_path
        return results

    def convert_from_arxiv_id(self, arxiv_id: str) -> Tuple[bool, Optional[Path]]:
        """
        根据arXiv ID转换PDF

        Args:
            arxiv_id: arXiv论文ID

        Returns:
            (成功标志, markdown文件路径)
        """
        pdf_path = self.pdf_dir / f"{arxiv_id}.pdf"
        return self.convert(pdf_path)


def convert_pdf_to_markdown_fallback(pdf_path: Path, output_path: Path) -> bool:
    """
    备用转换方法（使用PyMuPDF）
    当marker不可用时使用

    Args:
        pdf_path: PDF文件路径
        output_path: 输出Markdown路径

    Returns:
        成功标志
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)
        text_parts = []

        for page_num, page in enumerate(doc):
            text = page.get_text()
            text_parts.append(f"## Page {page_num + 1}\n\n{text}\n")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(text_parts))

        logger.info(f"备用转换完成: {output_path}")
        return True

    except ImportError:
        logger.error("PyMuPDF未安装，无法使用备用转换")
        return False
    except Exception as e:
        logger.error(f"备用转换失败: {e}")
        return False


def main():
    """测试入口"""
    import yaml

    # 加载配置
    with open("config/settings.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    converter = PDFConverter(config)

    # 查找已下载的PDF
    pdf_dir = Path(config["paths"]["pdfs"])
    pdf_files = list(pdf_dir.glob("*.pdf"))

    if pdf_files:
        print(f"找到 {len(pdf_files)} 个PDF文件")
        success, md_path = converter.convert(pdf_files[0])
        if success:
            print(f"转换成功: {md_path}")
        else:
            print("转换失败")
    else:
        print("没有找到PDF文件，请先下载论文")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
