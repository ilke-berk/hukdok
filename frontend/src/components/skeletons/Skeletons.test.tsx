// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import {
  AppShellSkeleton,
  CardListSkeleton,
  DetailSkeleton,
  LineListSkeleton,
  PageSkeleton,
  TableSkeleton,
} from "./Skeletons";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SRC_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const ciz = (el: React.ReactElement) => act(() => root.render(el));

describe("skeleton kalıpları", () => {
  it.each([
    ["TableSkeleton", <TableSkeleton key="t" />],
    ["CardListSkeleton", <CardListSkeleton key="c" />],
    ["LineListSkeleton", <LineListSkeleton key="l" />],
    ["DetailSkeleton", <DetailSkeleton key="d" />],
    ["PageSkeleton", <PageSkeleton key="p" />],
    ["AppShellSkeleton", <AppShellSkeleton key="a" />],
  ])("%s: tek role=status, ekran okuyucuya 'Yükleniyor' der, spinner yok", (_ad, el) => {
    ciz(el);
    const durumlar = container.querySelectorAll("[role='status']");
    expect(durumlar).toHaveLength(1);
    expect(durumlar[0].getAttribute("aria-busy")).toBe("true");
    expect(container.querySelector(".sr-only")?.textContent).toBe("Yükleniyor…");
    expect(container.querySelector(".animate-spin")).toBeNull();
    // Bloklar dekoratif: hepsi aria-hidden
    const bloklar = container.querySelectorAll(".skeleton-block");
    expect(bloklar.length).toBeGreaterThan(0);
    bloklar.forEach((b) => expect(b.closest("[aria-hidden='true']")).not.toBeNull());
  });

  it("özel etiket sr-only metne yazılır", () => {
    ciz(<TableSkeleton label="Dosyalar yükleniyor…" />);
    expect(container.querySelector(".sr-only")?.textContent).toBe("Dosyalar yükleniyor…");
  });

  it("TableSkeleton: satır ve kolon sayısı parametreye uyar, başlık kapatılabilir", () => {
    ciz(<TableSkeleton rows={4} columns={3} />);
    const satirlar = container.querySelectorAll("[data-skeleton-row]");
    expect(satirlar).toHaveLength(4);
    satirlar.forEach((s) => expect(s.querySelectorAll(".skeleton-block")).toHaveLength(3));
    // başlık + 4 satır
    expect(container.querySelector("[data-testid='table-skeleton']")!.children).toHaveLength(5);

    ciz(<TableSkeleton rows={2} columns={3} header={false} />);
    expect(container.querySelector("[data-testid='table-skeleton']")!.children).toHaveLength(2);
  });

  it("bölge gecikmeli belirir (skeleton-region) — hızlı yanıtta yanıp sönme yok", () => {
    ciz(<CardListSkeleton />);
    expect(container.querySelector("[role='status']")!.classList.contains("skeleton-region")).toBe(true);
  });
});

describe("index.css bekçisi", () => {
  const css = readFileSync(path.join(SRC_DIR, "index.css"), "utf8");

  it("skeleton rengi tema token'ından türetilir (bg-sunken değil: editorial-koyuda saydam)", () => {
    expect(css).toMatch(/\.skeleton-block\s*\{[^}]*color-mix\(in srgb, var\(--fg, currentColor\)/);
  });

  it("hareketi azalt tercihinde nabız ve gecikmeli belirme durur", () => {
    const blok = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(blok).toMatch(/\.animate-pulse/);
    expect(blok).toMatch(/\.skeleton-region/);
    expect(blok).toMatch(/animation: none/);
  });
});

describe("kabuk içi Suspense bekçisi", () => {
  it("ShellLayout sayfa parçasını kendi Suspense'inde PageSkeleton ile bekler (menü yerinde kalır)", () => {
    const shell = readFileSync(path.join(SRC_DIR, "components/shell/Shell.tsx"), "utf8");
    expect(shell).toMatch(/<Suspense fallback=\{<PageSkeleton \/>\}>\s*<Outlet \/>\s*<\/Suspense>/);
  });
});
