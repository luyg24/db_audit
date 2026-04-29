"""
数据库审计示例脚本
演示如何使用审计模块分析dbproxy日志
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from src.parser.sql_parser import SQLParser
from src.models.identifier import QueryIdentifier, QuerySource
from src.detector.anomaly_detector import AnomalyDetector, AnomalyType


def analyze_log_file(log_path: str, config: dict = None):
    """
    分析dbproxy日志文件

    Args:
        log_path: 日志文件路径(Excel格式)
        config: 检测配置
    """
    # 1. 加载数据
    print(f"加载日志文件: {log_path}")
    df = pd.read_excel(log_path)
    print(f"总记录数: {len(df)}")

    # 2. 初始化组件
    parser = SQLParser()
    identifier = QueryIdentifier()
    detector = AnomalyDetector(config or {})

    # 3. 分析结果存储
    results = []
    all_anomalies = []

    # 4. 逐条分析
    print("\n开始分析...")
    for idx, row in df.iterrows():
        sql = str(row.get('sql', ''))
        account = str(row.get('client_account', ''))
        client_ip = str(row.get('client_ip', ''))
        timestamp = str(row.get('time_stamp', ''))
        result_lines = int(row.get('result_lines', 0))

        # SQL解析
        features = parser.parse(sql)
        features_dict = parser.to_dict(features)

        # 人员/系统识别
        id_result = identifier.identify(
            sql=sql,
            account=account,
            client_ip=client_ip,
            timestamp=timestamp,
            sql_features=features_dict
        )

        # 异常检测
        anomalies = detector.detect(
            sql=sql,
            account=account,
            client_ip=client_ip,
            timestamp=timestamp,
            sql_features=features_dict,
            result_lines=result_lines
        )

        results.append({
            'sql_type': features.sql_type,
            'tables': features.tables,
            'source': id_result.source.value,
            'confidence': id_result.confidence,
            'risk_level': features.risk_level,
            'anomaly_count': len(anomalies)
        })

        if anomalies:
            for a in anomalies:
                all_anomalies.append({
                    'timestamp': timestamp,
                    'account': account,
                    'client_ip': client_ip,
                    'anomaly_type': a.anomaly_type.value,
                    'severity': a.severity.value,
                    'description': a.description,
                    'risk_score': a.risk_score,
                    'sql': sql[:100] + '...' if len(sql) > 100 else sql
                })

    # 5. 统计结果
    print("\n" + "=" * 60)
    print("分析结果统计")
    print("=" * 60)

    # 来源分布
    source_counts = pd.DataFrame(results)['source'].value_counts()
    print("\n查询来源分布:")
    for source, count in source_counts.items():
        print(f"  {source}: {count} ({count/len(results)*100:.1f}%)")

    # SQL类型分布
    sql_type_counts = pd.DataFrame(results)['sql_type'].value_counts()
    print("\nSQL类型分布:")
    for sql_type, count in sql_type_counts.head(10).items():
        print(f"  {sql_type}: {count}")

    # 风险等级分布
    risk_counts = pd.DataFrame(results)['risk_level'].value_counts()
    print("\n风险等级分布:")
    for risk, count in risk_counts.items():
        print(f"  {risk}: {count}")

    # 异常统计
    print(f"\n检测到异常: {len(all_anomalies)} 条")

    if all_anomalies:
        anomaly_df = pd.DataFrame(all_anomalies)
        print("\n异常类型分布:")
        print(anomaly_df['anomaly_type'].value_counts())

        print("\n严重程度分布:")
        print(anomaly_df['severity'].value_counts())

        print("\n高危异常详情(前10条):")
        high_severity = anomaly_df[anomaly_df['severity'].isin(['critical', 'high'])]
        for _, row in high_severity.head(10).iterrows():
            print(f"\n  [{row['severity']}] {row['anomaly_type']}")
            print(f"    时间: {row['timestamp']}")
            print(f"    账号: {row['account']}")
            print(f"    IP: {row['client_ip']}")
            print(f"    描述: {row['description']}")

    return results, all_anomalies


def main():
    """主函数"""
    # 配置
    config = {
        'sensitive_tables': ['users', 'password', 'secret', 'token'],
        'allowed_ips': [],  # 留空表示不做IP白名单检查
        'work_hours': (9, 18),
        'large_export_threshold': 10000,
    }

    # 分析样本日志
    sample_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'sample_proxy_log.xlsx'
    )

    if os.path.exists(sample_path):
        results, anomalies = analyze_log_file(sample_path, config)
    else:
        print(f"样本文件不存在: {sample_path}")

        # 使用内置测试数据
        print("\n使用测试数据演示...")
        test_data = [
            {"sql": "SELECT * FROM users WHERE id = 1 OR 1=1", "account": "test_rw", "ip": "10.0.0.1"},
            {"sql": "DELETE FROM logs", "account": "admin_rw", "ip": "10.0.0.2"},
            {"sql": "/*{\"traceid\":\"abc\"}*/ SELECT * FROM orders WHERE id = ?", "account": "order_api_u25r4b_rw", "ip": "10.0.0.3"},
        ]

        parser = SQLParser()
        identifier = QueryIdentifier()
        detector = AnomalyDetector(config)

        for item in test_data:
            features = parser.parse(item['sql'])
            id_result = identifier.identify(item['sql'], item['account'])
            anomalies = detector.detect(item['sql'], item['account'], item['ip'], '2026-04-21 10:00:00', parser.to_dict(features))

            print(f"\nSQL: {item['sql'][:50]}...")
            print(f"  类型: {features.sql_type}")
            print(f"  来源: {id_result.source.value} (置信度: {id_result.confidence:.2f})")
            print(f"  风险: {features.risk_level}")
            if anomalies:
                print(f"  异常: {[a.description for a in anomalies]}")


if __name__ == '__main__':
    main()
