FROM python:3.11-slim

# Install Java (required for PySpark)
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/default-java

# Install Python dependencies
RUN pip install --no-cache-dir \
    pyspark==3.5.1 \
    boto3==1.34.69 \
    kafka-python==2.0.2 \
    prometheus_client==0.20.0 \
    python-dotenv==1.0.1 \
    Faker==24.2.0 \
    numpy==1.24.4 \
    pandas==2.0.3

WORKDIR /app

# Copy JAR files for Kafka/Spark integration
COPY jars/ /app/jars/

# Copy source code
COPY src/ /app/src/

ENV PYTHONPATH=/app
ENV PYSPARK_PYTHON=python3
