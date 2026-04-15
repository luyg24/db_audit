"""
知识库存储模块
功能：
- 保存结构化数据为JSON
- 生成可读的Markdown摘要
- 按日期/主题组织文件
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """知识库存储管理"""

    def __init__(self, config: Dict):
        """
        初始化知识库

        Args:
            config: 配置字典
        """
        self.knowledge_dir = Path(config.get("paths", {}).get("knowledge", "./data/knowledge"))
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

    def save_paper(self, paper_info: Dict, extracted_info: Dict,
                   arxiv_id: str, date: Optional[datetime] = None) -> Path:
        """
        保存论文到知识库

        Args:
            paper_info: 论文基本信息（来自arXiv）
            extracted_info: LLM提取的结构化信息
            arxiv_id: arXiv ID
            date: 日期，默认今天

        Returns:
            保存的JSON文件路径
        """
        if date is None:
            date = datetime.now()

        # 按日期组织目录
        date_dir = self.knowledge_dir / date.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        # 合并信息
        full_data = {
            "arxiv_id": arxiv_id,
            "crawl_date": datetime.now().isoformat(),
            "paper_info": paper_info,
            "extracted": extracted_info
        }

        # 保存JSON
        json_path = date_dir / f"{arxiv_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(full_data, f, indent=2, ensure_ascii=False)

        logger.info(f"保存JSON: {json_path}")

        # 生成Markdown摘要
        md_path = date_dir / f"{arxiv_id}_summary.md"
        self._generate_summary(full_data, md_path)

        return json_path

    def _generate_summary(self, data: Dict, output_path: Path):
        """
        生成可读的Markdown摘要

        Args:
            data: 论文完整数据
            output_path: 输出路径
        """
        paper = data.get("paper_info", {})
        extracted = data.get("extracted", {})

        md_content = f"""# {paper.get('title', 'Unknown Title')}

**arXiv ID:** {data.get('arxiv_id', 'N/A')}
**Authors:** {', '.join(paper.get('authors', []))}
**Published:** {paper.get('published', 'N/A')}
**Crawled:** {data.get('crawl_date', 'N/A')}

## Abstract

{paper.get('abstract', 'N/A')}

---

## 核心问题

{extracted.get('problem', 'N/A')}

## 方法

{extracted.get('method', 'N/A')}

## 主要贡献

"""
        contributions = extracted.get('contribution', [])
        if isinstance(contributions, list):
            for c in contributions:
                md_content += f"- {c}\n"
        else:
            md_content += str(contributions)

        md_content += f"""
## 实验结果

{extracted.get('results', 'N/A')}

## 局限性

{extracted.get('limitations', 'N/A')}

## 未来工作

{extracted.get('future_work', 'N/A')}

## 关键词

{', '.join(extracted.get('keywords', []))}

---

**PDF:** {paper.get('pdf_url', 'N/A')}
**Categories:** {', '.join(paper.get('categories', []))}
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        logger.info(f"生成摘要: {output_path}")

    def get_paper(self, arxiv_id: str) -> Optional[Dict]:
        """
        获取论文数据

        Args:
            arxiv_id: arXiv ID

        Returns:
            论文数据字典，不存在返回None
        """
        # 在所有日期目录中搜索
        for date_dir in self.knowledge_dir.iterdir():
            if date_dir.is_dir():
                json_path = date_dir / f"{arxiv_id}.json"
                if json_path.exists():
                    with open(json_path, "r", encoding="utf-8") as f:
                        return json.load(f)
        return None

    def exists(self, arxiv_id: str) -> bool:
        """检查论文是否已存在"""
        return self.get_paper(arxiv_id) is not None

    def list_papers(self, date: Optional[datetime] = None) -> List[Dict]:
        """
        列出论文

        Args:
            date: 指定日期，None表示所有

        Returns:
            论文数据列表
        """
        papers = []

        if date:
            date_dir = self.knowledge_dir / date.strftime("%Y-%m-%d")
            if date_dir.exists():
                papers.extend(self._load_papers_from_dir(date_dir))
        else:
            for date_dir in sorted(self.knowledge_dir.iterdir(), reverse=True):
                if date_dir.is_dir():
                    papers.extend(self._load_papers_from_dir(date_dir))

        return papers

    def _load_papers_from_dir(self, dir_path: Path) -> List[Dict]:
        """从目录加载所有论文"""
        papers = []
        for json_file in dir_path.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    papers.append(json.load(f))
            except Exception as e:
                logger.error(f"加载失败 {json_file}: {e}")
        return papers

    def get_statistics(self) -> Dict:
        """获取知识库统计信息"""
        total_papers = 0
        dates = []

        for date_dir in self.knowledge_dir.iterdir():
            if date_dir.is_dir():
                count = len(list(date_dir.glob("*.json")))
                if count > 0:
                    dates.append({
                        "date": date_dir.name,
                        "count": count
                    })
                    total_papers += count

        return {
            "total_papers": total_papers,
            "dates": sorted(dates, reverse=True)
        }

    def generate_daily_report(self, date: Optional[datetime] = None) -> Path:
        """
        生成每日报告

        Args:
            date: 日期，默认今天

        Returns:
            报告文件路径
        """
        if date is None:
            date = datetime.now()

        papers = self.list_papers(date)

        if not papers:
            logger.warning(f"没有找到 {date.strftime('%Y-%m-%d')} 的论文")
            return None

        report_path = self.knowledge_dir / date.strftime("%Y-%m-%d") / "daily_report.md"

        report_content = f"""# 每日论文报告 - {date.strftime('%Y-%m-%d')}

共收集 **{len(papers)}** 篇论文

---

"""
        for i, paper in enumerate(papers, 1):
            info = paper.get("paper_info", {})
            extracted = paper.get("extracted", {})

            report_content += f"""## {i}. [{paper.get('arxiv_id', 'N/A')}] {info.get('title', 'N/A')}

**问题:** {extracted.get('problem', 'N/A')}

**关键词:** {', '.join(extracted.get('keywords', []))}

[查看详情]({paper.get('arxiv_id')}_summary.md)

---

"""

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info(f"生成日报: {report_path}")
        return report_path


def main():
    """测试入口"""
    import yaml

    # 加载配置
    with open("config/settings.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    kb = KnowledgeBase(config)

    # 测试保存
    test_paper = {
        "title": "Test Paper",
        "authors": ["Author 1", "Author 2"],
        "abstract": "This is a test abstract...",
        "published": "2024-01-15",
        "pdf_url": "https://arxiv.org/pdf/2401.12345",
        "categories": ["cs.CR", "cs.DB"]
    }

    test_extracted = {
        "problem": "Test problem",
        "method": "Test method",
        "contribution": ["Contribution 1", "Contribution 2"],
        "results": "Test results",
        "limitations": "Test limitations",
        "keywords": ["test", "paper", "audit"]
    }

    kb.save_paper(test_paper, test_extracted, "2401.12345")

    # 打印统计
    stats = kb.get_statistics()
    print(f"统计: {stats}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
