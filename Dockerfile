# ==============================================================================
# OpenFileRescue - Production & Development Container
# Open-Source Photo, Video & Data Recovery
# ==============================================================================
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENFILERESCUE_HOST=0.0.0.0 \
    OPENFILERESCUE_PORT=8765 \
    OPENFILERESCUE_NO_BROWSER=1

WORKDIR /app

# Install lightweight runtime dependencies (Pillow for EXIF thumbnails & image previews)
RUN pip install --no-cache-dir pillow>=9.0.0

# Copy application source and metadata
COPY openfilerescue/ /app/openfilerescue/
COPY run.py /app/run.py
COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY LICENSE /app/LICENSE

# Create mount point directories for disk images and recovered files
RUN mkdir -p /app/recovered_files /app/images

# Expose web dashboard port
EXPOSE 8765

# Declare persistent storage volumes
VOLUME ["/app/recovered_files", "/app/images"]

# Default entrypoint allows passing any CLI flags or running web UI
ENTRYPOINT ["python", "run.py"]
CMD ["--web", "--host", "0.0.0.0"]
