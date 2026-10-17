# Asosiy Python obrazini (eng yengil versiyasi) tanlaymiz
FROM python:3.11-slim

# Konteyner ichidagi ishchi papkani belgilaymiz
WORKDIR /app

# Atrof-muhit o'zgaruvchilarini sozlash (Python loglarni bufferlamasligi uchun)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Tizim paketlarini yangilash va kerakli kutubxonalarni o'rnatish
# timezone (tzdata) o'rnatamiz (O'zbekiston vaqti to'g'ri ishlashi uchun)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Talab etilgan paketlar ro'yxatini nusxalaymiz
COPY requirements.txt .

# Paketlarni o'rnatamiz
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Barcha kodlarni nusxalash
COPY . .

# Ma'lumotlar bazasi saqlanadigan papkani yaratamiz
RUN mkdir -p data

# Botni ishga tushirish komandasi
CMD ["python", "main.py"]
