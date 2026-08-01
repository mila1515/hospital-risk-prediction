FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && chown app:app /app

COPY --chown=app:app dashboard ./dashboard
COPY --chown=app:app etl ./etl

USER app

EXPOSE 8501

CMD ["streamlit", "run", "dashboard/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
