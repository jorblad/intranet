FROM python:3.14-slim

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY requirements.txt .
# Install system build dependencies required to compile native wheels (libvalkey, cryptography)
RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		build-essential \
		libssl-dev \
		libffi-dev \
		pkg-config \
	&& rm -rf /var/lib/apt/lists/* \
	&& python -m pip install --upgrade pip \
	&& pip install -r requirements.txt

COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
