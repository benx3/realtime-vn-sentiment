# Use official Spark as base image
FROM apache/spark:3.5.1

# Add build arguments
ARG SPARK_PACKAGES=org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1

# Switch to root for installations
USER root

# Download Spark Kafka package, token-provider and Kafka client into Spark jars (ensure available at runtime)
RUN mkdir -p /opt/spark/jars && \
    wget -P /opt/spark/jars https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.1/spark-sql-kafka-0-10_2.12-3.5.1.jar && \
    wget -P /opt/spark/jars https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_2.12/3.5.1/spark-token-provider-kafka-0-10_2.12-3.5.1.jar && \
    wget -P /opt/spark/jars https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.4.1/kafka-clients-3.4.1.jar && \
    wget -P /opt/spark/jars https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar && \
    wget -P /opt/spark/jars https://repo1.maven.org/maven2/org/mongodb/spark/mongo-spark-connector_2.12/10.3.0/mongo-spark-connector_2.12-10.3.0.jar && \
    wget -P /opt/spark/jars https://repo1.maven.org/maven2/org/mongodb/mongodb-driver-sync/5.1.0/mongodb-driver-sync-5.1.0.jar && \
    wget -P /opt/spark/jars https://repo1.maven.org/maven2/org/mongodb/bson/5.1.0/bson-5.1.0.jar && \
    wget -P /opt/spark/jars https://repo1.maven.org/maven2/org/mongodb/mongodb-driver-core/5.1.0/mongodb-driver-core-5.1.0.jar

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SPARK_MASTER=local[*] \
    SPARK_DRIVER_HOST=localhost \
    SPARK_LOCAL_IP=127.0.0.1 \
    SPARK_LOCAL_HOSTNAME=localhost \
    PYSPARK_PYTHON=/usr/bin/python3 \
    PYSPARK_DRIVER_PYTHON=/usr/bin/python3 \
    PATH="${PATH}:/opt/spark/bin"
    
# Ensure Spark packages env available at runtime for ivy to download transitive deps
ENV SPARK_PACKAGES=org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1

# Install system dependencies and Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir pymongo==4.8.0 pytest requests numpy pandas

# Create necessary directories
RUN mkdir -p /app/checkpoints /app/logs /app/spark-events \
    && chmod -R 777 /app

# Set working directory
WORKDIR /app

# Copy application code
COPY . .

# Create a simple test script
RUN echo 'from pyspark.sql import SparkSession\n\
def test_spark():\n\
    spark = SparkSession.builder.appName("test").getOrCreate()\n\
    test_data = [(1, "test"), (2, "spark")]\n\
    df = spark.createDataFrame(test_data, ["id", "text"])\n\
    count = df.count()\n\
    print(f"Test dataframe count: {count}")\n\
    print("Spark test successful!")\n\
\n\
if __name__ == "__main__":\n\
    test_spark()' > /app/test_spark.py

# Create spark user and group (uid/gid 1001) and set ownership
RUN groupadd -g 1001 spark || true && \
    useradd -m -u 1001 -g spark -s /bin/bash spark || true && \
    mkdir -p /home/spark && \
    chown -R spark:spark /home/spark /app /opt/spark/jars /tmp || true && \
    chmod -R 755 /home/spark || true

# Configure Hadoop/Spark user and local warehouse (avoid HDFS/viewfs attempts)
ENV HADOOP_USER_NAME=spark \
    SPARK_USER=spark \
    SPARK_GROUP=spark \
    SPARK_SQL_WAREHOUSE_DIR=/app/warehouse

RUN mkdir -p /app/warehouse && chown -R spark:spark /app/warehouse || true

# Switch to spark user for running the app
USER spark

# Create entrypoint script using a heredoc (more robust than echo with many escapes)
RUN mkdir -p /home/spark/.ivy2 && chown -R spark:spark /home/spark/.ivy2 || true

RUN cat > /app/entrypoint.sh <<'SH'
#!/bin/bash
user=${SPARK_USER:-$(whoami)}
group=${SPARK_GROUP:-$(id -gn)}
if [ "$user" = "root" ]; then
    mkdir -p /.ivy2
    chmod 777 /.ivy2
    export SPARK_USER_NAME=spark
fi

if [ "$1" = "test" ]; then
    exec spark-submit \
        --packages ${SPARK_PACKAGES} \
        --jars /opt/spark/jars/spark-sql-kafka-0-10_2.12-3.5.1.jar,/opt/spark/jars/spark-token-provider-kafka-0-10_2.12-3.5.1.jar \
        --conf spark.jars.ivy=/home/spark/.ivy2 \
        --conf spark.hadoop.user.name=spark \
        --master ${SPARK_MASTER} \
        --conf spark.driver.host=${SPARK_DRIVER_HOST} \
        --conf spark.driver.bindAddress=0.0.0.0 \
        /app/test_spark.py
else
    exec spark-submit \
        --packages ${SPARK_PACKAGES} \
        --jars /opt/spark/jars/spark-sql-kafka-0-10_2.12-3.5.1.jar,/opt/spark/jars/spark-token-provider-kafka-0-10_2.12-3.5.1.jar \
        --conf spark.jars.ivy=/home/spark/.ivy2 \
        --conf spark.hadoop.user.name=spark \
        --master ${SPARK_MASTER} \
        --conf spark.driver.host=${SPARK_DRIVER_HOST} \
        --conf spark.driver.bindAddress=0.0.0.0 \
        /app/main_streaming.py
fi
SH
RUN chmod +x /app/entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD ps aux | grep "spark" | grep -v grep || exit 1

# Set working directory and copy application files
WORKDIR /app
COPY . .

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["run"]
