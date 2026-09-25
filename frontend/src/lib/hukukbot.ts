// Hukukbot ayrı uygulamadır (kendi alanı + kendi girişi); kenar menüden yeni sekmede açılır.
// Adres build'de VITE_HUKUKBOT_URL ile değişir (lokalde lokal hukukbot, ör. http://localhost:3010);
// tanımsız/boşsa prod adresi.
export const HUKUKBOT_VARSAYILAN_URL = "https://hukbot.tragic.tr";

export function hukukbotAdresi(deger: string | undefined): string {
  const temiz = deger?.trim();
  return temiz ? temiz : HUKUKBOT_VARSAYILAN_URL;
}

export const HUKUKBOT_URL = hukukbotAdresi(import.meta.env.VITE_HUKUKBOT_URL);
