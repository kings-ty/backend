# Dockerfile

# --- Stage 1: Java 17 JRE builder ---
FROM eclipse-temurin:17-jre-jammy AS java-builder

# --- Stage 2: Python application build ---
FROM python:3.10-slim-bullseye

# Stage 1 builded Java 17 JRE copy.
COPY --from=java-builder /opt/java/openjdk /usr/local/openjdk-17

# Set JAVA_HOME environment variable
ENV JAVA_HOME /usr/local/openjdk-17
ENV PATH $PATH:$JAVA_HOME/bin

# apt-get update and install ca-certificates
# Required for HTTPS downloads and package list updates.
RUN apt-get update -y && \
    apt-get install -y ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements.txt and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Uvicorn run command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]