// @vitest-environment jsdom
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Suspense, act, lazy } from "react";
import { createRoot, type Root } from "react-dom/client";

import { CHUNK_RELOAD_FLAG, importWithReload, isChunkLoadError } from "@/lib/chunkReload";

// G182: route düzeyinde kod bölme. İki şey kilitlenir:
// 1) bayat parça (deploy sonrası 404) → sayfa BİR kez yenilenir, sessionStorage bayrağı döngüyü keser;
// 2) App.tsx'te Login/NotFound dışındaki tüm sayfalar lazy, sonner dinamik import'u yok.

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const chromiumChunkError = () =>
  new TypeError("Failed to fetch dynamically imported module: http://localhost:8080/assets/AdminPage-Dx1y2z3.js");

/** Söz belirli sürede çözülmedi/reddedilmedi mi? (yenileme dalı sözü askıda bırakır) */
async function staysPending(promise: Promise<unknown>, ms = 50): Promise<boolean> {
  const PENDING = Symbol("pending");
  const settled = await Promise.race([
    promise.then(
      () => "resolved",
      () => "rejected",
    ),
    new Promise((resolve) => setTimeout(() => resolve(PENDING), ms)),
  ]);
  return settled === PENDING;
}

describe("isChunkLoadError", () => {
  it("tarayıcıların dinamik import ağ hatalarını ve ChunkLoadError adını tanır", () => {
    expect(isChunkLoadError(chromiumChunkError())).toBe(true);
    expect(isChunkLoadError(new TypeError("error loading dynamically imported module: /assets/x.js"))).toBe(true);
    expect(isChunkLoadError(new TypeError("Importing a module script failed."))).toBe(true);
    expect(isChunkLoadError(new Error("Unable to preload CSS for /assets/ReportsPage-abc.css"))).toBe(true);
    const named = new Error("parça yok");
    named.name = "ChunkLoadError";
    expect(isChunkLoadError(named)).toBe(true);
  });

  it("modül içi çalışma hatasını ve Error olmayan değerleri parça hatası saymaz", () => {
    expect(isChunkLoadError(new TypeError("Cannot read properties of undefined (reading 'map')"))).toBe(false);
    expect(isChunkLoadError("Failed to fetch dynamically imported module")).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});

describe("importWithReload (bayat parça → bir kez yenile)", () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    sessionStorage.clear();
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("başarılı yüklemede modülü döner, yenilemez ve eski bayrağı temizler", async () => {
    sessionStorage.setItem(CHUNK_RELOAD_FLAG, "2026-09-14T00:00:00.000Z");
    const reload = vi.fn();
    const mod = { default: () => null };

    await expect(importWithReload(() => Promise.resolve(mod), reload)).resolves.toBe(mod);

    expect(reload).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(CHUNK_RELOAD_FLAG)).toBeNull();
  });

  it("ilk parça hatasında bayrağı yazar, sayfayı TAM BİR kez yeniler ve söz askıda kalır", async () => {
    const reload = vi.fn();

    const promise = importWithReload(() => Promise.reject(chromiumChunkError()), reload);

    expect(await staysPending(promise)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem(CHUNK_RELOAD_FLAG)).not.toBeNull();
    expect(warnSpy).toHaveBeenCalledTimes(1);
  });

  it("yenilemeden sonra da yüklenemezse (bayrak var) İKİNCİ kez yenilemez, hatayı fırlatır", async () => {
    sessionStorage.setItem(CHUNK_RELOAD_FLAG, "2026-09-14T00:00:00.000Z");
    const reload = vi.fn();
    const error = chromiumChunkError();

    await expect(importWithReload(() => Promise.reject(error), reload)).rejects.toBe(error);

    expect(reload).not.toHaveBeenCalled();
    // Bayrak korunur: kullanıcı elle yenileyip parça yüklenince temizlenir.
    expect(sessionStorage.getItem(CHUNK_RELOAD_FLAG)).not.toBeNull();
  });

  it("art arda iki parça hatası (yenileme tamamlanmadan) yine tek yenileme üretir", async () => {
    const reload = vi.fn();

    const first = importWithReload(() => Promise.reject(chromiumChunkError()), reload);
    expect(await staysPending(first)).toBe(true);
    await expect(importWithReload(() => Promise.reject(chromiumChunkError()), reload)).rejects.toBeInstanceOf(TypeError);

    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("parça hatası OLMAYAN hatada (modül içi çalışma hatası) yenilemez, bayrak yazmaz", async () => {
    const reload = vi.fn();
    const error = new TypeError("Cannot read properties of undefined (reading 'map')");

    await expect(importWithReload(() => Promise.reject(error), reload)).rejects.toBe(error);

    expect(reload).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(CHUNK_RELOAD_FLAG)).toBeNull();
  });

  it("sessionStorage kapalıysa döngü engellenemeyeceği için yenilemez, hatayı fırlatır", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("storage kapalı", "SecurityError");
    });
    const reload = vi.fn();
    const error = chromiumChunkError();

    await expect(importWithReload(() => Promise.reject(error), reload)).rejects.toBe(error);

    expect(reload).not.toHaveBeenCalled();
  });
});

