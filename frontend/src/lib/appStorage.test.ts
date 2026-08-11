// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import { appStorageKeys, clearAppStorage, isAppStorageKey } from "./appStorage";

// Uygulamada gerçekten kullanılan anahtarlar (kaynaklarıyla birlikte)
const APP_KEYS = [
  "hukudok-theme",                 // theme-provider
  "hukdok.dashboard.view",         // useDashboardView
  "hukudok-today-uploads",         // todayUploads
  "yetki_belgesi_avukat_cache",    // YetkiBelgesiModal (TC + sicil içerir)
  "hukdok.intake-draft.v1",        // intakeDraft
  "hukdok.newcase-draft.v1",       // newCaseDraft
  "hukdok.upload-flow-draft.v1",   // uploadFlowDraft
];

// Silinmemesi GEREKEN anahtarlar: MSAL kendi cache'ini yönetir, yabancı
// anahtarlar başka uygulama/eklenti verisidir.
const FOREIGN_KEYS = [
  "msal.account.keys",
  "msal.token.keys.6f1c2a3b-0000-4444-8888-abcdefabcdef",
  "6f1c2a3b-0000-4444-8888-abcdefabcdef.a1b2-login.windows.net-idtoken",
  "server-telemetry-6f1c2a3b",
  "baska-uygulama-oturumu",
  "theme",
];

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});

describe("isAppStorageKey", () => {
  it.each(APP_KEYS)("uygulama anahtarı tanınır: %s", (key) => {
    expect(isAppStorageKey(key)).toBe(true);
  });

  it.each(FOREIGN_KEYS)("yabancı/MSAL anahtarı kapsanmaz: %s", (key) => {
    expect(isAppStorageKey(key)).toBe(false);
  });
});

describe("appStorageKeys", () => {
  it("yalnız uygulama anahtarlarını listeler", () => {
    [...APP_KEYS, ...FOREIGN_KEYS].forEach((k) => sessionStorage.setItem(k, "1"));
    expect(appStorageKeys(sessionStorage).sort()).toEqual([...APP_KEYS].sort());
  });
});

describe("clearAppStorage", () => {
  it("iki depodaki uygulama anahtarlarını siler, diğerlerine dokunmaz", () => {
    APP_KEYS.forEach((k) => sessionStorage.setItem(k, "1"));
    FOREIGN_KEYS.forEach((k) => sessionStorage.setItem(k, "1"));
    APP_KEYS.forEach((k) => localStorage.setItem(k, "1"));
    FOREIGN_KEYS.forEach((k) => localStorage.setItem(k, "1"));

    const removed = clearAppStorage([sessionStorage, localStorage]);

    expect(removed).toHaveLength(APP_KEYS.length * 2);
    for (const storage of [sessionStorage, localStorage]) {
      APP_KEYS.forEach((k) => expect(storage.getItem(k)).toBeNull());
      FOREIGN_KEYS.forEach((k) => expect(storage.getItem(k)).toBe("1"));
    }
  });

  it("argümansız çağrıda window depolarını temizler", () => {
    sessionStorage.setItem("hukdok.newcase-draft.v1", "1");
    localStorage.setItem("hukudok-theme", "dark");
    localStorage.setItem("msal.account.keys", "[]");

    clearAppStorage();

    expect(sessionStorage.getItem("hukdok.newcase-draft.v1")).toBeNull();
    expect(localStorage.getItem("hukudok-theme")).toBeNull();
    expect(localStorage.getItem("msal.account.keys")).toBe("[]");
  });

  it("erişilemeyen depo diğerini engellemez", () => {
    localStorage.setItem("hukudok-theme", "dark");
    const broken = {
      get length(): number {
        throw new Error("erişim yok");
      },
      key: () => null,
      removeItem: () => undefined,
    } as unknown as Storage;

    expect(() => clearAppStorage([broken, localStorage])).not.toThrow();
    expect(localStorage.getItem("hukudok-theme")).toBeNull();
  });

  it("boş depoda sessizce boş liste döner", () => {
    expect(clearAppStorage([sessionStorage])).toEqual([]);
  });
});
