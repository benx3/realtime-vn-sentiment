import os
from pyspark.sql import SparkSession, functions as F, types as T
from pyspark.ml import Pipeline
from pyspark.ml.feature import Tokenizer, StopWordsRemover, HashingTF, IDF
from pyspark.ml.classification import LogisticRegression

spark = (SparkSession.builder
    .appName("vn-sentiment-realtime")
    .config("spark.mongodb.write.connection.uri","mongodb://mongo:27017")
    .getOrCreate())

schema = T.StructType([
    T.StructField("platform", T.StringType()),
    T.StructField("review_id", T.StringType()),
    T.StructField("product_id", T.StringType()),
    T.StructField("category_id", T.StringType()),
    T.StructField("category_name", T.StringType()),
    T.StructField("rating", T.IntegerType()),
    T.StructField("title", T.StringType()),
    T.StructField("content", T.StringType()),
    T.StructField("create_time", T.StringType()),
])

raw = (spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092"))
    .option("subscribe","reviews_raw")
    .option("startingOffsets","earliest")
    .option("failOnDataLoss","false").load())
json_df = raw.select(F.from_json(F.col("value").cast("string"), schema).alias("j")).select("j.*")

@F.udf(T.StringType())
def clean_text(t, c):
    import re
    s = (t or "") + " " + (c or "")
    s = s.lower()
    s = re.sub(r"http\S+|www\.\S+"," ", s)
    s = re.sub(r"(.)\1{2,}", r"\1\1", s)
    s = re.sub(r"[^a-zàáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ0-9\s]"," ", s)
    s = re.sub(r"\s+"," ", s).strip()
    return s

df = json_df.withColumn("text", clean_text("title","content")).filter(F.length("text")>3)
labeled = df.withColumn("label",
    F.when(F.col("rating") >= 4, F.lit(1)).when(F.col("rating") <= 2, F.lit(0)))

pipe = Pipeline(stages=[
    Tokenizer(inputCol="text", outputCol="tok"),
    StopWordsRemover(inputCol="tok", outputCol="tok2"),
    HashingTF(inputCol="tok2", outputCol="tf", numFeatures=1<<18),
    IDF(inputCol="tf", outputCol="tfidf"),
    LogisticRegression(featuresCol="tfidf", labelCol="label", maxIter=30, regParam=1e-3)
])

model_bc = {"model": None}

def foreach_batch(batch_df, bid):
    print(f"[SPARK BATCH {bid}] Received batch with {batch_df.count()} rows")
    labeled_batch = batch_df.filter("label is not null")
    labeled_count = labeled_batch.count()
    print(f"[SPARK BATCH {bid}] Labeled rows: {labeled_count}")
    
    if labeled_count >= 30:
        print(f"[SPARK BATCH {bid}] Training model with {labeled_count} labeled samples...")
        model_bc["model"] = pipe.fit(labeled_batch)
        print(f"[SPARK BATCH {bid}] Model trained successfully!")
    
    m = model_bc.get("model")
    if m is not None:
        print(f"[SPARK BATCH {bid}] Model exists, making predictions...")
        pred = m.transform(batch_df)
        
        # UDF to convert label to Vietnamese
        from pyspark.sql.types import StringType
        def label_to_vn(label):
            label_map = {0: "Không tốt", 1: "Tốt", 2: "Trung bình"}
            return label_map.get(label, f"Unknown({label})")
        
        label_to_vn_udf = F.udf(label_to_vn, StringType())
        
        # Use original review_id from input instead of generated monotonic id to avoid duplicates
        pred_out = (pred.select(
            F.col("review_id").cast("string"),
            "platform","product_id","category_id","category_name","rating","text",
            F.col("prediction").cast("int").alias("pred_label"),
            label_to_vn_udf(F.col("prediction").cast("int")).alias("pred_label_vn"),
            F.col("probability").cast("string").alias("pred_proba_vec"),
            F.current_timestamp().alias("ts"),
            F.lit("spark-baseline").alias("model")
        ).withColumnRenamed("review_id","review_id"))

        # Filter out rows without review_id to maintain unique constraint integrity
        pred_out = pred_out.filter(F.col("review_id").isNotNull())
        pred_count = pred_out.count()
        print(f"[SPARK BATCH {bid}] Writing {pred_count} predictions to MongoDB...")

        (pred_out.write.format("mongodb").option("database","reviews_db")
            .option("collection","reviews_pred").mode("append").save())
        print(f"[SPARK BATCH {bid}] Successfully wrote {pred_count} predictions!")
    else:
        print(f"[SPARK BATCH {bid}] No model available, skipping predictions")


# Use the labeled DataFrame for streaming so `label` exists in foreach_batch
(labeled.writeStream.outputMode("append")
    .foreachBatch(foreach_batch)
    .option("checkpointLocation","/tmp/chk_sentiment")
    .start()).awaitTermination()
