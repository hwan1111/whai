FROM apache/airflow:3.0.6-python3.12

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# 뉴스 수집 DAG 의존성 (Playwright 크롤링 + S3)
RUN pip install --no-cache-dir \
    playwright \
    boto3 \
    beautifulsoup4 \
    pymysql \
    FinanceDataReader \
    && playwright install chromium

# 주가 예측/재학습 DAG 의존성
#   finance_stock_predict_daily / finance_model_retrain 태스크가 런타임에 import.
#   누락 시 ModuleNotFoundError 발생.
RUN pip install --no-cache-dir \
    "mlflow>=2.14.0" \
    "scikit-learn>=1.3.0" \
    "lightgbm>=4.0.0" \
    "xgboost>=2.0.0" \
    "torch>=2.1.0" \
    "statsmodels>=0.14.0" \
    "arch>=6.0.0" \
    "prophet>=1.1.5" \
    "yfinance>=0.2.30" \
    "finance-datareader>=0.9.50" \
    "pykrx>=1.0.40" \
    "pymysql>=1.1.0"
