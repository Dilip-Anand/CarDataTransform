# Databricks notebook source
# MAGIC %md
# MAGIC # GOLD Transform Dimension Branch

# COMMAND ----------

from pyspark.sql.functions import *
from pyspark.sql.types import *
from delta.tables import DeltaTable

# COMMAND ----------

# MAGIC %md
# MAGIC ### Create a Flag Parameter

# COMMAND ----------

# MAGIC %md
# MAGIC ###### Creating a flag parameter to keep a note on the run. To check whether the run is initial load or incremental load

# COMMAND ----------

dbutils.widgets.text("Load_Flag", '0')
Load_Flag = dbutils.widgets.get("Load_Flag")

# COMMAND ----------

# MAGIC %md
# MAGIC #### Fetch the data from Silver layer to view the dataset

# COMMAND ----------

# MAGIC %sql
# MAGIC select * from parquet.`abfss://silver@cardemodatalake.dfs.core.windows.net/CarSalesData`
# MAGIC

# COMMAND ----------

# MAGIC %md
# MAGIC ## CREATE DIMENSION MODEL

# COMMAND ----------

# MAGIC %md
# MAGIC ##### Create a model table from the above fetched data to crete a Dimenstion Table

# COMMAND ----------

df_source = spark.sql('''
    select Distinct(Branch_ID) as BranchID, BranchName as BranchNAME from parquet.`abfss://silver@cardemodatalake.dfs.core.windows.net/CarSalesData`
''')

display(df_source)

# COMMAND ----------

# MAGIC %md
# MAGIC #### Create a Sink to store both inital and incremental data

# COMMAND ----------

if spark.catalog.tableExists('cars_catalog.gold.dim_branch') :

    df_sink = spark.sql('''
    select dim_Branch_Key, BranchID, BranchName 
    from cars_catalog.gold.dim_branch
    ''')

else:
    df_sink = spark.sql('''
    select 1 as dim_Branch_Key, Branch_ID, BranchName 
    from parquet.`abfss://silver@cardemodatalake.dfs.core.windows.net/CarSalesData`
    where True=False
    ''')

# COMMAND ----------

display(df_source)


# COMMAND ----------

# MAGIC %md
# MAGIC #### Filtering new records and old records

# COMMAND ----------

df_filter = df_source.join(df_sink, df_source['BranchID'] == df_sink['BranchID'], how='left').select(df_source['BranchID'], df_source['BranchNAME'], df_sink['dim_Branch_Key'])

display(df_filter)

# COMMAND ----------

# MAGIC %md
# MAGIC #### Get the existing values 

# COMMAND ----------

df_filter_old = df_filter.filter(df_filter['dim_Branch_Key'].isNotNull())


# COMMAND ----------

# MAGIC %md
# MAGIC #### Get the incremental or new values

# COMMAND ----------

df_filter_new = df_filter.filter(df_filter['dim_Branch_Key'].isNull())


# COMMAND ----------

# MAGIC %md
# MAGIC ### Create Surrogate key and assign the values 

# COMMAND ----------

if Load_Flag == '0':
    max_value = 1
else:
    df_max_value = spark.sql("Select max('dim_Branch_key') from cars_catalog.gold.dim_branch")
    max_value = df_max_value.collect()[0][0]

# COMMAND ----------

df_filter_new = df_filter_new.withColumn('dim_Branch_Key', max_value + monotonically_increasing_id()+1) 

# COMMAND ----------

# MAGIC %md
# MAGIC ### Create a new DF to store all the data Initial+incremental

# COMMAND ----------

df_final = df_filter_new.union(df_filter_old)

# COMMAND ----------

df_final = df_final.withColumn('dim_Branch_Key', col('dim_Branch_Key').cast("BIGINT"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Perform Upsert to Insert new data and merge exisiting data

# COMMAND ----------

if spark.catalog.tableExists('cars_catalog.gold.dim_branch') :
    #incremental Data
    delta_table = DeltaTable.forPath(spark,"abfss://gold@cardemodatalake.dfs.core.windows.net/dim_branch")

    delta_table.alias('target').merge(df_final.alias('source'), 'target.dim_Branch_Key = source.dim_Branch_Key').whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()

    #initial Data
else: 
    df_final.write.format("delta").mode("overwrite").option("path","abfss://gold@cardemodatalake.dfs.core.windows.net/dim_branch").saveAsTable("cars_catalog.gold.dim_branch")

# COMMAND ----------

# MAGIC %sql
# MAGIC select * from cars_catalog.gold.dim_branch

# COMMAND ----------

