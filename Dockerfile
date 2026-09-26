FROM python:3.12-slim

WORKDIR /app
COPY opener /app/opener

ENV PYTHONUNBUFFERED=1
ENV OPENER_HOST=0.0.0.0
ENV OPENER_PORT=8010
ENV LAYA_URL=http://host.docker.internal:8001/v1/systemone
ENV LAYA_HEALTH=http://host.docker.internal:8001/health

EXPOSE 8010
CMD ["python", "-m", "opener.server"]
