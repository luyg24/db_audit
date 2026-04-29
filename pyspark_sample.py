import pandas as pd
from pyspark.sql.session import SparkSession
from sklearn.preprocessing import MinMaxScaler
import pickle
spark = SparkSession.builder.appName("ParallelDataFrame").getOrCreate()

sql = """
    select  client_ip,
            db_name,
            db_service_name,
            client_account,
            sql_template
    from    infosec_zksec.sec_db_policy_online_30d_novisit_srcipusn_db_detail v
    where   v.dt = '2024-05-30-10'
        limit 5000000
    """
df = spark.sql(sql)
res = df.collect()
df = spark.createDataFrame(res, ["client_ip","db_name","db_service_name","client_account","sql_template"])
# df.show()
df_rdd = df.rdd
ip_rdd = df_rdd.map(lambda x: x[0])
ip_freq = ip_rdd.map(lambda x: (x, 1)).reduceByKey(lambda a, b: a + b)
res_rdd = df_rdd.map(lambda x: x[1])
res_freq = res_rdd.map(lambda x: (x, 1)).reduceByKey(lambda a, b: a + b)
time_rdd = df_rdd.map(lambda x: x[2])
time_freq = time_rdd.map(lambda x: (x, 1)).reduceByKey(lambda a, b: a + b)
sql_rdd = df_rdd.map(lambda x: x[3])
sql_freq = sql_rdd.map(lambda x: (x, 1)).reduceByKey(lambda a, b: a + b)
db_rdd = df_rdd.map(lambda x: x[4])
db_freq = db_rdd.map(lambda x: (x, 1)).reduceByKey(lambda a, b: a + b)

col_ip = spark.createDataFrame(ip_freq.collect(),["client_ip2","ip_freq"])
col_res = spark.createDataFrame(res_freq.collect(),["db_name2","db_freq"])
col_time = spark.createDataFrame(time_freq.collect(),["db_service_name2","service_freq"])
col_sql = spark.createDataFrame(sql_freq.collect(),["client_account2","acc_freq"])
col_db = spark.createDataFrame(db_freq.collect(),["sql_template2","sql_freq"])

res_df = df.join(col_ip,df["client_ip"]==col_ip["client_ip2"],"left")
res_df = res_df.join(col_res,df["db_name"]==col_res["db_name2"],"left")
res_df = res_df.join(col_time,df["db_service_name"]==col_time["db_service_name2"],"left")
res_df = res_df.join(col_sql,df["client_account"]==col_sql["client_account2"],"left")
res_df = res_df.join(col_db,df["sql_template"]==col_db["sql_template2"],"left")
res_df = res_df.na.drop()

res_df1 = res_df.select(["ip_freq","db_freq","service_freq","acc_freq","sql_freq"])
res_df2 = res_df.select(["client_ip2","db_name2","db_service_name2","client_account2","sql_template2"])

# res_df2 = spark.createDataFrame(res_df2.collect(), ["ip_freq","res_freq","time_freq","sql_freq","db_freq"])
df = pd.DataFrame(res_df1.collect(),columns = ["ip_freq","db_freq","service_freq","acc_freq","sql_freq"])
df_ans = pd.DataFrame(res_df2.collect(),columns = ["client_ip","db_name","db_service_name","client_account","sql_template"])

scaler = MinMaxScaler()
update_data = scaler.fit_transform(df)
res_df2 = pd.DataFrame(update_data, columns = ["ip_freq","db_freq","service_freq","acc_freq","sql_freq"])
# df_ans = df_ans.rename(columns={'client_ip2': 'client_ip', 'result_lines2': 'result_lines', 'time_stamp2': 'time_stamp','sql_template2':'sql_template','db_name2':'db_name'})




with open('xgb_info.pkl', 'rb') as file:
    xgbm = pickle.load(file)

y_pred = xgbm.predict(res_df2)
df_ans['predict_result'] = y_pred

columns_all =['dbproxy_cluster_id',
            'db_service_name',
            'time_stamp',
            'log_type',
            'version',
            'worker_thread_id',
            'request_id',
            'operation_type',
            'client_ip',
            'client_port',
            'client_field',
            'client_account',
            'server_ip',
            'server_port',
            'server_thread_id',
            'request_time_consumption',
            'process_request_time_consumption',
            'send_time_consumption',
            'wait_time_consumption',
            'read_result_time_consumption',
            'process_result_time_consumption',
            'send_result_time_consumption',
            'all_time_consumption',
            'effect_lines',
            'result_size',
            'status',
            'result_lines',
            'proxy_ip',
            'proxy_port',
            'cluster_name',
            'db_name',
            'character_set',
            'sql_id',
            'request_type',
            'packet_size',
            'sql',
            'sql_template',
            'predict_result',
            'dt'] 

df_ans = df_ans.reindex(columns = columns_all)

sparkdf = spark.createDataFrame(df_ans)
sparkdf.show()

sparkdf.createOrReplaceTempView("T_URL")
insert_sql = '''
    insert overwrite table datasec.db_proxy_log_ai_predict_01 partition(dt='{2024-05-30-10}')
    select dbproxy_cluster_id,db_service_name,time_stamp,log_type,version,worker_thread_id,request_id,operation_type,client_ip,client_port,client_field,client_account,server_ip,server_port,server_thread_id,request_time_consumption,process_request_time_consumption,send_time_consumption,wait_time_consumption,read_result_time_consumption,process_result_time_consumption,send_result_time_consumption,all_time_consumption,effect_lines,result_size,status,result_lines,proxy_ip,proxy_port,cluster_name,db_name,character_set,sql_id,request_type,packet_size,sql,sql_template,predict_result 
    from T_URL
'''
spark.sql(insert_sql)
