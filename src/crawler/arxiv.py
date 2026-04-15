"""
arXiv爬虫模块
功能：
- 按关键词搜索arXiv论文
- 按日期范围筛选（每日增量）
- 下载PDF到本地
- 返回论文元数据
"""

import arxiv
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class PaperInfo:
    """论文信息数据类"""
    def __init__(self, arxiv_id: str, title: str, authors: List[str],
                 abstract: str, published: datetime, pdf_url: str,
                 categories: List[str]):
        self.arxiv_id = arxiv_id
        self.title = title
        self.authors = authors
        self.abstract = abstract
        self.published = published
        self.pdf_url = pdf_url
        self.categories = categories

    def to_dict(self) -> Dict:
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "published": self.published.isoformat(),
            "pdf_url": self.pdf_url,
            "categories": self.categories
        }

    def __repr__(self):
        return f"PaperInfo({self.arxiv_id}: {self.title[:50]}...)"


class ArxivCrawler:
    """arXiv论文爬虫"""

    def __init__(self, config: Dict):
        """
        初始化爬虫

        Args:
            config: 配置字典，包含keywords, categories, paths等
        """
        self.keywords = config.get("keywords", [])
        self.categories = config.get("categories", [])
        self.pdf_dir = Path(config.get("paths", {}).get("pdfs", "./data/pdfs"))
        self.max_papers = config.get("paper", {}).get("max_papers_per_day", 10)
        self.skip_if_exists = config.get("paper", {}).get("skip_if_exists", True)

        # 确保PDF目录存在
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

    def search(self, query: Optional[str] = None,
               date_from: Optional[datetime] = None,
               date_to: Optional[datetime] = None,
               max_results: Optional[int] = None) -> List[PaperInfo]:
        """
        搜索arXiv论文

        Args:
            query: 搜索查询，如果不提供则使用配置的关键词
            date_from: 开始日期
            date_to: 结束日期
            max_results: 最大结果数

        Returns:
            论文信息列表
        """
        if max_results is None:
            max_results = self.max_papers

        # 构建搜索查询
        if query is None:
            # 使用关键词构建查询
            query_parts = [f'"{kw}"' for kw in self.keywords]
            query = " OR ".join(query_parts)

            # 添加分类筛选
            if self.categories:
                cat_query = " OR ".join([f"cat:{c}" for c in self.categories])
                query = f"({query}) AND ({cat_query})"

        logger.info(f"搜索查询: {query}")

        # 执行搜索
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )

        papers = []
        for result in search.results():
            # 日期筛选 - 统一使用UTC时区比较
            published_utc = result.published.replace(tzinfo=timezone.utc) if result.published.tzinfo is None else result.published
            if date_from:
                date_from_utc = date_from.replace(tzinfo=timezone.utc) if date_from.tzinfo is None else date_from
                if published_utc < date_from_utc:
                    continue
            if date_to:
                date_to_utc = date_to.replace(tzinfo=timezone.utc) if date_to.tzinfo is None else date_to
                if published_utc > date_to_utc:
                    continue

            paper = PaperInfo(
                arxiv_id=result.entry_id.split("/")[-1],
                title=result.title,
                authors=[a.name for a in result.authors],
                abstract=result.summary,
                published=result.published,
                pdf_url=result.pdf_url,
                categories=result.categories
            )
            papers.append(paper)

        logger.info(f"找到 {len(papers)} 篇论文")
        return papers

    def search_today(self) -> List[PaperInfo]:
        """搜索今天发布的论文"""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        return self.search(date_from=today, date_to=tomorrow)

    def search_recent(self, days: int = 7) -> List[PaperInfo]:
        """搜索最近N天的论文"""
        date_from = datetime.now(timezone.utc) - timedelta(days=days)
        return self.search(date_from=date_from)

    def search_years(self, years: int = 1) -> List[PaperInfo]:
        """搜索最近N年的论文"""
        date_from = datetime.now(timezone.utc) - timedelta(days=years*365)
        return self.search(date_from=date_from)

    def download_pdf(self, paper: PaperInfo) -> Optional[Path]:
        """
        下载论文PDF

        Args:
            paper: 论文信息

        Returns:
            PDF文件路径，失败返回None
        """
        import requests

        # 检查是否已存在
        pdf_path = self.pdf_dir / f"{paper.arxiv_id}.pdf"
        if pdf_path.exists() and self.skip_if_exists:
            logger.info(f"PDF已存在: {pdf_path}")
            return pdf_path

        try:
            logger.info(f"下载PDF: {paper.arxiv_id}")

            # 直接使用requests下载PDF
            pdf_url = f"https://arxiv.org/pdf/{paper.arxiv_id}.pdf"
            response = requests.get(pdf_url, timeout=60)
            response.raise_for_status()

            # 保存PDF
            with open(pdf_path, 'wb') as f:
                f.write(response.content)

            logger.info(f"下载完成: {pdf_path}")
            return pdf_path
        except Exception as e:
            logger.error(f"下载失败 {paper.arxiv_id}: {e}")
            return None

    def download_papers(self, papers: List[PaperInfo]) -> Dict[str, Path]:
        """
        批量下载论文PDF

        Args:
            papers: 论文列表

        Returns:
            {arxiv_id: pdf_path} 字典
        """
        results = {}
        for paper in papers:
            pdf_path = self.download_pdf(paper)
            if pdf_path:
                results[paper.arxiv_id] = pdf_path
        return results


def main():
    """测试入口"""
    import yaml

    # 加载配置
    with open("config/settings.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    crawler = ArxivCrawler(config)

    # 搜索最近7天的论文
    papers = crawler.search_recent(days=7)
    print(f"\n找到 {len(papers)} 篇论文:")
    for p in papers[:5]:
        print(f"  - [{p.arxiv_id}] {p.title}")

    # 下载第一篇论文测试
    if papers:
        pdf_path = crawler.download_pdf(papers[0])
        print(f"\n下载到: {pdf_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
