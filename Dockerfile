# Hugging Face Docker Space（Streamlit 模板）通用容器
# 本地运行: docker build -t genshin-calc . && docker run -p 8501:8501 genshin-calc
FROM python:3.11-slim

WORKDIR /app

# 先复制依赖清单以利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HF Space 要求监听 0.0.0.0 且端口与 README.md 中 app_port 一致
EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
