FROM python:3.12-slim

WORKDIR /app

# Install system deps for OpenCV
RUN apt-get update && apt-get install -y \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Build context is project root — copy requirements first for layer caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Model weights (gitignored) are not baked into the image. Provide them at
# runtime by mounting a volume into /app/models:
#   docker run -v /path/to/models:/app/models ...
# (The Render deploy uses the python runtime + scripts/download_models.sh
#  instead — see backend/render.yaml.)

EXPOSE 8000
CMD ["python", "app.py"]
