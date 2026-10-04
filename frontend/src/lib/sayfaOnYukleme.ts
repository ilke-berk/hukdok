// Faz 4 (algılanan hız): sayfa parçasını kullanıcı tıklamadan önce indir. Menü öğesine fare gelince
// (ya da dava satırında kart önden yüklenirken) ilgili route parçası arkada `import()` edilir; tıklayınca
// App.tsx'teki `lazy(() => importWithReload(() => import(...)))` aynı modülü tarayıcının modül
// önbelleğinden anında alır — Suspense iskeleti çoğu kez hiç görünmez.
//
// Yollar App.tsx'teki lazy tanımlarıyla AYNI modüllerdir (bekçi: sayfaOnYukleme.test.ts). Hata
// yutulur: bayat parça (deploy sonrası 404) burada sessiz kalır, gerçek gezinmede `importWithReload`
// sayfayı bir kez yeniler (lib/chunkReload.ts). Her parça oturum başına en fazla bir kez istenir.

type Yukleyici = () => Promise<unknown>;

const YUKLEYICILER: Record<string, Yukleyici[]> = {
  "/": [() => import("../pages/dashboards/AvukatDashboard"), () => import("../pages/dashboards/IdariDashboard")],
  "/upload": [() => import("../pages/Index")],
  "/cases": [() => import("../pages/CaseList")],
  "/cases/:id": [() => import("../pages/CaseDetails")],
  "/clients": [() => import("../pages/ClientList")],
  "/activity-history": [() => import("../pages/ActivityHistory")],
  "/hukukbot": [() => import("../pages/HukukbotPage")],
  "/reports": [() => import("../pages/ReportsPage")],
  "/lexis": [() => import("../pages/LexisPage")],
  "/admin": [() => import("../pages/AdminPage")],
};

const istenenler = new Set<string>();

/** Bilinen bir route yolunun parçasını arkada indirir; bilinmeyen yol / ikinci çağrı no-op. */
export function sayfaParcasiniOnYukle(yol: string): void {
  const yukleyiciler = YUKLEYICILER[yol];
  if (!yukleyiciler || istenenler.has(yol)) return;
  istenenler.add(yol);
  for (const yukle of yukleyiciler) {
    yukle().catch(() => {
      // Sonraki fare gelişinde yeniden denenebilsin
      istenenler.delete(yol);
    });
  }
}

/** Test yardımcısı: hangi yolların önden yüklenebildiği. */
export const ON_YUKLENEBILIR_YOLLAR = Object.keys(YUKLEYICILER);
