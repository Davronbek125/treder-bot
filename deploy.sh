#!/bin/bash
# Treder Bot - Deployment va Yangilash skripti

echo "🚀 Treder Bot: Deployment boshlanmoqda..."

# 1. Eng yangi kodni tortish (agar Git ulangan bo'lsa)
# git pull origin main

# 2. Eski konteynerlarni to'xtatish va o'chirish
echo "⏹ Eski konteyner to'xtatilmoqda..."
docker compose down

# 3. Yangi tasvirni (image) qurish va orqa fonda ishga tushirish
echo "🏗 Yangi versiya yig'ilmoqda va ishga tushirilmoqda..."
docker compose up -d --build

# 4. Tozalash (keraksiz/dangling Docker imagelarni o'chirish)
docker image prune -f

echo "✅ Deployment muvaffaqiyatli yakunlandi!"
echo "Loglarni ko'rish uchun: docker compose logs -f"
