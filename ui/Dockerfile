FROM python:3.11-slim
ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1
RUN pip install streamlit==1.40.1 requests==2.32.3 pandas==2.2.3 \
    && useradd --create-home --uid 1000 app
WORKDIR /srv
COPY ui/app.py .
USER app
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
