"""
人员/系统查询识别模型
基于多维度特征识别查询来源：
1. 账号归属表（强信号）
2. SQL语法特征（中等信号）
3. 行为模式（辅助信号）
"""
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json


class QuerySource(Enum):
    """查询来源类型"""
    SYSTEM = "system"  # 系统查询
    HUMAN = "human"  # 人员查询
    UNKNOWN = "unknown"  # 无法确定


@dataclass
class IdentificationResult:
    """识别结果"""
    source: QuerySource  # 来源类型
    score: int  # 系统查询评分(0-100)
    confidence: float  # 置信度(0-1)
    features: Dict[str, int]  # 各特征得分
    account_owner: Optional[str]  # 账号归属(如有)
    matched_rules: List[str]  # 匹配的规则


class AccountMapping:
    """账号归属映射管理"""

    def __init__(self):
        self.account_map: Dict[str, Dict] = {}  # 账号 -> 归属信息
        self.ip_map: Dict[str, str] = {}  # IP -> 账号

    def load_from_dict(self, data: List[Dict]):
        """从字典列表加载账号映射"""
        for item in data:
            account = item.get('account', '')
            if account:
                self.account_map[account] = {
                    'owner': item.get('owner', ''),  # 归属人/系统
                    'owner_type': item.get('owner_type', 'unknown'),  # human/system
                    'department': item.get('department', ''),
                    'contact': item.get('contact', ''),
                    'description': item.get('description', ''),
                }

    def load_from_excel(self, file_path: str):
        """从Excel加载账号映射"""
        import pandas as pd
        df = pd.read_excel(file_path)
        data = df.to_dict('records')
        self.load_from_dict(data)

    def get_account_info(self, account: str) -> Optional[Dict]:
        """获取账号归属信息"""
        return self.account_map.get(account)

    def is_system_account(self, account: str) -> Optional[bool]:
        """判断是否为系统账号(基于映射表)"""
        info = self.account_map.get(account)
        if info:
            return info.get('owner_type') == 'system'
        return None


