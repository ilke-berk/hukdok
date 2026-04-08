#!/bin/bash

# Renk tanımlamaları
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}   HukuDok v2 Deployment Başlatılıyor    ${NC}"
echo -e "${BLUE}=========================================${NC}"

# 1. Ortam dosyası kontrolü
if [ ! -f .env ]; then
    echo -e "${RED}Hata: .env dosyası bulunamadı!${NC}"
    exit 1
fi

# 2. Kodları güncelle
echo -e "${YELLOW}🔄 Kodlar güncelleniyor (Git Pull)...${NC}"
# git pull komutunu projenin git yapısına göre aktif edebilirsin
git pull origin main || echo -e "${RED}Uyarı: Git pull başarısız oldu veya git repo değil.${NC}"

# 3. Eski konteynerleri durdur
echo -e "${YELLOW}🛑 Mevcut servisler durduruluyor...${NC}"
docker-compose down --remove-orphans

# 4. Yeniden Build ve Start
echo -e "${YELLOW}🏗️  Docker imajları oluşturuluyor ve başlatılıyor...${NC}"
docker-compose up -d --build

# 5. Sağlık Kontrolü
echo -e "${YELLOW}🧪 Servisler kontrol ediliyor...${NC}"
sleep 5
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 6. Temizlik (Eski imajları siler)
echo -e "${YELLOW}🧹 Gereksiz Docker imajları temizleniyor...${NC}"
docker image prune -f

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN} ✅ Karada ölüm yok! HukuDok v2 LIVE!     ${NC}"
echo -e "${GREEN}=========================================${NC}"
