# MySQL数据库访问行为异常审计系统

## 项目概述

本系统用于审计MySQL数据库访问行为，检测异常操作，覆盖：
- 黑客入侵行为（SQL注入等）
- 内部人员异常操作
- 异常导出
- 异常查询

核心功能：**区分人员查询和系统查询**

## 项目结构

```
db_audit/
├── config/                 # 配置文件
│   └── config.py          # 系统配置
├── src/
│   ├── parser/            # SQL解析模块
│   │   └── sql_parser.py  # SQL特征提取
│   ├── models/            # 识别模型
│   │   └── identifier.py  # 人员/系统识别
│   ├── detector/          # 异常检测
│   │   └── anomaly_detector.py
│   └── utils/             # 工具函数
├── scripts/               # 脚本
│   └── audit_sample.py    # 审计示例
├── data/
│   ├── sample/            # 样本数据
│   └── config/            # 配置数据
├── docs/                  # 文档
│   └── MySQL数据库访问行为异常审计方案.md
└── output/                # 输出结果
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行示例

```bash
python scripts/audit_sample.py
```

### 3. 核心模块使用

```python
from src.parser.sql_parser import SQLParser
from src.models.identifier import QueryIdentifier
from src.detector.anomaly_detector import AnomalyDetector

# 初始化
parser = SQLParser()
identifier = QueryIdentifier()
detector = AnomalyDetector({
    'sensitive_tables': ['users', 'orders'],
    'work_hours': (9, 18),
})

# SQL解析
features = parser.parse("SELECT * FROM users WHERE id = 1")
print(features.sql_type)  # SELECT
print(features.tables)    # ['users']

# 人员/系统识别
result = identifier.identify(sql, account="app_api_rw")
print(result.source.value)  # system/human/unknown

# 异常检测
anomalies = detector.detect(sql, account, ip, timestamp, parser.to_dict(features))
```

## 核心算法

### 人员 vs 系统识别

采用三层识别模型：

| 层级 | 数据源 | 权重 |
|------|--------|------|
| 账号归属表 | 配置表 | 最高 |
| SQL特征 | traceid/JSON注释 | 高 |
| 行为模式 | 时间/频率 | 辅助 |

### 异常检测场景

| 场景 | 检测方法 |
|------|----------|
| SQL注入 | 语法模式匹配 |
| 敏感表访问 | 配置表+关键词 |
| 大量导出 | 结果行数阈值 |
| 无WHERE危险操作 | SQL解析 |
| 异常时间访问 | 时间窗口 |

## 配置说明

编辑 `config/config.py` 调整检测参数：

```python
ANOMALY_THRESHOLDS = {
    "large_export_rows": 10000,      # 大量导出行数阈值
    "high_frequency_per_minute": 100, # 高频查询阈值
    "sensitive_tables": [],          # 敏感表清单
    "work_hours": (9, 18),           # 工作时间
}
```

## 扩展开发

### 添加账号归属表

```python
from src.models.identifier import AccountMapping

mapping = AccountMapping()
mapping.load_from_dict([
    {"account": "app_api_rw", "owner": "订单系统", "owner_type": "system"},
    {"account": "zhang_san_rw", "owner": "张三", "owner_type": "human"},
])
```

### 添加自定义检测规则

在 `src/detector/anomaly_detector.py` 中添加新的检测方法。

## 文档

详细方案见：`docs/MySQL数据库访问行为异常审计方案.md`
