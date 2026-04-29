"""
异常检测引擎
覆盖场景:
1. SQL注入检测
2. 敏感表访问
3. 异常导出
4. 异常时间访问
5. 异常IP访问
6. 高频查询
"""
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class AnomalyType(Enum):
    """异常类型"""
    SQL_INJECTION = "sql_injection"  # SQL注入
    SENSITIVE_TABLE = "sensitive_table"  # 敏感表访问
    LARGE_EXPORT = "large_export"  # 大量导出
    ABNORMAL_TIME = "abnormal_time"  # 异常时间访问
    ABNORMAL_IP = "abnormal_ip"  # 异常IP访问
    HIGH_FREQUENCY = "high_frequency"  # 高频查询
    NO_WHERE_DELETE = "no_where_delete"  # 无WHERE删除
    NO_WHERE_UPDATE = "no_where_update"  # 无WHERE更新
    FULL_TABLE_SCAN = "full_table_scan"  # 全表扫描
    PRIVILEGE_ESCALATION = "privilege_escalation"  # 权限提升尝试


class Severity(Enum):
    """严重程度"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class AnomalyEvent:
    """异常事件"""
    anomaly_type: AnomalyType
    severity: Severity
    description: str
    details: Dict
    sql: str
    account: str
    client_ip: str
    timestamp: str
    risk_score: int  # 0-100
    suggestions: List[str] = field(default_factory=list)


class AnomalyDetector:
    """异常检测器"""

    # SQL注入检测模式
    SQL_INJECTION_PATTERNS = [
        (r"(?i)(\bunion\b.*\bselect\b)", Severity.CRITICAL, 'UNION注入'),
        # OR注入: OR '1'='1' 或 OR 1=1 (需要更精确的模式)
        (r"(?i)\bor\b\s+['\"]?1['\"]?\s*=\s*['\"]?1['\"]?", Severity.HIGH, 'OR注入'),
        (r"(?i)\bor\b\s+['\"][^'\"]+['\"]\s*=\s*['\"][^'\"]+['\"]", Severity.HIGH, 'OR注入'),
        # AND注入: 仅匹配恒真条件
        (r"(?i)\band\b\s+['\"]?1['\"]?\s*=\s*['\"]?1['\"]?", Severity.HIGH, 'AND注入'),
        (r"(?i)(;\s*\bdrop\b)", Severity.CRITICAL, '堆叠注入DROP'),
        (r"(?i)(;\s*\bdelete\b)", Severity.CRITICAL, '堆叠注入DELETE'),
        (r"(?i)(;\s*\btruncate\b)", Severity.CRITICAL, '堆叠注入TRUNCATE'),
        (r"(?i)(;\s*\bupdate\b)", Severity.HIGH, '堆叠注入UPDATE'),
        (r"(?i)(\bexec\b.*\bxp_)", Severity.CRITICAL, '存储过程注入'),
        (r"(?i)(\bload_file\b)", Severity.HIGH, '文件读取尝试'),
        (r"(?i)(\binto\s+outfile\b)", Severity.CRITICAL, '文件写入尝试'),
        (r"(?i)(\binto\s+dumpfile\b)", Severity.CRITICAL, '文件写入尝试'),
        (r"(?i)(\bbenchmark\b\s*\()", Severity.MEDIUM, '时间盲注'),
        (r"(?i)(\bsleep\b\s*\()", Severity.MEDIUM, '时间盲注'),
        (r"(?i)(\bwaitfor\b.*\bdelay\b)", Severity.MEDIUM, '时间盲注'),
        # 注释符号检测 - 仅在特殊上下文中告警
        (r"(?i)'\s*--", Severity.MEDIUM, '注释截断'),
        (r"(?i)'\s*\#", Severity.MEDIUM, '注释截断'),
    ]

    # 敏感表关键词
    SENSITIVE_TABLE_KEYWORDS = [
        'user', 'password', 'passwd', 'pwd', 'secret', 'token',
        'key', 'credential', 'auth', 'permission', 'role',
        'account', 'finance', 'payment', 'order', 'customer',
        'employee', 'salary', 'personal', 'private', 'config'
    ]

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化检测器

        Args:
            config: 配置字典,包含:
                - sensitive_tables: 敏感表清单
                - allowed_ips: IP白名单
                - work_hours: 工作时间范围
                - large_export_threshold: 大量导出行数阈值
                - high_frequency_threshold: 高频查询阈值
        """
        self.config = config or {}
        self._compile_patterns()

    def _compile_patterns(self):
        """预编译正则表达式"""
        self.compiled_injection_patterns = [
            (re.compile(p), s, d) for p, s, d in self.SQL_INJECTION_PATTERNS
        ]

    def detect(
        self,
        sql: str,
        account: str,
        client_ip: str,
        timestamp: str,
        sql_features: Optional[Dict] = None,
        result_lines: int = 0,
        context: Optional[Dict] = None
    ) -> List[AnomalyEvent]:
        """
        检测异常

        Args:
            sql: SQL语句
            account: 数据库账号
            client_ip: 来源IP
            timestamp: 时间戳
            sql_features: SQL解析特征
            result_lines: 返回行数
            context: 上下文信息(如查询频率统计)

        Returns:
            List[AnomalyEvent]: 检测到的异常事件列表
        """
        anomalies = []

        # 1. SQL注入检测
        injection_anomalies = self._detect_sql_injection(sql, account, client_ip, timestamp)
        anomalies.extend(injection_anomalies)

        # 2. 敏感表访问
        table_anomalies = self._detect_sensitive_table_access(
            sql, account, client_ip, timestamp, sql_features
        )
        anomalies.extend(table_anomalies)

        # 3. 大量导出
        export_anomalies = self._detect_large_export(
            sql, account, client_ip, timestamp, result_lines, sql_features
        )
        anomalies.extend(export_anomalies)

        # 4. 异常时间访问
        time_anomalies = self._detect_abnormal_time(sql, account, client_ip, timestamp)
        anomalies.extend(time_anomalies)

        # 5. 异常IP访问
        ip_anomalies = self._detect_abnormal_ip(sql, account, client_ip, timestamp)
        anomalies.extend(ip_anomalies)

        # 6. 无WHERE的危险操作
        dangerous_anomalies = self._detect_dangerous_operations(
            sql, account, client_ip, timestamp, sql_features
        )
        anomalies.extend(dangerous_anomalies)

        # 7. 高频查询(需要上下文)
        if context:
            freq_anomalies = self._detect_high_frequency(
                sql, account, client_ip, timestamp, context
            )
            anomalies.extend(freq_anomalies)

        return anomalies

    def _detect_sql_injection(
        self, sql: str, account: str, client_ip: str, timestamp: str
    ) -> List[AnomalyEvent]:
        """检测SQL注入"""
        anomalies = []

        for pattern, severity, desc in self.compiled_injection_patterns:
            if pattern.search(sql):
                anomalies.append(AnomalyEvent(
                    anomaly_type=AnomalyType.SQL_INJECTION,
                    severity=severity,
                    description=f'疑似SQL注入: {desc}',
                    details={'pattern': desc, 'matched': pattern.pattern},
                    sql=sql,
                    account=account,
                    client_ip=client_ip,
                    timestamp=timestamp,
                    risk_score=90 if severity == Severity.CRITICAL else 70,
                    suggestions=[
                        '立即检查该查询来源',
                        '确认是否为授权的安全测试',
                        '考虑对该账号进行限制'
                    ]
                ))

        return anomalies

    def _detect_sensitive_table_access(
        self, sql: str, account: str, client_ip: str,
        timestamp: str, sql_features: Optional[Dict]
    ) -> List[AnomalyEvent]:
        """检测敏感表访问"""
        anomalies = []

        tables = sql_features.get('tables', []) if sql_features else []

        # 配置的敏感表
        sensitive_tables = set(self.config.get('sensitive_tables', []))

        # 检查配置的敏感表
        for table in tables:
            if table.lower() in [t.lower() for t in sensitive_tables]:
                anomalies.append(AnomalyEvent(
                    anomaly_type=AnomalyType.SENSITIVE_TABLE,
                    severity=Severity.HIGH,
                    description=f'敏感表访问: {table}',
                    details={'table': table},
                    sql=sql,
                    account=account,
                    client_ip=client_ip,
                    timestamp=timestamp,
                    risk_score=60,
                    suggestions=[
                        '确认该账号是否有权限访问此表',
                        '检查访问频率是否异常'
                    ]
                ))

        # 检查关键词敏感表
        for table in tables:
            table_lower = table.lower()
            for keyword in self.SENSITIVE_TABLE_KEYWORDS:
                if keyword in table_lower and table_lower not in [t.lower() for t in sensitive_tables]:
                    anomalies.append(AnomalyEvent(
                        anomaly_type=AnomalyType.SENSITIVE_TABLE,
                        severity=Severity.MEDIUM,
                        description=f'疑似敏感表访问: {table}(包含关键词: {keyword})',
                        details={'table': table, 'keyword': keyword},
                        sql=sql,
                        account=account,
                        client_ip=client_ip,
                        timestamp=timestamp,
                        risk_score=40,
                        suggestions=[
                            f'建议将表 {table} 加入敏感表监控清单',
                            '确认访问权限'
                        ]
                    ))
                    break

        return anomalies

    def _detect_large_export(
        self, sql: str, account: str, client_ip: str,
        timestamp: str, result_lines: int, sql_features: Optional[Dict]
    ) -> List[AnomalyEvent]:
        """检测大量导出"""
        anomalies = []

        threshold = self.config.get('large_export_threshold', 10000)

        if result_lines > threshold:
            anomalies.append(AnomalyEvent(
                anomaly_type=AnomalyType.LARGE_EXPORT,
                severity=Severity.HIGH,
                description=f'大量数据导出: {result_lines}行',
                details={'result_lines': result_lines, 'threshold': threshold},
                sql=sql,
                account=account,
                client_ip=client_ip,
                timestamp=timestamp,
                risk_score=min(80, 30 + result_lines // 1000),
                suggestions=[
                    '确认导出操作是否经授权',
                    '检查导出数据的敏感程度',
                    '考虑对导出操作增加审批流程'
                ]
            ))

        # SELECT * 无LIMIT
        if sql_features:
            if sql_features.get('has_select_all') and not sql_features.get('has_limit'):
                if sql_features.get('sql_type') == 'SELECT':
                    anomalies.append(AnomalyEvent(
                        anomaly_type=AnomalyType.FULL_TABLE_SCAN,
                        severity=Severity.MEDIUM,
                        description='全表扫描风险: SELECT * 无LIMIT',
                        details={'sql_type': 'SELECT'},
                        sql=sql,
                        account=account,
                        client_ip=client_ip,
                        timestamp=timestamp,
                        risk_score=30,
                        suggestions=[
                            '建议添加LIMIT限制',
                            '确认是否需要全部字段'
                        ]
                    ))

        return anomalies

    def _detect_abnormal_time(
        self, sql: str, account: str, client_ip: str, timestamp: str
    ) -> List[AnomalyEvent]:
        """检测异常时间访问"""
        anomalies = []

        work_hours = self.config.get('work_hours', (9, 18))

        try:
            if isinstance(timestamp, str):
                dt = datetime.strptime(timestamp[:19], '%Y-%m-%d %H:%M:%S')
            else:
                dt = timestamp

            hour = dt.hour

            # 非工作时间(深夜)
            if hour < work_hours[0] or hour >= work_hours[1]:
                # 只对敏感操作告警
                sql_upper = sql.upper().strip()
                is_sensitive = (
                    sql_upper.startswith('DELETE') or
                    sql_upper.startswith('DROP') or
                    sql_upper.startswith('TRUNCATE') or
                    sql_upper.startswith('UPDATE')
                )

                if is_sensitive:
                    anomalies.append(AnomalyEvent(
                        anomaly_type=AnomalyType.ABNORMAL_TIME,
                        severity=Severity.MEDIUM,
                        description=f'非工作时间敏感操作({hour}:00)',
                        details={'hour': hour, 'work_hours': work_hours},
                        sql=sql,
                        account=account,
                        client_ip=client_ip,
                        timestamp=timestamp,
                        risk_score=40,
                        suggestions=[
                            '确认是否为计划内的维护操作',
                            '联系账号负责人确认'
                        ]
                    ))
        except Exception:
            pass

        return anomalies

    def _detect_abnormal_ip(
        self, sql: str, account: str, client_ip: str, timestamp: str
    ) -> List[AnomalyEvent]:
        """检测异常IP访问"""
        anomalies = []

        allowed_ips = set(self.config.get('allowed_ips', []))

        if allowed_ips and client_ip not in allowed_ips:
            # 只对敏感操作告警
            sql_upper = sql.upper().strip()
            is_sensitive = (
                'DELETE' in sql_upper or
                'DROP' in sql_upper or
                'TRUNCATE' in sql_upper or
                'UPDATE' in sql_upper or
                'INSERT' in sql_upper
            )

            if is_sensitive:
                anomalies.append(AnomalyEvent(
                    anomaly_type=AnomalyType.ABNORMAL_IP,
                    severity=Severity.HIGH,
                    description=f'非白名单IP访问: {client_ip}',
                    details={'client_ip': client_ip},
                    sql=sql,
                    account=account,
                    client_ip=client_ip,
                    timestamp=timestamp,
                    risk_score=50,
                    suggestions=[
                        '确认该IP是否合法',
                        '考虑将该IP加入白名单或封禁',
                        '检查账号是否泄露'
                    ]
                ))

        return anomalies

    def _detect_dangerous_operations(
        self, sql: str, account: str, client_ip: str,
        timestamp: str, sql_features: Optional[Dict]
    ) -> List[AnomalyEvent]:
        """检测危险操作(无WHERE的DELETE/UPDATE)"""
        anomalies = []

        if not sql_features:
            return anomalies

        sql_type = sql_features.get('sql_type', '')
        has_where = sql_features.get('has_where', False)

        if sql_type == 'DELETE' and not has_where:
            anomalies.append(AnomalyEvent(
                anomaly_type=AnomalyType.NO_WHERE_DELETE,
                severity=Severity.CRITICAL,
                description='DELETE操作无WHERE条件',
                details={'sql_type': sql_type},
                sql=sql,
                account=account,
                client_ip=client_ip,
                timestamp=timestamp,
                risk_score=95,
                suggestions=[
                    '立即停止该操作',
                    '确认是否为误操作',
                    '考虑对DELETE操作增加审批'
                ]
            ))

        if sql_type == 'UPDATE' and not has_where:
            anomalies.append(AnomalyEvent(
                anomaly_type=AnomalyType.NO_WHERE_UPDATE,
                severity=Severity.CRITICAL,
                description='UPDATE操作无WHERE条件',
                details={'sql_type': sql_type},
                sql=sql,
                account=account,
                client_ip=client_ip,
                timestamp=timestamp,
                risk_score=90,
                suggestions=[
                    '立即停止该操作',
                    '确认是否为误操作',
                    '考虑对UPDATE操作增加审批'
                ]
            ))

        return anomalies

    def _detect_high_frequency(
        self, sql: str, account: str, client_ip: str,
        timestamp: str, context: Dict
    ) -> List[AnomalyEvent]:
        """检测高频查询"""
        anomalies = []

        threshold = self.config.get('high_frequency_threshold', 100)
        frequency = context.get('frequency_per_minute', 0)

        if frequency > threshold:
            anomalies.append(AnomalyEvent(
                anomaly_type=AnomalyType.HIGH_FREQUENCY,
                severity=Severity.MEDIUM,
                description=f'高频查询: {frequency}次/分钟',
                details={'frequency': frequency, 'threshold': threshold},
                sql=sql,
                account=account,
                client_ip=client_ip,
                timestamp=timestamp,
                risk_score=40,
                suggestions=[
                    '检查是否存在循环调用',
                    '确认是否为正常业务高峰'
                ]
            ))

        return anomalies


if __name__ == '__main__':
    # 测试
    config = {
        'sensitive_tables': ['users', 'orders', 'payments'],
        'allowed_ips': ['10.0.0.1', '10.0.0.2'],
        'work_hours': (9, 18),
        'large_export_threshold': 10000,
    }

    detector = AnomalyDetector(config)

    # 测试SQL注入
    test_sqls = [
        ("SELECT * FROM users WHERE id = 1 OR 1=1", "test_rw", "10.0.0.5"),
        ("DELETE FROM logs", "test_rw", "10.0.0.5"),
        ("SELECT * FROM users", "test_rw", "10.0.0.5"),
    ]

    for sql, account, ip in test_sqls:
        anomalies = detector.detect(
            sql=sql,
            account=account,
            client_ip=ip,
            timestamp='2026-04-21 03:00:00',
            sql_features={'sql_type': 'DELETE' if 'DELETE' in sql else 'SELECT', 'has_where': 'WHERE' in sql, 'tables': ['users' if 'users' in sql else 'logs']},
            result_lines=0
        )
        if anomalies:
            print(f"\nSQL: {sql}")
            for a in anomalies:
                print(f"  [{a.severity.value}] {a.anomaly_type.value}: {a.description}")
