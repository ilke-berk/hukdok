import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

// İçerik yüklenirken spinner yerine içeriğin ŞEKLİ çizilir (algılanan hız). Kural: spinner yalnız
// kullanıcının başlattığı eylemde (Kaydet/Analiz/İndir düğmesi) kalır; sayfa/kart/liste yüklemesi
// bu kalıplarla gösterilir. Her kalıp `SkeletonRegion` içindedir: tek `role="status"` + sr-only
// "Yükleniyor…" (ekran okuyucu ve testler için spinner'lı eski hâliyle eşdeğer), bloklar aria-hidden.

const VARSAYILAN_ETIKET = "Yükleniyor…";

export function SkeletonRegion({
  label = VARSAYILAN_ETIKET,
  className,
  children,
}: {
  label?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div role="status" aria-live="polite" aria-busy="true" className={cn("skeleton-region", className)}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

// Hücre genişlikleri sabit bir desenden gelir (rastgele değil): her render'da aynı, testte kararlı.
const HUCRE_GENISLIKLERI = ["w-3/4", "w-1/2", "w-2/3", "w-5/12", "w-7/12"];

export function TableSkeleton({
  rows = 8,
  columns = 6,
  header = true,
  label,
  className,
}: {
  rows?: number;
  columns?: number;
  /** Sütun başlığı satırı (gerçek tabloda thead yoksa — satır listesi — kapatılır). */
  header?: boolean;
  label?: string;
  className?: string;
}) {
  const kolonSayisi = Math.max(1, columns);
  // İlk kolon (dava no / ad) geniş; diğerleri eşit.
  const gridTemplateColumns = `minmax(0,2fr) repeat(${kolonSayisi - 1}, minmax(0,1fr))`;
  return (
    <SkeletonRegion label={label} className={className}>
      <div data-testid="table-skeleton" aria-hidden="true">
        {header && (
          <div
            className="grid gap-4 px-5 py-3 border-b border-[var(--border)] bg-[var(--bg)]"
            style={{ gridTemplateColumns }}
          >
            {Array.from({ length: kolonSayisi }, (_, c) => (
              <Skeleton key={c} className="h-2.5 w-1/2" />
            ))}
          </div>
        )}
        {Array.from({ length: rows }, (_, r) => (
          <div
            key={r}
            data-skeleton-row=""
            className="grid gap-4 px-5 py-3.5 border-b border-[var(--border)]"
            style={{ gridTemplateColumns }}
          >
            {Array.from({ length: kolonSayisi }, (_, c) => (
              <Skeleton
                key={c}
                className={cn("h-3", c === 0 ? "w-4/5" : HUCRE_GENISLIKLERI[(r + c) % HUCRE_GENISLIKLERI.length])}
              />
            ))}
          </div>
        ))}
      </div>
    </SkeletonRegion>
  );
}

export function CardListSkeleton({
  count = 4,
  itemClassName = "h-14",
  label,
  className,
}: {
  count?: number;
  itemClassName?: string;
  label?: string;
  className?: string;
}) {
  return (
    <SkeletonRegion label={label} className={cn("space-y-2", className)}>
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} className={cn("w-full", itemClassName)} />
      ))}
    </SkeletonRegion>
  );
}

// Başlıktaki sayaç ("123 kayıt") yerine satır içi kısa çubuk.
export function InlineSkeleton({ className }: { className?: string }) {
  return <Skeleton className={cn("inline-block h-2.5 w-14 align-middle", className)} />;
}

// Satır içi iki çizgili liste öğesi (bildirim, not, oturum): başlık + alt satır.
export function LineListSkeleton({
  count = 3,
  label,
  className,
}: {
  count?: number;
  label?: string;
  className?: string;
}) {
  return (
    <SkeletonRegion label={label} className={cn("space-y-3", className)}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="space-y-1.5">
          <Skeleton className={cn("h-3", HUCRE_GENISLIKLERI[i % HUCRE_GENISLIKLERI.length])} />
          <Skeleton className="h-2.5 w-1/3" />
        </div>
      ))}
    </SkeletonRegion>
  );
}

export function DetailSkeleton({ label, className }: { label?: string; className?: string }) {
  return (
    <SkeletonRegion label={label} className={cn("space-y-6", className)}>
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-[400px] w-full" />
    </SkeletonRegion>
  );
}

// Uygulama kabuğunun silueti (menü + üst bar + sayfa): kabuk henüz çizilemezken (MSAL açılışı, kabuk
// dışı Suspense) tam ekran spinner yerine. Gelecek ekranın düzeni önceden görünür.
export function AppShellSkeleton({ label }: { label?: string }) {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground">
      <SkeletonRegion label={label} className="flex w-full">
        <div aria-hidden="true" className="hidden md:flex w-56 shrink-0 flex-col gap-3 border-r border-border p-4">
          <Skeleton className="h-7 w-32 mb-4" />
          {Array.from({ length: 7 }, (_, i) => (
            <Skeleton key={i} className="h-4 w-36" />
          ))}
        </div>
        <div className="flex-1 min-w-0 flex flex-col">
          <div aria-hidden="true" className="h-14 border-b border-border px-7 flex items-center">
            <Skeleton className="h-4 w-40" />
          </div>
          <div aria-hidden="true" className="px-7 pt-6 space-y-5">
            <Skeleton className="h-6 w-56" />
            <Skeleton className="h-8 w-80 max-w-full" />
            <Skeleton className="h-[320px] w-full" />
          </div>
        </div>
      </SkeletonRegion>
    </div>
  );
}

// Kabuk içi genel sayfa iskeleti: başlık + filtre şeridi + tablo. Parça (lazy route) inerken ve
// sayfa ilk verisini beklerken kullanılır; menü/üst bar yerinde kalır.
export function PageSkeleton({ label, className }: { label?: string; className?: string }) {
  return (
    <SkeletonRegion label={label} className={cn("space-y-5", className)}>
      <div className="space-y-2">
        <Skeleton className="h-6 w-56" />
        <Skeleton className="h-3 w-80 max-w-full" />
      </div>
      <div className="flex gap-2">
        <Skeleton className="h-8 w-64 max-w-full" />
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-8 w-24" />
      </div>
      <div className="border border-[var(--border)]">
        <div aria-hidden="true">
          {Array.from({ length: 7 }, (_, r) => (
            <div key={r} className="flex gap-4 px-5 py-3.5 border-b border-[var(--border)] last:border-b-0">
              <Skeleton className="h-3 w-1/4" />
              <Skeleton className={cn("h-3", HUCRE_GENISLIKLERI[r % HUCRE_GENISLIKLERI.length], "max-w-[40%]")} />
              <Skeleton className="h-3 w-1/6 ml-auto" />
            </div>
          ))}
        </div>
      </div>
    </SkeletonRegion>
  );
}
