// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  areDraftsSuppressed,
  attachUnloadGuard,
  createDraftStore,
  describeDraftAge,
  resumeAllDrafts,
  sessionDraftStorage,
  suppressAllDrafts,
} from "./formDraft";

interface Sample {
  name: string;
  count: number;
}

const KEY = "hukdok.test-draft.v1";
const HOUR = 60 * 60 * 1000;

const makeStore = (overrides: Partial<Parameters<typeof createDraftStore<Sample>>[0]> = {}) =>
  createDraftStore<Sample>({
    key: KEY,
    version: 1,
    maxAgeMs: 2 * HOUR,
    ...overrides,
  });

beforeEach(() => sessionStorage.clear());

describe("createDraftStore", () => {
  it("kaydedilen taslak yaşıyla birlikte geri okunur (round-trip)", () => {
    const store = makeStore();
    store.save({ name: "Ahmet", count: 2 }, 1_000_000);
    const loaded = store.load(1_000_000 + 5 * 60_000);
    expect(loaded?.data).toEqual({ name: "Ahmet", count: 2 });
    expect(loaded?.ageMs).toBe(5 * 60_000);
    expect(loaded?.savedAt.getTime()).toBe(1_000_000);
  });

  it("taslak yokken null döner", () => {
    expect(makeStore().load()).toBeNull();
  });

  it("bozuk JSON temizlenir ve null döner", () => {
    sessionStorage.setItem(KEY, "{bozuk");
    expect(makeStore().load()).toBeNull();
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("sürüm uyuşmazlığı temizlenir ve null döner", () => {
    makeStore({ version: 2 }).save({ name: "x", count: 1 });
    expect(makeStore({ version: 1 }).load()).toBeNull();
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("maxAgeMs'i aşan BAYAT taslak okunmaz ve silinir", () => {
    const store = makeStore({ maxAgeMs: HOUR });
    store.save({ name: "eski", count: 1 }, 0);
    expect(store.load(HOUR + 1)).toBeNull();
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("sınırın tam üstündeki taslak hâlâ okunur", () => {
    const store = makeStore({ maxAgeMs: HOUR });
    store.save({ name: "sinir", count: 1 }, 0);
    expect(store.load(HOUR)?.data.name).toBe("sinir");
  });

  it("isValid'i geçemeyen kayıt temizlenir", () => {
    const store = makeStore({ isValid: (d) => typeof (d as Sample)?.name === "string" });
    sessionStorage.setItem(
      KEY,
      JSON.stringify({ version: 1, savedAt: new Date().toISOString(), data: { count: 3 } }),
    );
    expect(store.load()).toBeNull();
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("clear taslağı siler", () => {
    const store = makeStore();
    store.save({ name: "a", count: 1 });
    store.clear();
    expect(store.load()).toBeNull();
  });

  it("saat geri alınmışsa yaş negatife düşmez", () => {
    const store = makeStore();
    store.save({ name: "gelecek", count: 1 }, 5_000_000);
    expect(store.load(4_000_000)?.ageMs).toBe(0);
  });

  it("depo erişimi patlasa bile akış kırılmaz", () => {
    const store = makeStore({
      storage: () => {
        throw new Error("storage engelli");
      },
    });
    expect(() => store.save({ name: "a", count: 1 })).not.toThrow();
    expect(store.load()).toBeNull();
    expect(() => store.clear()).not.toThrow();
  });

  it("null döndüren depo sağlayıcıda save/load sessizce boş geçer", () => {
    const store = makeStore({ storage: () => null });
    expect(() => store.save({ name: "a", count: 1 })).not.toThrow();
    expect(store.load()).toBeNull();
    expect(() => store.clear()).not.toThrow();
  });
});

describe("sessionDraftStorage", () => {
  it("jsdom'da sessionStorage döner", () => {
    expect(sessionDraftStorage()).toBe(window.sessionStorage);
  });
});

describe("describeDraftAge", () => {
  it.each([
    [0, "az önce"],
    [59_000, "az önce"],
    [60_000, "1 dakika önce"],
    [59 * 60_000, "59 dakika önce"],
    [HOUR, "1 saat önce"],
    [5 * HOUR, "5 saat önce"],
    [-1000, "az önce"],
  ])("%i ms → %s", (ms, expected) => {
    expect(describeDraftAge(ms)).toBe(expected);
  });
});

describe("attachUnloadGuard", () => {
  const fireUnload = () => {
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    return event;
  };

  it("active=false iken HİÇBİR dinleyici bağlanmaz (temiz formda uyarı yok)", () => {
    const flush = vi.fn();
    const detach = attachUnloadGuard(false, flush);
    const event = fireUnload();
    expect(event.defaultPrevented).toBe(false);
    expect(flush).not.toHaveBeenCalled();
    detach();
  });

  it("active=true iken uyarı tetiklenir ve bekleyen yazım flush edilir", () => {
    const flush = vi.fn();
    const detach = attachUnloadGuard(true, flush);
    const event = fireUnload();
    expect(event.defaultPrevented).toBe(true);
    expect(flush).toHaveBeenCalledTimes(1);
    detach();
  });

  it("sökme sonrası uyarı çıkmaz", () => {
    const flush = vi.fn();
    attachUnloadGuard(true, flush)();
    const event = fireUnload();
    expect(event.defaultPrevented).toBe(false);
    expect(flush).not.toHaveBeenCalled();
  });
});

// =====================================================================
// Logout bastırması (G004 denetim düzeltmesi — RET bulgusu).
// Senaryo: Sidebar Çıkış → suppressAllDrafts() → clearAppStorage() →
// logoutRedirect navigasyonu pagehide/beforeunload flush'larını tetikler.
// Bastırma olmadan bu flush'lar silinen TC'li taslağı GERİ yazardı.
// =====================================================================
describe("suppressAllDrafts (logout bastırması)", () => {
  const fireUnload = () => {
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    return event;
  };

  afterEach(() => resumeAllDrafts());

  it("bayrak kuruluyken save diske YAZMAZ — temizlenen taslak dirilmez", () => {
    const store = makeStore();
    store.save({ name: "önceki kullanıcı", count: 1 });
    expect(sessionStorage.getItem(KEY)).not.toBeNull();

    suppressAllDrafts();
    sessionStorage.clear(); // clearAppStorage'ın temizliğini temsil eder
    store.save({ name: "önceki kullanıcı", count: 1 }); // pagehide/unmount flush'ı
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("resumeAllDrafts yazımı geri açar (logout kurulamadı → oturum sürüyor)", () => {
    const store = makeStore();
    suppressAllDrafts();
    store.save({ name: "a", count: 1 });
    expect(sessionStorage.getItem(KEY)).toBeNull();

    resumeAllDrafts();
    store.save({ name: "a", count: 1 });
    expect(store.load()?.data.name).toBe("a");
  });

  it("bastırma clear'ı ENGELLEMEZ — silme her zaman güvenlidir", () => {
    const store = makeStore();
    store.save({ name: "a", count: 1 });
    suppressAllDrafts();
    store.clear();
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("areDraftsSuppressed bayrağın güncel durumunu yansıtır", () => {
    expect(areDraftsSuppressed()).toBe(false);
    suppressAllDrafts();
    expect(areDraftsSuppressed()).toBe(true);
    resumeAllDrafts();
    expect(areDraftsSuppressed()).toBe(false);
  });

  it("bastırma kuruluyken guard uyarı da flush da üretmez (diyalog logout'u bölmez)", () => {
    const flush = vi.fn();
    const detach = attachUnloadGuard(true, flush);
    suppressAllDrafts();
    const event = fireUnload();
    expect(event.defaultPrevented).toBe(false);
    expect(flush).not.toHaveBeenCalled();
    detach();
  });

  it("guard bayrağı OLAY ANINDA okur: resume sonrası aynı guard yeniden uyarır", () => {
    const flush = vi.fn();
    const detach = attachUnloadGuard(true, flush); // bağlanırken bayrak yok
    suppressAllDrafts();
    expect(fireUnload().defaultPrevented).toBe(false);

    resumeAllDrafts(); // Sidebar catch yolu: logout kurulamadı
    const event = fireUnload();
    expect(event.defaultPrevented).toBe(true);
    expect(flush).toHaveBeenCalledTimes(1);
    detach();
  });
});
