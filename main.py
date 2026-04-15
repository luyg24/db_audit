#!/usr/bin/env python3
"""
自动化论文搜集系统 - 主入口

用法:
    python main.py --once          # 执行一次
    python main.py --daemon         # 启动定时任务
    python main.py --search "keyword"  # 搜索指定关键词
    python main.py --stats          # 查看统计信息
"""

import argparse
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
import yaml

from src.crawler import ArxivCrawler
from src.converter import PDFConverter
from src.extractor import LLMExtractor
from src.storage import KnowledgeBase
from src.scheduler import DailyScheduler, create_daily_task


def load_config() -> dict:
    """加载配置文件"""
    config_path = Path(__file__).parent / "config" / "settings.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(verbose: bool = False):
    """设置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
        ]
    )


def run_once(config: dict):
    """执行一次完整流程"""
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info(f"开始论文收集: {datetime.now()}")
    logger.info("=" * 60)

    try:
        # 初始化组件
        crawler = ArxivCrawler(config)
        converter = PDFConverter(config)
        extractor = LLMExtractor(config)
        kb = KnowledgeBase(config)

        # 创建并执行任务
        task = create_daily_task(crawler, converter, extractor, kb)
        result = task()

        logger.info("=" * 60)
        logger.info(f"完成: {result}")
        logger.info("=" * 60)

        return result

    except Exception as e:
        logger.error(f"执行失败: {e}")
        raise


def run_daemon(config: dict):
    """启动定时任务守护进程"""
    logger = logging.getLogger(__name__)

    # 初始化组件
    crawler = ArxivCrawler(config)
    converter = PDFConverter(config)
    extractor = LLMExtractor(config)
    kb = KnowledgeBase(config)

    # 创建任务和调度器
    task = create_daily_task(crawler, converter, extractor, kb)
    scheduler = DailyScheduler(config, task)

    logger.info("启动定时任务守护进程...")
    scheduler.start()


def run_search(config: dict, keyword: str, days: int = 7):
    """搜索论文"""
    from datetime import datetime, timedelta

    logger = logging.getLogger(__name__)

    crawler = ArxivCrawler(config)

    date_from = datetime.now() - timedelta(days=days)
    papers = crawler.search(query=keyword, date_from=date_from)

    print(f"\n找到 {len(papers)} 篇论文:\n")

    for paper in papers[:20]:  # 最多显示20篇
        print(f"[{paper.arxiv_id}] {paper.title}")
        print(f"    作者: {', '.join(paper.authors[:3])}...")
        print(f"    发布: {paper.published.strftime('%Y-%m-%d')}")
        print(f"    分类: {', '.join(paper.categories)}")
        print()


def run_stats(config: dict):
    """显示统计信息"""
    kb = KnowledgeBase(config)
    stats = kb.get_statistics()

    print("\n" + "=" * 50)
    print("知识库统计")
    print("=" * 50)
    print(f"总论文数: {stats['total_papers']}")
    print("\n按日期统计:")
    for item in stats['dates'][:10]:
        print(f"  {item['date']}: {item['count']} 篇")
    print("=" * 50)


def run_download(config: dict, arxiv_id: str):
    """下载指定论文"""
    logger = logging.getLogger(__name__)

    crawler = ArxivCrawler(config)
    converter = PDFConverter(config)

    # 搜索指定论文
    papers = crawler.search(query=f"id:{arxiv_id}")

    if not papers:
        print(f"未找到论文: {arxiv_id}")
        return

    paper = papers[0]
    print(f"\n找到论文: {paper.title}")
    print(f"下载中...")

    pdf_path = crawler.download_pdf(paper)
    if pdf_path:
        print(f"下载完成: {pdf_path}")

        # 转换
        success, md_path = converter.convert(pdf_path)
        if success:
            print(f"转换完成: {md_path}")
        else:
            print("转换失败")
    else:
        print("下载失败")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="自动化论文搜集系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python main.py --once              # 执行一次收集
    python main.py --daemon            # 启动定时任务
    python main.py --search "database audit"  # 搜索论文
    python main.py --download 2401.12345     # 下载指定论文
    python main.py --stats             # 查看统计
        """
    )

    parser.add_argument("--once", action="store_true",
                        help="执行一次论文收集")
    parser.add_argument("--daemon", action="store_true",
                        help="启动定时任务守护进程")
    parser.add_argument("--search", type=str, metavar="KEYWORD",
                        help="搜索论文")
    parser.add_argument("--days", type=int, default=7,
                        help="搜索最近N天的论文（默认7天）")
    parser.add_argument("--download", type=str, metavar="ARXIV_ID",
                        help="下载指定arXiv ID的论文")
    parser.add_argument("--stats", action="store_true",
                        help="显示知识库统计信息")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="详细输出")

    args = parser.parse_args()

    # 加载环境变量和配置
    load_dotenv()
    config = load_config()

    # 设置日志
    setup_logging(args.verbose)

    # 执行对应操作
    if args.once:
        run_once(config)
    elif args.daemon:
        run_daemon(config)
    elif args.search:
        run_search(config, args.search, args.days)
    elif args.download:
        run_download(config, args.download)
    elif args.stats:
        run_stats(config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
