// Bugün arşivlenen belgeler — backend per-belge akış endpoint'i gelene kadar
// localStorage üzerinde, güne göre (yerel tarih) tutulur. Gece yarısı sıfırlanır.
// Hem sayaç (drop zone) hem "Bugünkü yüklemelerim" listesi bu kayıttan beslenir.

const KEY = "hukudok-today-uploads";
const MAX_ITEMS = 50; // localStorage'ı şişirmemek için gün içi kayıt tavanı

export type TodayUploadStatus = "BAĞLANDI" | "ARŞİVLENDİ" | "İŞLENİYOR" | "SIRADA";

export interface TodayUploadItem {
  id: string;
  filename: string;
  sizeBytes: number;
  ext: string;            // "PDF", "DOCX", ... (büyük harf, noktasız)
  clientName?: string;
  caseNo?: string;
  uploader?: string;      // yükleyen kişi (kaynak satırı)
  status: TodayUploadStatus;
  ts: number;             // epoch ms — "x dk önce" hesabı için
}

interface Store {
  date: string;
  items: TodayUploadItem[];
}

function todayKey(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// Kaydı oku; tarih değiştiyse (yeni gün) boş döndür → otomatik sıfırlama.
function read(): Store {
  const empty: Store = { date: todayKey(), items: [] };
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return empty;
    const obj = JSON.parse(raw) as Partial<Store>;
    if (obj.date !== todayKey()) return empty;
    return { date: todayKey(), items: Array.isArray(obj.items) ? obj.items : [] };
  } catch {
    return empty;
  }
}

export function getTodayUploadItems(): TodayUploadItem[] {
  return read().items;
}

export function getTodayUploads(): number {
  return read().items.length;
}

// Yeni bir arşivlenen belge ekle (en yeni en üstte). Güncel listeyi döndürür ki
// çağıran hem sayacı hem listeyi tek seferde tazeleyebilsin.
export function addTodayUpload(item: Omit<TodayUploadItem, "id" | "ts">): TodayUploadItem[] {
  const store = read();
  const full: TodayUploadItem = {
    ...item,
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    ts: Date.now(),
  };
  const items = [full, ...store.items].slice(0, MAX_ITEMS);
  try {
    localStorage.setItem(KEY, JSON.stringify({ date: todayKey(), items }));
  } catch {
    /* storage erişilemez — bu oturumda kalıcı olmaz */
  }
  return items;
}
