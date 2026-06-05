# Hugging Face Spaces (Docker SDK).
# Serves the dashboard from the committed snapshot in data/snapshot/, so none
# of the ~15 MB raw Home Office ODS files are needed on the host. HF routes
# traffic to the port declared as `app_port` in the Space README (7860 — it
# must match the bind below).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860
CMD ["gunicorn", "app:server", "--workers", "1", "--threads", "4", "--timeout", "120", "--bind", "0.0.0.0:7860"]
