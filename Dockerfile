FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY digital_twin_evaluation ./digital_twin_evaluation
RUN python -m pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "digital_twin_evaluation"]
CMD ["list"]
