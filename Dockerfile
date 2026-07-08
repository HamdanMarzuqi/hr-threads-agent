FROM python:3.11-slim

# Set timezone untuk mesin docker (sangat penting agar jam jadwal akurat)
ENV TZ=Asia/Jakarta
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy semua file ke dalam container
COPY . .

# Jalankan bot
CMD ["python", "main.py"]
