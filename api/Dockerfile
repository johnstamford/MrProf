FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /srv

COPY api/requirements.txt api/pytest.ini ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api/app ./app
COPY api/tests ./tests
COPY sim ./sim

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
