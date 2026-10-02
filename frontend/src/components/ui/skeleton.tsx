import { cn } from "@/lib/utils";

// Tek skeleton bloğu. Renk `.skeleton-block` (index.css): ön plan renginin %9'u — altı hangi tema/yüzey
// olursa olsun (açık/koyu, bg/bg-elevated) görünür, bordo değil nötrdür. Köşe kare (tasarım dili);
// "hareketi azalt" tercihinde nabız durur, düz blok kalır. Dekoratiftir: ekran okuyucuya kapsayıcı
// (`SkeletonRegion`) "Yükleniyor" der, blok kendisi gizlidir.
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn("skeleton-block animate-pulse motion-reduce:animate-none", className)}
      {...props}
    />
  );
}

export { Skeleton };