describe("React.lazy + importWithReload + Suspense", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;

  beforeEach(() => {
    sessionStorage.clear();
    vi.spyOn(console, "warn").mockImplementation(() => {});
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("bayat parçada sayfa yenilenir ve kullanıcı hata ekranı yerine yükleniyor göstergesinde kalır", async () => {
    const reload = vi.fn();
    const Page = lazy(() =>
      importWithReload<{ default: () => JSX.Element }>(() => Promise.reject(chromiumChunkError()), reload),
    );

    root = createRoot(container);
    await act(async () => {
      root!.render(
        <Suspense fallback={<span>Yükleniyor...</span>}>
          <Page />
        </Suspense>,
      );
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });

    expect(reload).toHaveBeenCalledTimes(1);
    expect(container.textContent).toBe("Yükleniyor...");
  });
});

// --- App.tsx kaynak bekçisi ------------------------------------------------

// jsdom ortamında global URL jsdom'unkidir; node'un fileURLToPath'ine string verilir.
const SRC_DIR = path.dirname(fileURLToPath(import.meta.url));
const APP_SOURCE = readFileSync(path.join(SRC_DIR, "App.tsx"), "utf8");
const API_SOURCE = readFileSync(path.join(SRC_DIR, "lib", "api.ts"), "utf8");
const STATIK_KALAN_SAYFALAR = new Set(["./pages/Login", "./pages/NotFound"]);

/** pages/ altındaki sayfa modülleri ("./pages/X" biçiminde), testler hariç. */
function sayfaModulleri(): string[] {
  const pagesDir = path.join(SRC_DIR, "pages");
  return readdirSync(pagesDir, { recursive: true, encoding: "utf8" })
    .filter((dosya) => dosya.endsWith(".tsx") && !dosya.includes(".test."))
    .map((dosya) => "./pages/" + dosya.replace(/\\/g, "/").replace(/\.tsx$/, ""))
    .sort();
}

describe("App.tsx route kod bölme bekçisi (G182)", () => {
  it("Login ve NotFound dışında hiçbir sayfa statik import edilmez", () => {
    const statikSayfalar = [...APP_SOURCE.matchAll(/^import\s+[\w{}\s,]+\s+from\s+"(\.\/pages\/[^"]+)";/gm)].map((m) => m[1]);
    expect(statikSayfalar.sort()).toEqual([...STATIK_KALAN_SAYFALAR].sort());
  });

  it("geri kalan her sayfa React.lazy + importWithReload ile yüklenir", () => {
    const beklenen = sayfaModulleri().filter((modul) => !STATIK_KALAN_SAYFALAR.has(modul));
    // 12 sayfa: dashboard'lar, iş sayfaları, /reports ve /admin.
    expect(beklenen).toHaveLength(12);
    const lazySayfalar = [
      ...APP_SOURCE.matchAll(/lazy\(\(\)\s*=>\s*importWithReload\(\(\)\s*=>\s*import\("(\.\/pages\/[^"]+)"\)\)\)/g),
    ].map((m) => m[1]);
    expect(lazySayfalar.sort()).toEqual(beklenen);
  });

  it("Routes tek bir Suspense ile sarılıdır", () => {
    expect(APP_SOURCE.match(/<Suspense\b/g)).toHaveLength(1);
    expect(APP_SOURCE).toMatch(/<Suspense fallback=\{<PageLoading \/>\}>\s*<Routes>/);
    expect(APP_SOURCE).toMatch(/<\/Routes>\s*<\/Suspense>/);
  });

  it("sonner dinamik import edilmez (App.tsx ve lib/api.ts statik import eder)", () => {
    for (const kaynak of [APP_SOURCE, API_SOURCE]) {
      expect(kaynak).not.toMatch(/import\(\s*["']sonner["']\s*\)/);
      expect(kaynak).toMatch(/^import \{ toast \} from "sonner";$/m);
    }
  });
});