class QueryIdentifier:
    """人员/系统查询识别器"""

    # 系统账号命名模式
    SYSTEM_ACCOUNT_PATTERNS = [
        (r'_[a-z0-9]{6}_rw$', 25, '随机串后缀(如_u25r4b_rw)'),
        (r'_api_rw$', 20, 'API账号'),
        (r'_service_rw$', 20, '服务账号'),
        (r'_sys_rw$', 20, '系统账号'),
        (r'_app_rw$', 15, '应用账号'),
        (r'_batch_rw$', 20, '批处理账号'),
        (r'_job_rw$', 20, '任务账号'),
        (r'_task_rw$', 20, '任务账号'),
        (r'_cron_rw$', 20, '定时任务账号'),
        (r'_schedule_rw$', 20, '调度账号'),
    ]

    # 人员账号命名模式(负分,降低系统判定)
    HUMAN_ACCOUNT_PATTERNS = [
        (r'^[a-z]+\.[a-z]+_rw$', -15, '姓名格式(如zhang.san_rw)'),
        (r'^[a-z]+_[a-z]+_rw$', -15, '姓名格式(如zhang_san_rw)'),
        (r'^emp\d+_rw$', -20, '工号格式'),
        (r'^user\d+_rw$', -15, '用户编号格式'),
        (r'^admin_rw$', -10, '管理员账号'),
    ]

    # SQL特征权重
    SQL_FEATURE_WEIGHTS = {
        'has_traceid': 30,
        'has_json_comment': 20,
        'has_bind_variable': 10,
        'is_batch': 10,
        'has_limit': 5,
        'has_select_all': -10,  # 人员更可能用SELECT *
    }

    # 非工作时间(深夜)
    NIGHT_HOURS = [0, 1, 2, 3, 4, 5, 22, 23]

    def __init__(self, account_mapping: Optional[AccountMapping] = None):
        self.account_mapping = account_mapping or AccountMapping()
        self._compile_patterns()

    def _compile_patterns(self):
        """预编译正则表达式"""
        self.compiled_system_patterns = [
            (re.compile(p), s, d) for p, s, d in self.SYSTEM_ACCOUNT_PATTERNS
        ]
        self.compiled_human_patterns = [
            (re.compile(p), s, d) for p, s, d in self.HUMAN_ACCOUNT_PATTERNS
        ]

    def identify(
        self,
        sql: str,
        account: str,
        client_ip: str = '',
        timestamp: Optional[str] = None,
        sql_features: Optional[Dict] = None
    ) -> IdentificationResult:
        """
        识别查询来源

        Args:
            sql: SQL语句
            account: 数据库账号
            client_ip: 来源IP
            timestamp: 时间戳
            sql_features: SQL解析特征(可选,若已解析)

        Returns:
            IdentificationResult: 识别结果
        """
        features = {}
        score = 0
        matched_rules = []
        account_owner = None

        # 1. 账号归属表检查(强信号)
        account_info = self.account_mapping.get_account_info(account)
        if account_info:
            account_owner = account_info.get('owner', '')
            owner_type = account_info.get('owner_type', '')
            if owner_type == 'system':
                features['account_mapping'] = 50
                score += 50
                matched_rules.append(f'账号归属表: 系统账号({account_owner})')
            elif owner_type == 'human':
                features['account_mapping'] = -50
                score -= 50
                matched_rules.append(f'账号归属表: 人员账号({account_owner})')

        # 2. 账号命名模式检查
        account_score, account_rules = self._check_account_pattern(account)
        if account_score != 0:
            features['account_pattern'] = account_score
            score += account_score
            matched_rules.extend(account_rules)

        # 3. SQL语法特征检查
        sql_score, sql_rules = self._check_sql_features(sql, sql_features)
        if sql_score != 0:
            features['sql_features'] = sql_score
            score += sql_score
            matched_rules.extend(sql_rules)

        # 4. 行为模式检查
        behavior_score, behavior_rules = self._check_behavior(timestamp)
        if behavior_score != 0:
            features['behavior'] = behavior_score
            score += behavior_score
            matched_rules.extend(behavior_rules)

        # 确定来源类型
        source, confidence = self._determine_source(score, features)

        return IdentificationResult(
            source=source,
            score=score,
            confidence=confidence,
            features=features,
            account_owner=account_owner,
            matched_rules=matched_rules
        )

    def _check_account_pattern(self, account: str) -> Tuple[int, List[str]]:
        """检查账号命名模式"""
        score = 0
        rules = []

        # 系统账号模式
        for pattern, pattern_score, desc in self.compiled_system_patterns:
            if pattern.search(account):
                score += pattern_score
                rules.append(f'账号模式: {desc}')

        # 人员账号模式(负分)
        for pattern, pattern_score, desc in self.compiled_human_patterns:
            if pattern.search(account):
                score += pattern_score  # pattern_score已经是负数
                rules.append(f'账号模式: {desc}')

        return score, rules

    def _check_sql_features(
        self, sql: str, sql_features: Optional[Dict]
    ) -> Tuple[int, List[str]]:
        """检查SQL特征"""
        score = 0
        rules = []

        if sql_features:
            # 使用已解析的特征
            for feature, weight in self.SQL_FEATURE_WEIGHTS.items():
                if sql_features.get(feature):
                    score += weight
                    if weight > 0:
                        rules.append(f'SQL特征: {feature}')
        else:
            # 实时检查
            sql_lower = sql.lower()

            if 'traceid' in sql_lower or 'trace_id' in sql_lower:
                score += 30
                rules.append('SQL特征: 包含traceid')

            if sql.strip().startswith('/*{'):
                score += 20
                rules.append('SQL特征: JSON注释头')

            if '?' in sql:
                score += 10
                rules.append('SQL特征: 绑定变量')

            if ' limit ' in sql_lower:
                score += 5
                rules.append('SQL特征: 有LIMIT')

            if 'select *' in sql_lower:
                score -= 10
                rules.append('SQL特征: SELECT *')

        return score, rules

    def _check_behavior(self, timestamp: Optional[str]) -> Tuple[int, List[str]]:
        """检查行为模式"""
        score = 0
        rules = []

        if timestamp:
            try:
                from datetime import datetime
                if isinstance(timestamp, str):
                    dt = datetime.strptime(timestamp[:19], '%Y-%m-%d %H:%M:%S')
                else:
                    dt = timestamp

                hour = dt.hour
                if hour in self.NIGHT_HOURS:
                    score += 5
                    rules.append(f'行为特征: 非工作时间({hour}:00)')
            except Exception:
                pass

        return score, rules

    def _determine_source(self, score: int, features: Dict) -> Tuple[QuerySource, float]:
        """根据评分确定来源类型"""
        if score >= 50:
            return QuerySource.SYSTEM, min(0.95, 0.5 + score / 100)
        elif score <= -30:
            return QuerySource.HUMAN, min(0.95, 0.5 + abs(score) / 100)
        elif score >= 20:
            return QuerySource.SYSTEM, 0.6 + score / 100
        elif score <= -10:
            return QuerySource.HUMAN, 0.6 + abs(score) / 100
        else:
            return QuerySource.UNKNOWN, 0.5

    def is_system_query(
        self, sql: str, account: str,
        client_ip: str = '', timestamp: Optional[str] = None
    ) -> Tuple[bool, float]:
        """
        简化接口: 判断是否为系统查询

        Returns:
            (is_system, confidence): 是否为系统查询, 置信度
        """
        result = self.identify(sql, account, client_ip, timestamp)
        return result.source == QuerySource.SYSTEM, result.confidence


def create_identifier_udf():
    """创建PySpark UDF"""
    identifier = QueryIdentifier()

    def identify_udf(sql: str, account: str) -> str:
        is_system, confidence = identifier.is_system_query(sql, account)
        if is_system:
            return 'system'
        else:
            return 'human'

    return identify_udf


if __name__ == '__main__':
    # 测试
    identifier = QueryIdentifier()

    test_cases = [
        ("SELECT * FROM users WHERE id = 1", "zhang_san_rw"),
        ("/*{\"traceid\":\"abc\"}*/ SELECT * FROM orders WHERE id = ?", "order_api_u25r4b_rw"),
        ("INSERT INTO logs VALUES (1, 'test')", "batch_job_rw"),
        ("SELECT name, email FROM employees", "hr_service_rw"),
        ("UPDATE config SET value = 1", "admin_rw"),
    ]

    for sql, account in test_cases:
        result = identifier.identify(sql, account)
        print(f"\n账号: {account}")
        print(f"SQL: {sql[:50]}...")
        print(f"判定: {result.source.value} (置信度: {result.confidence:.2f})")
        print(f"评分: {result.score}")
        print(f"规则: {result.matched_rules}")
