FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN addgroup --system app && adduser --system --ingroup app --no-create-home app

COPY --chown=app:app . .

USER app

EXPOSE 8000

CMD ["fastapi", "run", "src", "--port", "8000", "--host", "0.0.0.0"]
