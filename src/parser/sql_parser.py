"""
SQL解析器 - 提取SQL的特征信息
支持：
- SQL操作类型识别
- 表名提取
- 字段提取
- 风险特征识别
"""
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SQLFeatures:
    """SQL特征结构"""
    sql_type: str  # 操作类型: SELECT, INSERT, UPDATE, DELETE, etc.
    tables: List[str]  # 涉及的表名
    fields: List[str]  # 涉及的字段
    has_where: bool  # 是否有WHERE条件
    has_limit: bool  # 是否有LIMIT
    has_bind_variable: bool  # 是否使用绑定变量(?)
    has_traceid: bool  # 是否包含traceid
    has_json_comment: bool  # 是否包含JSON注释头
    has_select_all: bool  # 是否SELECT *
    is_batch: bool  # 是否批量操作
    risk_level: str  # 风险等级: LOW, MEDIUM, HIGH, CRITICAL
    risk_features: List[str]  # 风险特征列表


class SQLParser:
    """SQL解析器"""

    # SQL操作类型模式
    SQL_TYPE_PATTERNS = [
        (r'^\s*SELECT\b', 'SELECT'),
        (r'^\s*INSERT\b', 'INSERT'),
        (r'^\s*UPDATE\b', 'UPDATE'),
        (r'^\s*DELETE\b', 'DELETE'),
        (r'^\s*DROP\b', 'DROP'),
        (r'^\s*TRUNCATE\b', 'TRUNCATE'),
        (r'^\s*ALTER\b', 'ALTER'),
        (r'^\s*CREATE\b', 'CREATE'),
        (r'^\s*SHOW\b', 'SHOW'),
        (r'^\s*DESC\b', 'DESC'),
        (r'^\s*DESCRIBE\b', 'DESCRIBE'),
        (r'^\s*USE\b', 'USE'),
        (r'^\s*SET\b', 'SET'),
        (r'^\s*COMMIT\b', 'COMMIT'),
        (r'^\s*ROLLBACK\b', 'ROLLBACK'),
        (r'^\s*START\b', 'START'),
        (r'^\s*BEGIN\b', 'BEGIN'),
        (r'^\s*CONNECT\b', 'CONNECT'),
        (r'^\s*query_read\b', 'QUERY_READ'),
        (r'^\s*command\b', 'COMMAND'),
    ]

    # 表名提取模式
    TABLE_PATTERNS = [
        r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        r'\bINTO\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        r'\bUPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        r'\bTABLE\s+([a-zA-Z_][a-zA-Z0-9_]*)',
    ]

    def __init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        """预编译正则表达式"""
        self.compiled_sql_types = [
            (re.compile(p, re.IGNORECASE), t) for p, t in self.SQL_TYPE_PATTERNS
        ]
        self.compiled_table_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.TABLE_PATTERNS
        ]

    def parse(self, sql: str) -> SQLFeatures:
        """解析SQL语句"""
        if not sql or not isinstance(sql, str):
            return SQLFeatures(
                sql_type='UNKNOWN',
                tables=[],
                fields=[],
                has_where=False,
                has_limit=False,
                has_bind_variable=False,
                has_traceid=False,
                has_json_comment=False,
                has_select_all=False,
                is_batch=False,
                risk_level='LOW',
                risk_features=[]
            )

        sql_upper = sql.upper()
        sql_lower = sql.lower()

        # 识别SQL类型
        sql_type = self._identify_sql_type(sql)

        # 提取表名
        tables = self._extract_tables(sql)

        # 提取字段
        fields = self._extract_fields(sql)

        # 特征检测
        has_where = ' WHERE ' in sql_upper
        has_limit = ' LIMIT ' in sql_upper
        has_bind_variable = '?' in sql
        has_traceid = 'traceid' in sql_lower or 'trace_id' in sql_lower
        has_json_comment = sql.strip().startswith('/*{')
        has_select_all = 'SELECT *' in sql_upper or 'SELECT  *' in sql_upper
        is_batch = sql_type == 'INSERT' and sql.count('VALUES') > 1

        # 风险评估
        risk_level, risk_features = self._assess_risk(
            sql, sql_type, tables, has_select_all, has_where, has_limit
        )

        return SQLFeatures(
            sql_type=sql_type,
            tables=tables,
            fields=fields,
            has_where=has_where,
            has_limit=has_limit,
            has_bind_variable=has_bind_variable,
            has_traceid=has_traceid,
            has_json_comment=has_json_comment,
            has_select_all=has_select_all,
            is_batch=is_batch,
            risk_level=risk_level,
            risk_features=risk_features
        )

    def _identify_sql_type(self, sql: str) -> str:
        """识别SQL操作类型"""
        for pattern, sql_type in self.compiled_sql_types:
            if pattern.match(sql):
                return sql_type
        return 'UNKNOWN'

    def _extract_tables(self, sql: str) -> List[str]:
        """提取表名"""
        tables = set()
        for pattern in self.compiled_table_patterns:
            matches = pattern.findall(sql)
            tables.update(matches)
        # 过滤掉SQL关键字
        keywords = {'FROM', 'WHERE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE',
                    'JOIN', 'INTO', 'TABLE', 'AND', 'OR', 'ON', 'AS', 'BY'}
        return [t for t in tables if t.upper() not in keywords]

    def _extract_fields(self, sql: str) -> List[str]:
        """提取字段名"""
        fields = []
        # SELECT后的字段
        select_match = re.search(r'SELECT\s+(.+?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
        if select_match:
            field_str = select_match.group(1)
            if field_str.strip() != '*':
                # 简单分割，实际项目中可能需要更复杂的解析
                fields = [f.strip().split('.')[-1] for f in field_str.split(',') if f.strip()]
        return fields

    def _assess_risk(
        self, sql: str, sql_type: str, tables: List[str],
        has_select_all: bool, has_where: bool, has_limit: bool
    ) -> Tuple[str, List[str]]:
        """评估风险等级"""
        risk_features = []
        risk_score = 0

        # 高危操作类型
        if sql_type in ('DROP', 'TRUNCATE'):
            risk_score += 50
            risk_features.append(f'高危操作: {sql_type}')

        if sql_type == 'DELETE':
            risk_score += 30
            risk_features.append('删除操作')

        # 无WHERE条件的更新/删除
        if sql_type in ('UPDATE', 'DELETE') and not has_where:
            risk_score += 40
            risk_features.append(f'{sql_type}无WHERE条件')

        # SELECT *
        if has_select_all and sql_type == 'SELECT':
            risk_score += 15
            risk_features.append('全字段查询(SELECT *)')

        # 无LIMIT的大量查询
        if sql_type == 'SELECT' and not has_limit and has_where:
            risk_score += 10
            risk_features.append('查询无LIMIT限制')

        # 敏感表访问 (示例，实际应从配置读取)
        sensitive_keywords = ['user', 'password', 'secret', 'token', 'key', 'account']
        for table in tables:
            if any(kw in table.lower() for kw in sensitive_keywords):
                risk_score += 20
                risk_features.append(f'敏感表访问: {table}')

        # SQL注入风险特征
        injection_patterns = [
            (r"(?i)\bUNION\b.*\bSELECT\b", 'UNION注入'),
            (r"(?i)\bOR\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+", 'OR注入'),
            (r"(?i);\s*\bDROP\b", '堆叠注入DROP'),
            (r"(?i);\s*\bDELETE\b", '堆叠注入DELETE'),
            (r"(?i)\bLOAD_FILE\b", '文件读取'),
            (r"(?i)\bINTO\s+OUTFILE\b", '文件写入'),
            (r"(?i)\bSLEEP\b\s*\(", '时间盲注'),
        ]
        for pattern, desc in injection_patterns:
            if re.search(pattern, sql):
                risk_score += 50
                risk_features.append(f'疑似SQL注入: {desc}')

        # 确定风险等级
        if risk_score >= 50:
            risk_level = 'CRITICAL'
        elif risk_score >= 30:
            risk_level = 'HIGH'
        elif risk_score >= 15:
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'

        return risk_level, risk_features

    def to_dict(self, features: SQLFeatures) -> Dict:
        """转换为字典格式"""
        return {
            'sql_type': features.sql_type,
            'tables': features.tables,
            'fields': features.fields,
            'has_where': features.has_where,
            'has_limit': features.has_limit,
            'has_bind_variable': features.has_bind_variable,
            'has_traceid': features.has_traceid,
            'has_json_comment': features.has_json_comment,
            'has_select_all': features.has_select_all,
            'is_batch': features.is_batch,
            'risk_level': features.risk_level,
            'risk_features': features.risk_features
        }


# PySpark UDF版本
def create_sql_parser_udf():
    """创建PySpark UDF"""
    parser = SQLParser()

    def parse_sql_udf(sql: str) -> dict:
        features = parser.parse(sql)
        return parser.to_dict(features)

    return parse_sql_udf


if __name__ == '__main__':
    # 测试
    parser = SQLParser()

    test_sqls = [
        "SELECT * FROM users WHERE id = 1",
        "INSERT INTO orders (id, name) VALUES (1, 'test')",
        "/*{\"traceid\":\"abc123\"}*/ SELECT * FROM orders WHERE order_id = ?",
        "DELETE FROM logs",
        "UPDATE users SET status = 1",
        "SELECT * FROM users WHERE id = 1 OR 1=1",
    ]

    for sql in test_sqls:
        features = parser.parse(sql)
        print(f"\nSQL: {sql[:50]}...")
        print(f"  类型: {features.sql_type}")
        print(f"  表: {features.tables}")
        print(f"  风险: {features.risk_level} - {features.risk_features}")
