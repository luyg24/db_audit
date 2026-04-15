"""
定时任务调度模块
功能：
- 每日固定时间执行
- 支持手动触发
- 错误重试机制
- 执行日志记录
"""

import time
import logging
import schedule
from datetime import datetime
from typing import Callable, Optional, Dict
from pathlib import Path
import traceback

logger = logging.getLogger(__name__)


class DailyScheduler:
    """每日任务调度器"""

    def __init__(self, config: Dict, task_func: Callable):
        """
        初始化调度器

        Args:
            config: 配置字典
            task_func: 要执行的任务函数
        """
        self.config = config
        self.task_func = task_func
        self.schedule_time = config.get("schedule", {}).get("time", "08:00")
        self.enabled = config.get("schedule", {}).get("enabled", True)
        self.max_retries = 3
        self.retry_delay = 60  # 重试延迟（秒）

        # 设置日志
        self._setup_logging()

    def _setup_logging(self):
        """设置日志"""
        log_dir = Path(self.config.get("paths", {}).get("logs", "./logs"))
        log_dir.mkdir(parents=True, exist_ok=True)

        # 文件处理器
        log_file = log_dir / "scheduler.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)

    def run_once(self):
        """执行一次任务"""
        logger.info(f"开始执行任务: {datetime.now()}")
        start_time = time.time()

        for attempt in range(self.max_retries):
            try:
                result = self.task_func()
                elapsed = time.time() - start_time
                logger.info(f"任务完成，耗时: {elapsed:.2f}秒")
                return result

            except Exception as e:
                logger.error(f"任务执行失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                logger.error(traceback.format_exc())

                if attempt < self.max_retries - 1:
                    logger.info(f"{self.retry_delay}秒后重试...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("任务最终失败")
                    raise

    def start(self):
        """启动定时任务"""
        if not self.enabled:
            logger.info("定时任务已禁用")
            return

        logger.info(f"设置定时任务: 每天 {self.schedule_time}")

        schedule.every().day.at(self.schedule_time).do(self.run_once)

        logger.info("调度器已启动，等待执行...")

        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次

    def stop(self):
        """停止定时任务"""
        schedule.clear()
        logger.info("调度器已停止")


def create_daily_task(crawler, converter, extractor, knowledge_base):
    """
    创建每日任务函数

    Args:
        crawler: ArxivCrawler实例
        converter: PDFConverter实例
        extractor: LLMExtractor实例
        knowledge_base: KnowledgeBase实例

    Returns:
        任务函数
    """
    def task():
        from datetime import datetime

        logger.info("=" * 50)
        logger.info(f"开始每日论文收集: {datetime.now()}")
        logger.info("=" * 50)

        # 1. 搜索最近论文
        logger.info("Step 1: 搜索论文...")
        papers = crawler.search_recent(days=1)
        logger.info(f"找到 {len(papers)} 篇论文")

        if not papers:
            logger.info("没有新论文")
            return {"papers_found": 0, "papers_processed": 0}

        # 2. 下载PDF
        logger.info("Step 2: 下载PDF...")
        downloaded = crawler.download_papers(papers)
        logger.info(f"下载成功 {len(downloaded)} 篇")

        # 3. 转换和提取
        logger.info("Step 3: 转换和提取...")
        processed_count = 0

        for arxiv_id, pdf_path in downloaded.items():
            try:
                # 检查是否已处理
                if knowledge_base.exists(arxiv_id):
                    logger.info(f"已存在，跳过: {arxiv_id}")
                    continue

                logger.info(f"处理: {arxiv_id}")

                # 转换PDF
                success, md_path = converter.convert(pdf_path)
                if not success:
                    logger.warning(f"转换失败: {arxiv_id}")
                    continue

                # 提取信息
                extracted = extractor.extract_from_file(md_path)

                # 保存到知识库
                paper_info = next((p.to_dict() for p in papers if p.arxiv_id == arxiv_id), None)
                if paper_info:
                    knowledge_base.save_paper(paper_info, extracted, arxiv_id)
                    processed_count += 1

            except Exception as e:
                logger.error(f"处理失败 {arxiv_id}: {e}")
                continue

        # 4. 生成日报
        logger.info("Step 4: 生成日报...")
        knowledge_base.generate_daily_report()

        logger.info("=" * 50)
        logger.info(f"完成: 找到 {len(papers)} 篇，处理 {processed_count} 篇")
        logger.info("=" * 50)

        return {
            "papers_found": len(papers),
            "papers_processed": processed_count
        }

    return task


def main():
    """测试入口"""
    import yaml
    from dotenv import load_dotenv

    # 加载环境变量
    load_dotenv()

    # 加载配置
    with open("config/settings.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 导入模块
    import sys
    sys.path.insert(0, ".")
    from src.crawler import ArxivCrawler
    from src.converter import PDFConverter
    from src.extractor import LLMExtractor
    from src.storage import KnowledgeBase

    # 初始化组件
    crawler = ArxivCrawler(config)
    converter = PDFConverter(config)
    extractor = LLMExtractor(config)
    kb = KnowledgeBase(config)

    # 创建任务
    task = create_daily_task(crawler, converter, extractor, kb)

    # 创建调度器
    scheduler = DailyScheduler(config, task)

    # 执行一次测试
    print("执行一次测试...")
    result = scheduler.run_once()
    print(f"结果: {result}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    main()
