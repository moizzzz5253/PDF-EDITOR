# Same app, many users: docker build -t pdfscope . && docker run -p 8000:8000 -v pdfscope-data:/data pdfscope
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/pdfscope
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PDFSCOPE_WORKSPACE=/data HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["python", "run.py"]
