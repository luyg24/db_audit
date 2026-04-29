"""
配置管理模块
"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_DIR = DATA_DIR / "sample"
CONFIG_DIR = DATA_DIR / "config"
OUTPUT_DIR = PROJECT_ROOT / "output"

# 人员/系统识别阈值
IDENTIFICATION_THRESHOLD = 50  # 评分阈值

# 异常检测阈值
ANOMALY_THRESHOLDS = {
    "large_export_rows": 10000,  # 大量导出行数阈值
    "high_frequency_per_minute": 100,  # 高频查询阈值(每分钟)
    "sensitive_tables": [],  # 敏感表清单(从配置加载)
    "allowed_ips": [],  # IP白名单(从配置加载)
    "work_hours": (9, 18),  # 工作时间范围
}

# SQL注入检测关键词
SQL_INJECTION_PATTERNS = [
    r"(?i)(\bunion\b.*\bselect\b)",  # UNION注入
    r"(?i)(\bor\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+)",  # OR 1=1
    r"(?i)(\band\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+)",  # AND 1=1
    r"(?i)(;\s*\bdrop\b)",  # 堆叠注入DROP
    r"(?i)(;\s*\bdelete\b)",  # 堆叠注入DELETE
    r"(?i)(;\s*\btruncate\b)",  # 堆叠注入TRUNCATE
    r"(?i)(\bexec\b.*\bxp_)",  # 存储过程注入
    r"(?i)(\bload_file\b)",  # 文件读取
    r"(?i)(\binto\s+outfile\b)",  # 文件写入
    r"(?i)(\binto\s+dumpfile\b)",  # 文件写入
    r"(--|\#|\/\*)",  # 注释符号
    r"(?i)(\bbenchmark\b)",  # 时间盲注
    r"(?i)(\bsleep\b\s*\()",  # 时间盲注
    r"(?i)(\bwaitfor\b.*\bdelay\b)",  # SQL Server时间盲注
]

# 系统账号特征模式
SYSTEM_ACCOUNT_PATTERNS = [
    r"_[a-z0-9]{6}_rw$",  # 随机串后缀: xxx_u25r4b_rw
    r"_api_rw$",  # API账号
    r"_service_rw$",  # 服务账号
    r"_sys_rw$",  # 系统账号
    r"_app_rw$",  # 应用账号
    r"_batch_rw$",  # 批处理账号
    r"_job_rw$",  # 任务账号
]
