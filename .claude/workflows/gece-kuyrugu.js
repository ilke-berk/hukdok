export const meta = {
  name: "gece-kuyrugu",
  description:
    "gorevler/KUYRUK.md'deki isleri bant kurallariyla uygular (backend=ana dizin seri, frontend/docs=worktree, lexis=../lexis-rapor deposu seri), gorev-devam/gorev-denetle sozlesmeleriyle dogrular, KUYRUK'u isaretler, sabah raporu yazar. Push/ssh/deploy YAPMAZ.",
  whenToUse:
    "Gece kuyrugu kosusu (otomasyon/README.md v3 bolumu). KUYRUK.md'de acik ([ ]) ve BLOKE'siz gorev olmali. CLI kosucusu kuyruk-kosusu.ps1'in Workflow tabanli halefi (org ayari CLI erisimini kapatti, 2026-08-18).",
  phases: [
    { title: "Plan", detail: "on kontroller + KUYRUK.md + gorev dosyalari -> dalgalar" },
    { title: "Uygula", detail: "gorev-devam sozlesmesi + ilerleme-kapili dongu" },
    { title: "Teshis", detail: "takilan gorev icin TAZE baglamda kok neden" },
    { title: "Kapi", detail: "test butunlugu + kirmizi-yesil kaniti (mekanik)" },
    { title: "Denetle", detail: "temiz-context bagimsiz denetim (gorev-denetle sozlesmesi)" },
    { title: "Onar", detail: "RET icin tek onarim hakki + yeniden denetim" },
    { title: "Teslim", detail: "worktree merge + entegrasyon vitest + KUYRUK isaretleme" },
    { title: "Rapor", detail: "otomasyon/loglar/kuyruk-workflow_<tarih>.md" },
  ],
};

/* ==========================================================================
   HUKDOK GECE KUYRUGU - Workflow kosucusu (v3)

   Kaynak desen: design_handoff_kolayilan/.claude/workflows/gece-kuyrugu.js
   (PR+CI+otomatik-merge modeli). HUKDOK uyarlamasindaki BILINCLI farklar:

   1. TESLIM = YEREL. Push/PR/CI yok - bu projede push + deploy DAIMA insan
      karari (CLAUDE.md; Deploy #11'de agent push'u zaten sinifladirici
      tarafindan engellendi). Worktree dallari yerel merge edilir, KUYRUK.md
      isaretlenir; sabah inceleme + push + deploy kullanicida.
   2. BANT KURALLARI hukudok gercegi: backend gorevleri ANA DIZINDE ve SERI
      kosar (lokal konteyner ./backend'i override ile bind-mount eder; pytest
      yalniz ana dizindeki kodu dogru test eder - worktree'de backend testi
      YANLIS kodu test ederdi). frontend/docs gorevleri C:/dev/hukudok-wt
      altinda worktree'de kosar (OneDrive DISI - dosya kilidi/senkron riski).
   3. Gorev tanimi/sozlesme mevcut sistemin aynisi: KUYRUK.md satir formati,
      gorevler/gorev/<id>.md dosyalari, gorev-devam + gorev-denetle skill'leri.
      Planlayici (/plan-hazirla) degismedi.
   4. Kolayilan'dan ALINAN yeni yetenekler: ilerleme-kapili dongu (parmak izi),
      taze-baglamda teshis + yeniden deneme, mekanik Kapi (test butunlugu +
      kirmizi-yesil kaniti), RET'e tek onarim hakki + yeniden denetim,
      izin engellerinin olcumu, token butcesi tabani.

   ANA DIZIN MUTEX'i: ana dizine yazan/orada test kosturan her adim tek bir
   siradan (anaSira) gecer - backend gorev zinciri BUTUNUYLE, worktree
   gorevlerinin ise yalniz teslim (merge+vitest+KUYRUK) adimi. Iki ajan ayni
   anda ana dizine dokunamaz.

   LEXIS BANDI (07.10.2026, kullanici karari): dis depo ../lexis-rapor
   (LEXIS_KOK) icin dorduncu bant. Backend bandinin aynasi: worktree YOK,
   dal YOK (depo OneDrive altinda), dogrudan o deponun main'ine commit; testi
   HOST'ta `python -m pytest` + ruff (docker YOK - servis imaji testi test
   etmez). Kendi mutex'i (lexisSira) vardir: ayni anda tek lexis gorevi;
   HUKDOK bantlariyla paralel kosar. Gorev dosyasi (Rapor bolumu) HUKDOK
   deposundadir: isci onu YAZAR ama HUKDOK'ta commit ATMAZ; Teslim ajani
   KUYRUK + gorev dosyasini tek pathspec commit'iyle atar. Oturumun
   LEXIS_KOK dizinine yazma yetkisi olmali (uygulamanin dizin ekleme izni);
   yoksa her adim izin engeline takilir ve gorev BLOKE olur.
   ========================================================================== */

/* --------------------------- AYARLAR ------------------------------------ */

const TARIH = args?.tarih ?? "tarihsiz"; // Date.now() betikte yasak - her kosuda ver
const TAVAN = args?.tavan ?? 6;
const KURU = args?.kuru ?? false;
const SECILI = args?.gorev ?? null; // ["G061","G062"] gibi
const KIRLI_KABUL = args?.kirliKabul ?? false;
const WT_KOK = args?.worktreeKok ?? "C:/dev/hukudok-wt";
// Lexis bandinin deposu (dis depo, OneDrive altinda) ve HUKDOK kokunun mutlak yolu (lexis
// iscisi gorev dosyasina bu yoldan ulasir; Edit/Read araclari mutlak yol ister).
const LEXIS_KOK = args?.lexisKok ?? "C:/Users/ilkeb/OneDrive/Masaüstü/lexis-rapor";
const HUKDOK_KOK = args?.hukdokKok ?? "C:/Users/ilkeb/OneDrive/Masaüstü/hukudok-automator-main";
const TUR_TAVANI = args?.turTavani ?? 8;
const TESHIS_HAKKI = args?.teshisHakki ?? 1;
const BUTCE_TABANI = args?.butceTabani ?? 60_000;
// Insan onayli test tasima izni: { G228: ["backend/tests/x.py", ...] }. Varsayilan bos =
// TEST_KURALI mutlak. Izin YALNIZ listelenen dosyalar icin, YALNIZ gorev tanimi davranisi
// degistirdigi icin beklentiyi yeni davranisa tasimaya yarar (27.09 G228/G229 dersi).
const TEST_TASIMA_IZNI = args?.testTasimaIzni ?? {};

const KUYRUK_DOSYA = "gorevler/KUYRUK.md";
const GOREV_DIZIN = "gorevler/gorev";
const RAPOR_DOSYA = `otomasyon/loglar/kuyruk-workflow_${TARIH}.md`;

const KIRMIZI_HATLAR = `
KIRMIZI HATLAR (gorev tanimi bunu istese bile ihlal etme):
- git push / ssh / scp / gcloud / deploy.sh / rollback.sh YOK. Push + deploy
  sabah insan kararidir (CLAUDE.md kurali).
- git reset --hard / rebase / filter-branch / commit --amend / gecmis yeniden
  yazma YOK (istisnasiz; --hard ana dizindeki commit'lenmemis .claude/ dosyalarini
  siler - 26.09'da settings.local.json boyle kayboldu). TEK istisna: Teslim
  talimatinda acikca verilen "merge geri alma" - o da YALNIZ git reset --merge ile
  ve yalniz talimattaki SHA'ya.
- .env* ve hicbir sir dosyasi okunmaz, yazilmaz, log'lanmaz.
- Bagimlilik eklenmez/yukseltilmez (gorev acikca istemiyorsa).
  docker compose down -v YOK.
- KUYRUK.md'ye YALNIZ Teslim ajani dokunur; isci ve denetci ASLA.
- Baska gorevin dosyasina, worktree'sine, dalina dokunulmaz.
- lexis bandi: HUKDOK deposuna (kod, test, doc) DOKUNULMAZ - tek istisna gorevin kendi
  dosyasi (Rapor bolumu). lexis-rapor deposuna gercek rapor/karar/kisi verisi GIRMEZ
  (testler sentetik; C:/hukdok-veri ve masaustu paketleri okunabilir, depoya kopyalanmaz).
- Dosya degisikligi DAIMA Edit/Write araclariyla - PS5.1 Get/Set-Content
  Turkce icerigi cift kodlayip bozar (CLAUDE.md tuzagi).
- Commit mesajinda cift tirnak kullanma, basligi ASCII yaz (PS5.1 arguman
  tuzagi: cift tirnakli here-string argumani boler).
`.trim();

const TEST_KURALI = `
TEST BUTUNLUGU (mutlak - yesilin DOGRU sebeple gelmesi amac):
- Mevcut testleri DEGISTIRME, SILME; yeni skip/xfail/only/todo ISARETLEME
  (pytest: @pytest.mark.skip/skipif/xfail; vitest: .skip/.only/.todo).
- Beklentileri GEVSETME (kesin deger -> any/truthy, assert silme).
- backend/pyproject.toml [tool.pytest.ini_options] (testpaths/addopts/markers),
  lexis-rapor/pyproject.toml ayni bolumu ve tests/conftest.py'si,
  frontend vitest/eslint/tsc yapilandirmasi ZAYIFLATILMAZ.
- Hatayi susturma: # noqa, # type: ignore, @ts-ignore, eslint-disable YOK.
- Testi degistirmeden gecemiyorsan DEGISIKLIGIN kendisi yanlistir: DUR,
  durmaSebebi="test-degistirmek-gerekti" dondur. Bu basarisizlik degil,
  DOGRU davranistir. Yanlis kod, sahte yesilden iyidir.
- YENI test eklemek serbest ve beklenir; davranis degistiyse eski kodda
  BASARISIZ olacak test ekle (Kapi asamasi bunu mekanik dogrular).
`.trim();

/** Gorevin test kurali: izin yoksa TEST_KURALI aynen; varsa dar istisna eklenir. */
function testKurali(gorevId) {
  const izinli = TEST_TASIMA_IZNI[gorevId] ?? [];
  if (!izinli.length) return TEST_KURALI;
  return `${TEST_KURALI}

INSAN ONAYLI TEST TASIMA ISTISNASI (yalniz ${gorevId}):
- Asagidaki MEVCUT test dosyalarinda, gorev tanimi davranisi degistirdigi icin eskiyi
  sabitleyen beklentileri YENI davranisa tasiyabilirsin:
${izinli.map((d) => `    - ${d}`).join("\n")}
- Tasima = beklentiyi yeni davranisa CEVIRMEK (or. "kod eslesir" -> "kod artik eslesmez,
  sonuc None/422"). Test SILINMEZ, assert SAYISI AZALMAZ, beklenti GEVSETILMEZ,
  skip/xfail/only/todo EKLENMEZ. Listede OLMAYAN dosyada kural mutlak kalir.
- Her tasinan testi uygula raporunda "tasinanTestler" olarak ad + eski->yeni beklenti
  seklinde bir satirla bildir (denetci ve sabah incelemesi buna bakar).`;
}

/* --------------------------- SEMALAR ------------------------------------ */

const PLAN_SEMA = {
  type: "object",
  required: ["gorevler", "bittiIdler", "kirliDosyalar", "dockerCalisiyor"],
  properties: {
    gorevler: {
      type: "array",
      description: "YALNIZ acik ([ ]) ve BLOKE'siz satirlar",
      items: {
        type: "object",
        required: ["id", "baslik", "bant", "bagimli", "zatenTamam", "kabulVar"],
        properties: {
          id: { type: "string" },
          baslik: { type: "string" },
          bant: { type: "string", enum: ["backend", "frontend", "docs", "lexis"] },
          bagimli: { type: "array", items: { type: "string" } },
          zatenTamam: {
            type: "boolean",
            description:
              "gorev dosyasinin Rapor bolumunde 'Durum: TAMAM' yaziyor (is yapilmis ama KUYRUK isaretlenmemis)",
          },
          kabulVar: { type: "boolean" },
          dosya: { type: "array", items: { type: "string" } },
        },
      },
    },
    bittiIdler: {
      type: "array",
      items: { type: "string" },
      description: "KUYRUK'ta [x] olan TUM id'ler (bagimlilik cozumu icin)",
    },
    blokeIdler: { type: "array", items: { type: "string" } },
    kirliDosyalar: {
      type: "array",
      items: { type: "string" },
      description: "git status --porcelain'de .claude/ DISI kirli dosyalar",
    },
    lexisKirliDosyalar: {
      type: "array",
      items: { type: "string" },
      description: "lexis-rapor deposunda .claude/ DISI kirli dosyalar (depo yoksa bos + uyari)",
    },
    lexisDepoVar: { type: "boolean", description: "LEXIS_KOK bir git deposu olarak acildi" },
    dockerCalisiyor: { type: "boolean" },
    uyarilar: { type: "array", items: { type: "string" } },
  },
};

const UYGULA_SEMA = {
  type: "object",
  required: ["id", "basarili", "verifyDurumu", "turSayisi", "oncekiHead"],
  properties: {
    id: { type: "string" },
    basarili: { type: "boolean" },
    ozet: { type: "string", description: "En fazla 3 cumle. Dosya icerigi YAZMA." },
    verifyDurumu: {
      type: "string",
      enum: ["yesil", "kirmizi", "calistirilmadi", "test-yok"],
    },
    turSayisi: { type: "number" },
    durmaSebebi: {
      type: "string",
      enum: [
        "yesil",
        "ilerleme-yok",
        "tur-tavani",
        "test-degistirmek-gerekti",
        "kapsam-disi-gerekti",
        "ortam",
        "hata",
      ],
    },
    oncekiHead: {
      type: "string",
      description: "Ise baslamadan ONCEKI HEAD SHA'si (calisma alaninda)",
    },
    commitHash: { type: "string", description: "Atilan gorev commit'i (basariliysa)" },
    sonParmakIzi: { type: "string" },
    denenenYaklasimlar: { type: "array", items: { type: "string" } },
    degisenDosyalar: { type: "array", items: { type: "string" } },
    eklenenTestler: {
      type: "array",
      items: { type: "string" },
      description: "Yeni eklenen test DOSYALARI (yol) - Kapi kirmizi-yesil bunu kullanir",
    },
    kabulKarsilanmayan: { type: "array", items: { type: "string" } },
    izinEngelleri: {
      type: "array",
      items: { type: "string" },
      description: "Permission denied goren komutlar AYNEN - izin listesi bununla olculur",
    },
    notlar: { type: "string" },
  },
};

const TESHIS_SEMA = {
  type: "object",
  required: ["kokNeden", "yenidenDenenmeli", "yeniYaklasim"],
  properties: {
    kokNeden: { type: "string", description: "Tek paragraf. Semptom degil, sebep." },
    yenidenDenenmeli: { type: "boolean" },
    yeniYaklasim: { type: "string", description: "Onceki denemelerden FARKLI olmali" },
    gorevTanimiHatali: {
      type: "boolean",
      description: "true = sorun kodda degil kabul olcutunde; insan duzeltmeli",
    },
    insanaSoru: { type: "string" },
  },
};

const KAPI_SEMA = {
  type: "object",
  required: ["id", "gecti", "testButunlugu", "kirmiziYesil"],
  properties: {
    id: { type: "string" },
    gecti: { type: "boolean" },
    testButunlugu: { type: "string", enum: ["temiz", "ihlal"] },
    ihlaller: { type: "array", items: { type: "string" } },
    kirmiziYesil: {
      type: "string",
      enum: ["kanitlandi", "kanitlanamadi", "uygulanamaz"],
    },
    kirmiziYesilNotu: { type: "string" },
  },
};

const DENETIM_SEMA = {
  type: "object",
  required: ["id", "sonuc"],
  properties: {
    id: { type: "string" },
    sonuc: { type: "string", enum: ["GECTI", "RET"] },
    sebep: { type: "string", description: "RET ise tek cumle somut sebep" },
    bulgular: {
      type: "array",
      items: {
        type: "object",
        required: ["ciddiyet", "dosya", "iddia"],
        properties: {
          ciddiyet: { type: "string", enum: ["kritik", "yuksek", "orta", "dusuk"] },
          dosya: { type: "string" },
          satir: { type: "number" },
          iddia: { type: "string" },
          senaryo: { type: "string", description: "SOMUT girdi/durum -> yanlis cikti" },
        },
      },
    },
  },
};

const ONAR_SEMA = {
  type: "object",
  required: ["id", "basarili", "verifyDurumu"],
  properties: {
    id: { type: "string" },
    basarili: { type: "boolean" },
    verifyDurumu: { type: "string", enum: ["yesil", "kirmizi", "calistirilmadi"] },
    duzeltilen: { type: "array", items: { type: "string" } },
    duzeltilmeyen: {
      type: "array",
      items: {
        type: "object",
        required: ["iddia", "gerekce"],
        properties: { iddia: { type: "string" }, gerekce: { type: "string" } },
      },
    },
    commitHash: { type: "string" },
    notlar: { type: "string" },
  },
};

const TESLIM_SEMA = {
  type: "object",
  required: ["id", "islem"],
  properties: {
    id: { type: "string" },
    islem: { type: "string", enum: ["isaretlendi", "bloke", "yapilamadi"] },
    blokeSebebi: { type: "string" },
    mergeYapildi: { type: "boolean" },
    entegrasyonTesti: { type: "string", enum: ["yesil", "kirmizi", "uygulanamaz"] },
    worktreeTemizlendi: { type: "boolean" },
    kuyrukCommit: { type: "string" },
    hata: { type: "string" },
  },
};

/* --------------------------- YARDIMCILAR -------------------------------- */

const wt = (id) => `${WT_KOK}/${id}`;
const dal = (id) => `gorev/${id}`;

/** Ana dizin mutex'i: ana dizine yazan/orada test kosan isler tek tek. */
let anaSlot = Promise.resolve();
function anaSira(is) {
  const sonuc = anaSlot.then(is, is);
  anaSlot = sonuc.then(
    () => {},
    () => {},
  );
  return sonuc;
}

/** Lexis deposu mutex'i: ../lexis-rapor'a yazan/orada test kosan isler tek tek (anaSira'dan bagimsiz). */
let lexisSlot = Promise.resolve();
function lexisSira(is) {
  const sonuc = lexisSlot.then(is, is);
  lexisSlot = sonuc.then(
    () => {},
    () => {},
  );
  return sonuc;
}

/** Worktree'siz bantlar: dogrudan kendi deposunun main'ine commit'ler (merge/dal yok). */
const dogrudanBant = (gorev) => gorev.bant === "backend" || gorev.bant === "lexis";
/** Gorevin deposu (git -C icin): lexis bandi dis depo, gerisi HUKDOK ana dizini / worktree'si. */
const depoYolu = (gorev) => (gorev.bant === "lexis" ? LEXIS_KOK : gorev.bant === "backend" ? "." : wt(gorev.id));
/** Denetim/kapi araliginin sonu: dogrudan bantlarda gorev commit'i, worktree bantlarinda dal. */
const aralikSonu = (gorev, uygula) => (dogrudanBant(gorev) ? uygula.commitHash : dal(gorev.id));

/** Topolojik dalgalar. `harici` = kosu disinda bitmis sayilan id'ler. */
function dalgalaraBol(gorevler, harici) {
  const kalan = new Map(gorevler.map((g) => [g.id, g]));
  const bitti = new Set(harici);
  const dalgalar = [];
  while (kalan.size > 0) {
    const hazir = [...kalan.values()].filter((g) =>
      (g.bagimli ?? []).every((b) => bitti.has(b) || !kalan.has(b)),
    );
    // NOT: "!kalan.has(b)" = bagimlilik bu KOSUDA yok (tavan disi / BLOKE /
    // secim disi). Dalga SIRALAMASI icin saglanmis sayilir; gercek kontrol
    // kosu sirasinda doneSet ile yapilir (bagimliligi bu gece bitmeyen gorev
    // baslatilmaz, acik birakilir).
    if (hazir.length === 0)
      throw new Error(`Bagimlilik dongusu: ${[...kalan.keys()].join(", ")}`);
    dalgalar.push(hazir);
    for (const g of hazir) {
      kalan.delete(g.id);
      bitti.add(g.id);
    }
  }
  return dalgalar;
}

function bantDogrulama(gorev) {
  if (gorev.bant === "backend")
    return `Gorev dosyasinin "Dogrulama" bolumu esastir. Tipik (KONTEYNERDE):
  docker compose exec -T backend python -m pytest        (EKSTRA -q EKLEME - addopts zaten -q; -qq ozeti yutar)
  docker compose exec -T backend python -m ruff check .
  docker compose exec -T backend python -m mypy
Dev araclari konteynerde yoksa ONCE: docker compose exec -T backend pip install -r requirements-dev.txt
docker compose KULLANIMI SERBEST (ana dizindesin; konteyner ./backend'i bind-mount eder).`;
  if (gorev.bant === "frontend")
    return `Gorev dosyasinin "Dogrulama" bolumu esastir. Tipik (HOST'ta, worktree icinde):
  npm --prefix "${wt(gorev.id)}/frontend" test
  npm --prefix "${wt(gorev.id)}/frontend" run lint
  npx --prefix "${wt(gorev.id)}/frontend" tsc -b --force "${wt(gorev.id)}/frontend"
DIKKAT: ciplak "npx tsc --noEmit" SAHTEDIR (solution-style tsconfig, hicbir dosyayi
denetlemez) - daima yukaridaki -b --force bicimi.
docker compose KESINLIKLE YASAK: konteyner ANA dizini mount eder, senin worktree
kodunu test etmez; sonuc yanilticidir (gorev-denetle bunu bant ihlali sayar).`;
  if (gorev.bant === "lexis")
    return `Gorev dosyasinin "Dogrulama" bolumu esastir. Tipik (HOST'ta, lexis-rapor deposunda):
  cd "${LEXIS_KOK}" && PYTHONIOENCODING=utf-8 python -m pytest     (EKSTRA -q EKLEME - pyproject addopts zaten -q)
  cd "${LEXIS_KOK}" && python -m ruff check .
Veritabani isteyen testler SQLite ile kosar (tests/conftest.py LEXIS_DB_URL'i siler); Postgres'e
bagli (tsvector vb.) test varsa gorev dosyasi LEXIS_TEST_DB_URL'i verir, yoksa o testler skip
olur ve Rapor'da sayisi yazilir.
docker compose KESINLIKLE YASAK (lexis-rapor compose'u servis imajini kaldirir, host kodunu
test etmez; HUKDOK compose'u ise baska deponun isidir). HUKDOK konteynerlerine dokunma.`;
  return `docs bandi: test yok. Ic tutarlilik kontrolu yeterli (bozuk link, yanlis yol,
kod ile celisen iddia). Operasyonel iddialar KODDAN dogrulanir (CLAUDE.md ALTIN KURAL).`;
}

/* ==========================================================================
   1 - PLAN
   ========================================================================== */

phase("Plan");

const plan = await agent(
  `HUKDOK gece kuyrugu on kontrol + plan. HICBIR DOSYAYI DEGISTIRME (salt okuma + git/docker sorgulari).

1. ${KUYRUK_DOSYA} dosyasini oku. Satir formati:
     - [ ] Gnnn | bant:backend|frontend|docs | bagimli:-|Gxxx,Gyyy | Kisa baslik
   - [x] olanlarin TUM id'lerini bittiIdler[] icine yaz.
   - Satirinda "BLOKE" gecen acik gorevleri blokeIdler[] icine yaz - bunlar SECILMEZ.
   - Acik ([ ]) ve BLOKE'siz her gorev icin ${GOREV_DIZIN}/<id>.md dosyasini oku:
     * "Kabul kriterleri" bolumu dolu mu -> kabulVar
     * "Rapor" bolumunde "Durum: TAMAM" yaziyor mu -> zatenTamam=true
       (is ana oturumda yapilmis ama denetim+KUYRUK isareti eksik demektir)
     * "Dosya kapsami" yollarini dosya[] icine aktar (varsa)
   - Gorev dosyasi YOKSA gorevi dondurme; uyarilar[] icine "<id>: gorev dosyasi yok" yaz.
   - kabulVar=false olanlari da dondurme; uyarilar[] icine yaz.

2. git status --porcelain kos. ".claude/" ile baslayanlar ve "otomasyon/loglar/"
   altindakiler HARIC kirli dosyalari kirliDosyalar[] icine yaz.

2b. Lexis deposu: git -C "${LEXIS_KOK}" status --porcelain kos. Komut duserse (dizin yok /
   git deposu degil) lexisDepoVar=false + uyarilar[]'a yaz; yoksa lexisDepoVar=true ve
   ".claude/" disi kirli dosyalari lexisKirliDosyalar[] icine yaz. (Bu depoda SADECE
   okuma; dosya acma gerekmiyor.)

3. docker info kos -> calisiyorsa dockerCalisiyor=true. (docker compose up DENEME -
   yalniz durum tespiti; konteyneri gerekirse backend iscisi kaldirir.)

4. git log --oneline -3 ciktisindan HEAD'i uyarilar[]'a ekleme; sadece kendine not.

Yalnizca yapilandirilmis nesneyi dondur.`,
  { label: "planlayici", phase: "Plan", schema: PLAN_SEMA, effort: "low" },
);

if (!plan) return { durum: "plan-basarisiz" };
for (const u of plan.uyarilar ?? []) log(`uyari: ${u}`);

/* --- kapilar --- */

if (plan.kirliDosyalar?.length > 0 && !KIRLI_KABUL) {
  log(`Ana dizin kirli (${plan.kirliDosyalar.length} dosya) - kosu baslamiyor. ` +
      `Commit/stash et ya da kirliKabul:true ver (o zaman backend gorevleri ve merge'ler ertelenir).`);
  return { durum: "kirli-agac", kirliDosyalar: plan.kirliDosyalar };
}
const anaKirli = (plan.kirliDosyalar?.length ?? 0) > 0;

let secilenler = plan.gorevler ?? [];
if (SECILI) secilenler = secilenler.filter((g) => SECILI.includes(g.id));

if (anaKirli) {
  const ertelenenBackend = secilenler.filter((g) => g.bant === "backend" && !g.zatenTamam);
  if (ertelenenBackend.length)
    log(`kirliKabul: ana dizin kirli -> backend gorevleri ERTELENDI: ${ertelenenBackend.map((g) => g.id).join(", ")}`);
  secilenler = secilenler.filter((g) => g.bant !== "backend" || g.zatenTamam);
}

// Lexis bandi: depo yoksa ya da kirliyse (kirliKabul verilmedikce) o bantta uygulama yok;
// HUKDOK bantlari etkilenmez. zatenTamam gorevleri yalniz denetim+isaret oldugu icin gecer.
const lexisKirli = (plan.lexisKirliDosyalar?.length ?? 0) > 0;
if (plan.lexisDepoVar === false || (lexisKirli && !KIRLI_KABUL)) {
  const dusen = secilenler.filter((g) => g.bant === "lexis" && !g.zatenTamam);
  if (dusen.length)
    log(`lexis deposu ${plan.lexisDepoVar === false ? "acilamadi" : `kirli (${plan.lexisKirliDosyalar.length} dosya)`} -> lexis gorevleri ERTELENDI: ${dusen.map((g) => g.id).join(", ")}`);
  secilenler = secilenler.filter((g) => g.bant !== "lexis" || g.zatenTamam);
}

const backendVar = secilenler.some((g) => g.bant === "backend" && !g.zatenTamam);
if (backendVar && !plan.dockerCalisiyor) {
  const dusen = secilenler.filter((g) => g.bant === "backend" && !g.zatenTamam);
  log(`Docker calismiyor -> backend gorevleri bu kosuda ERTELENDI: ${dusen.map((g) => g.id).join(", ")}`);
  secilenler = secilenler.filter((g) => g.bant !== "backend" || g.zatenTamam);
}

const atlanan = secilenler.slice(TAVAN);
secilenler = secilenler.slice(0, TAVAN);
if (atlanan.length > 0)
  log(`TAVAN=${TAVAN}: atlandi -> ${atlanan.map((g) => g.id).join(", ")}`);

if (secilenler.length === 0) {
  log("Kosulacak gorev yok.");
  return { durum: "bos-kuyruk", uyarilar: plan.uyarilar ?? [] };
}

let dalgalar;
try {
  dalgalar = dalgalaraBol(secilenler, plan.bittiIdler ?? []);
} catch (e) {
  log(String(e?.message ?? e));
  return { durum: "bagimlilik-dongusu", hata: String(e?.message ?? e) };
}

log(
  `${secilenler.length} gorev, ${dalgalar.length} dalga: ` +
    dalgalar.map((d, i) => `D${i + 1}[${d.map((g) => g.id).join(" ")}]`).join(" "),
);

if (KURU) {
  return {
    durum: "kuru-kosu",
    dalgalar: dalgalar.map((d) =>
      d.map((g) => ({
        id: g.id,
        baslik: g.baslik,
        bant: g.bant,
        zatenTamam: g.zatenTamam,
        calismaAlani: g.bant === "backend" ? "(ana dizin)" : g.bant === "lexis" ? LEXIS_KOK : wt(g.id),
        dal: dogrudanBant(g) ? `main (dogrudan${g.bant === "lexis" ? ", lexis-rapor deposu" : ""})` : dal(g.id),
      })),
    ),
    atlanan: atlanan.map((g) => g.id),
    anaKirli,
    lexisDepoVar: plan.lexisDepoVar ?? null,
    lexisKirli,
    dockerCalisiyor: plan.dockerCalisiyor,
    uyarilar: plan.uyarilar ?? [],
  };
}

/* ==========================================================================
   2-7 - GOREV ZINCIRI
   ========================================================================== */

const doneSet = new Set(plan.bittiIdler ?? []);
const sonuclar = [];

/* --- Teslim yardimcisi: KUYRUK isaretleme / BLOKE / merge - DAIMA anaSira
       icinden cagrilir (cagiran garanti eder). --- */
async function teslimEt(gorev, mod, sebep) {
  const isaretleme = `KUYRUK ISARETLEME KURALLARI:
- ${KUYRUK_DOSYA} icinde "- [ ] ${gorev.id} |" ile baslayan SATIRI bul.
- ${mod === "tamam"
      ? `Satiri "- [x]" yap (Edit araciyla, satirin kalanina dokunma).`
      : `Satirin SONUNA " | BLOKE(${sebep})" ekle (Edit araciyla; satirda zaten BLOKE varsa dokunma).`}
- Baska HICBIR satira/dosyaya dokunma.
${gorev.bant === "lexis"
      ? `- lexis bandi: gorev dosyasi ${GOREV_DIZIN}/${gorev.id}.md HUKDOK'ta kirli durur (isci Rapor'u yazdi ama
  bu depoda commit atmadi - kod lexis-rapor deposundadir). Onu KUYRUK ile BIRLIKTE commit'le:
    git add ${GOREV_DIZIN}/${gorev.id}.md
    git commit -m 'chore: kuyruk durumu - ${gorev.id} ${mod === "tamam" ? "tamam" : "BLOKE"} (lexis)' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>' -- ${KUYRUK_DOSYA} ${GOREV_DIZIN}/${gorev.id}.md`
      : `- Commit'i PATHSPEC ile at (index'te baska sey olsa bile yalniz KUYRUK girer):
    git commit -m 'chore: kuyruk durumu - ${gorev.id} ${mod === "tamam" ? "tamam" : "BLOKE"}' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>' -- ${KUYRUK_DOSYA}`}
- kuyrukCommit alanina commit SHA'sini yaz.`;

  if (dogrudanBant(gorev) || gorev.zatenTamam || mod === "bloke") {
    // Merge yok: backend dogrudan main'e commit'ledi ya da gorev bloke.
    return agent(
      `TESLIM - gorev ${gorev.id} (${mod === "tamam" ? "isaretle" : "BLOKE isaretle"}).
Ana dizindesin (repo koku). Kod degistirme; yalniz asagidaki isaretleme.

${isaretleme}

${mod === "bloke" && !dogrudanBant(gorev) ? `Gorevin worktree'si/dali varsa (${wt(gorev.id)}, ${dal(gorev.id)}) DOKUNMA - sabah incelemesi icin korunur.` : ""}
${gorev.bant === "lexis" ? `lexis-rapor deposuna (${LEXIS_KOK}) DOKUNMA - oradaki commit/kirlilik sabah incelemesi icindir.` : ""}
islem alanini "${mod === "tamam" ? "isaretlendi" : "bloke"}" yap. Adim duserse islem="yapilamadi" + hata.`,
      { label: `teslim:${gorev.id}`, phase: "Teslim", schema: TESLIM_SEMA, effort: "low" },
    );
  }

  // frontend/docs TAMAM: yerel merge + (frontend) entegrasyon vitest + isaretleme.
  return agent(
    `TESLIM - gorev ${gorev.id} (${gorev.bant}): worktree dalini ana dala YEREL merge et.
Ana dizinde calis (repo koku). PUSH YOK.

0. git status --porcelain: ".claude/" ve "otomasyon/loglar/" DISINDA kirli dosya varsa
   MERGE YAPMA -> islem="bloke", blokeSebebi="ana dizin kirli - merge ertelendi",
   KUYRUK'a BLOKE isaretle (asagidaki kurallarla, sebep ayni) ve dur.
1. onceSha = git rev-parse HEAD  (kaydet - geri alma yalniz BU SHA'ya olabilir)
2. git merge --no-ff --no-edit ${dal(gorev.id)}
   Catisma cikarsa: git merge --abort -> islem="bloke",
   blokeSebebi="merge cakismasi - worktree ve dal korundu", KUYRUK'a BLOKE isaretle, dur.
${gorev.bant === "frontend"
      ? `3. ENTEGRASYON: npm --prefix frontend test   (ana dizinde, TAM paket)
   Kirmiziysa: dusen test dosyalarini BIR KEZ tekrar kos
   (npm --prefix frontend test -- <dosya yollari>). Tekrarda yesilse kararsiz test sayilir:
   merge KALIR, raporun "izlenecekler"ine dusen testin adini "KARARSIZ" diye yaz, 4. adima gec.
   Tekrarda da kirmiziysa: git reset --merge <onceSha>   (YALNIZ 1. adimda kaydettigin SHA;
   --hard ASLA - ana dizinde izin verilen .claude/ kirliligini siler, 26.09 dersi. --merge
   commit'lenmemis dosyaya dokunmaz, cakisirsa hata verir: o zaman DUR, islem="yapilamadi",
   hata="merge geri alinamadi - insan bakmali", baska reset DENEME) -> islem="bloke",
   blokeSebebi="entegrasyon testi kirmizi (<dusen test adi>) - merge geri alindi, worktree korundu",
   KUYRUK'a BLOKE isaretle, dur. entegrasyonTesti alanini doldur.`
      : `3. docs bandi: entegrasyon testi yok (entegrasyonTesti="uygulanamaz").`}
4. ${isaretleme.replace("KUYRUK ISARETLEME KURALLARI:", "KUYRUK ISARETLEME KURALLARI (mod: tamam):")}
5. TEMIZLIK (yalniz merge + isaret BASARILIYSA):
     git worktree remove "${wt(gorev.id)}"
     git branch -d ${dal(gorev.id)}
   Bloke yolunda worktree/dal KORUNUR.
islem="isaretlendi", mergeYapildi/worktreeTemizlendi alanlarini gercege gore doldur.
Adim duserse sonraki adimlara gecme; islem="yapilamadi" + hata.

${KIRMIZI_HATLAR}`,
    { label: `teslim:${gorev.id}`, phase: "Teslim", schema: TESLIM_SEMA, effort: "low" },
  );
}

/* --- Uygula prompt'u --- */
function uygulaPrompt(gorev, deneme, teshis) {
  const alan = gorev.bant === "backend" ? "(repo koku - ana dizin)" : gorev.bant === "lexis" ? LEXIS_KOK : wt(gorev.id);
  const gorevDosyasi = gorev.bant === "lexis" ? `${HUKDOK_KOK}/${GOREV_DIZIN}/${gorev.id}.md` : `${GOREV_DIZIN}/${gorev.id}.md`;
  const kurulum =
    gorev.bant === "lexis"
      ? `KURULUM (lexis - dis depo ../lexis-rapor, DOGRUDAN):
- Calisma alanin "${LEXIS_KOK}" deposudur (OneDrive altinda). Worktree YOK, dal YOK: dogrudan
  o deponun main'ine commit'lersin. Her git komutunu "git -C ${LEXIS_KOK} ..." ya da o dizine
  cd ederek kos; HUKDOK deposuna (${HUKDOK_KOK}) kod/test/doc YAZMA.
- ONCE "${LEXIS_KOK}/CLAUDE.md" dosyasini oku: o deponun kurallari (Write/Edit ile yazma,
  PYTHONIOENCODING=utf-8, kisi verisi depoya girmez, K-kararlari) burada da gecerlidir.
  "${LEXIS_KOK}/PLAN.md" yalniz gorev dosyasi isaret ederse acilir.
- git -C "${LEXIS_KOK}" status --porcelain: kirli dosya varsa gorev-devam 2. bolumu uygulanir
  (kapsam disi kirlilik = BLOKE).
- oncekiHead = git -C "${LEXIS_KOK}" rev-parse HEAD (semaya yaz).
- GOREV DOSYASI HUKDOK'TADIR: ${gorevDosyasi}. Rapor bolumunu ve DURUM satirini Edit ile oraya
  yazarsin ama HUKDOK'ta commit ATMAZSIN (Teslim ajani KUYRUK ile birlikte commit'ler). Kod
  commit'i YALNIZ lexis-rapor deposunda.`
      : gorev.bant === "backend"
      ? `KURULUM (backend - ana dizin):
- Calisma alanin repo kokudur. Worktree YOK, dal YOK: backend dogrudan main'e commit'ler
  (lokal konteyner ./backend'i bind-mount eder; pytest yalniz ana dizini dogru test eder).
- docker compose up -d kos; hazir bekle: "docker compose exec -T backend python -c 'print(1)'"
  basarili olana dek (5 sn arayla, en cok ~3 dk). Olmuyorsa durmaSebebi="ortam" ile dur.
- oncekiHead = git rev-parse HEAD (semaya yaz).`
      : `KURULUM (${gorev.bant} - worktree, KOSUCU ROLU):
- Once artik kontrolu: "${wt(gorev.id)}" dizini VARSA kurcalamadan dur:
  basarili=false, durmaSebebi="ortam", notlar="eski worktree duruyor - elle incele".
- git worktree add -b ${dal(gorev.id)} "${wt(gorev.id)}" HEAD
  (dal artigi yuzunden duserse: basarili=false, durmaSebebi="ortam", notlar'a yaz.)
${gorev.bant === "frontend" ? `- npm --prefix "${wt(gorev.id)}/frontend" ci   (birkac dakika surebilir)` : ""}
- oncekiHead = git -C "${wt(gorev.id)}" rev-parse HEAD (semaya yaz).
- Bundan sonra ISCI ROLUNDESIN ve TUM is "${wt(gorev.id)}" icinde. Ana dizine dokunma.
  (gorev-devam skill'indeki "git worktree yasak" kurali bu kurulumdan SONRASI icindir.)`;

  return `GOREV ${gorev.id}: ${gorev.baslik}${deneme > 1 ? `\n\n[YENIDEN DENEME ${deneme}]` : ""}
${teshis ? `\nONCEKI DENEMENIN KOK NEDENI (taze baglamda teshis edildi):\n${teshis.kokNeden}\n\nBU DEFA FARKLI YAKLASIM:\n${teshis.yeniYaklasim}\n` : ""}
HUKDOK gece kuyrugu iscisisin. Calisma alani: ${alan}

${kurulum}

ISCI SOZLESMESI:
.claude/skills/gorev-devam/SKILL.md dosyasini OKU ve harfiyen uygula, su uyarlamalarla:
- Skill'de "bulundugun dizin" gecen her yer = ${alan}.
- Son satir sentineli ("GOREV-SONUC: ...") YERINE bu cagridaki yapilandirilmis alanlari
  doldur (basarili/durmaSebebi/notlar). Skill'in istedigi gorev dosyasi Rapor bolumu
  ve DURUM satiri AYNEN yazilir.
- Gorev tanimi: ${gorevDosyasi} (hedef, kabul, dosya kapsami, dogrulama).
  "Dokunma" listesindeki dosya gerekirse DEGISIKLIK YAPMA -> durmaSebebi="kapsam-disi-gerekti",
  gorev dosyasina DURUM: BLOKE satirini yaz, dur.
${gorev.bant === "lexis" ? `- Skill'in "Kapat" bolumundeki "kod + gorev dosyasi TEK commit" kurali lexis bandinda
  "kod TEK commit (lexis-rapor'da), gorev dosyasi commit'siz (HUKDOK'ta kalir)" diye okunur.` : ""}

DOGRULAMA (bant: ${gorev.bant}):
${bantDogrulama(gorev)}

DONGU MUHENDISLIGI - dogrulama komutlari icin:
  Her turda:
    a. Kos. Yesilse DUR, basarili.
    b. Kirmiziysa hatanin PARMAK IZINI cikar (basarisiz test adlari + hata tipi + dosya).
    c. Parmak izi bir ONCEKI turla AYNIYSA ayni yoldan gidiyorsun: ya KOKTEN farkli
       yaklasim dene ya da DUR (durmaSebebi="ilerleme-yok").
    d. Parmak izi DEGISTIYSE ilerleme var, devam.
  Sert tavan: ${TUR_TAVANI} tur. 2 ayni imzada dur. denenenYaklasimlar[]'a her denemeyi
  bir satirla yaz.

${testKurali(gorev.id)}

${KIRMIZI_HATLAR}

IZIN ENGELLERI: bir komut "Permission ... denied" ile donerse:
- AYNI ISI BASKA YOLDAN dene (sed/awk yerine Edit; cat/head yerine Read). Cogu engel
  boyle asilir ve asilmasi GEREKIR - izin listesi bilerek dar.
- Kirmizi hatlardan birine denk geliyorsa (push, ssh, merge, reset) BASKA YOL ARAMA -
  o engel kasitlidir; dur ve rapor et.
- Iki durumda da engellenen komutu izinEngelleri[] icine AYNEN yaz (izin listesi
  olcerek genisletilecek - tek veri kaynagi bu).

GECICI DOSYA: $TMPDIR tanimsiz olabilir. Gecici cikti gerekiyorsa calisma alani ICINDE
git'e girmeyecek bir ad kullan (./.gk-tmp-${gorev.id}.log gibi; is bitince sil).

Kapat: gorev-devam'in "Kapat" bolumu aynen (Rapor bolumu + TEK commit, yalniz dokundugun
dosyalar, Co-Authored-By satiri, baslik ASCII). commitHash ve eklenenTestler[] alanlarini
doldur. Kabul olcutu karsilanamadiysa kabulKarsilanmayan[] + notlar. Sessizce atlama, uydurma.`;
}

/* --- Kapi prompt'u (mekanik) --- */
function kapiPrompt(gorev, uygula) {
  const aralik = `${uygula.oncekiHead}..${aralikSonu(gorev, uygula)}`;
  const lexisKanit = `KANIT DUZENEGI (lexis - dis depo, HOST python):
  git -C "${LEXIS_KOK}" worktree add "${WT_KOK}/kanit-${gorev.id}" ${uygula.oncekiHead}
  git -C "${WT_KOK}/kanit-${gorev.id}" checkout ${uygula.commitHash} -- <eklenen test dosyalari>
  cd "${WT_KOK}/kanit-${gorev.id}" && PYTHONIOENCODING=utf-8 python -m pytest -o addopts='' <test yollari>
  (Bagimliliklar host Python'unda zaten kurulu - lexis bandinin dogrulamasi da orada kosar.)
  BEKLENEN: en az bir test FAIL (kirmizi) -> "kanitlandi". Hepsi PASS -> "kanitlanamadi", gecti=false.
  Hepsi SKIP / import hatasi (yeni modul eski kodda yok -> ImportError de KIRMIZIDIR, kanitlandi sayilir;
  yalniz toplama disi SKIP "uygulanamaz"dir) -> kirmiziYesilNotu'na yaz.
  TEMIZLIK: git -C "${LEXIS_KOK}" worktree remove --force "${WT_KOK}/kanit-${gorev.id}"`;
  const backendKanit = `KANIT DUZENEGI (backend):
  git worktree add "${WT_KOK}/kanit-${gorev.id}" ${uygula.oncekiHead}
  git -C "${WT_KOK}/kanit-${gorev.id}" checkout ${uygula.commitHash} -- <eklenen test dosyalari>
  Imaj adini ogren: docker compose images backend  (Repository:Tag sutunu)
  docker run --rm -v "${WT_KOK}/kanit-${gorev.id}/backend:/app" --entrypoint bash <imaj> \\
    -c "pip install -q -r requirements-dev.txt && python -m pytest -o addopts='' <backend-goreli test yollari>"
  (DATABASE_URL YOK - gercek DB isteyen testler 3-ortam kurali gieregi SKIP olur.)
  BEKLENEN: en az bir test FAIL (kirmizi) -> kirmiziYesil="kanitlandi".
  Hepsi PASS ise test yeni davranisi olcmuyor -> "kanitlanamadi", gecti=false.
  Hepsi SKIP ise altyapi kaniti veremiyor -> "uygulanamaz" + kirmiziYesilNotu (RET sebebi DEGIL).
  pip/imaj/docker duserse -> "uygulanamaz" + not (altyapi hatasi RET sebebi degil).
  TEMIZLIK: git worktree remove --force "${WT_KOK}/kanit-${gorev.id}"`;
  const frontendKanit = `KANIT DUZENEGI (frontend):
  git worktree add "${WT_KOK}/kanit-${gorev.id}" ${uygula.oncekiHead}
  npm --prefix "${WT_KOK}/kanit-${gorev.id}/frontend" ci
  git -C "${WT_KOK}/kanit-${gorev.id}" checkout ${dal(gorev.id)} -- <eklenen test dosyalari>
  cd "${WT_KOK}/kanit-${gorev.id}/frontend" && npx vitest run <o test dosyalari>
  BEKLENEN: FAIL (kirmizi) -> "kanitlandi". PASS -> "kanitlanamadi", gecti=false.
  Altyapi duserse -> "uygulanamaz" + not.
  TEMIZLIK: git worktree remove --force "${WT_KOK}/kanit-${gorev.id}"`;

  return `KAPI - gorev ${gorev.id}. MEKANIK kontrol, yorum degil. Gorev dosyalarina DOKUNMA.

## 1) TEST BUTUNLUGU
Diff'i incele: git ${gorev.bant === "lexis" ? `-C "${LEXIS_KOK}" ` : ""}diff ${aralik}
IHLAL sayilanlar (her birini ihlaller[] icine yaz):
${gorev.bant === "frontend"
      ? `- Silinen test dosyasi; net azalan "expect(" sayisi (silinen > eklenen)
- Yeni .skip( / .only( / .todo( / xit( / xdescribe(
- Gevsetilen beklenti (kesin deger -> truthy/any/stringContaining)
- vitest.config include daraltilmis / exclude genisletilmis; package.json test/lint zayiflatilmis
- Kaynakta yeni @ts-ignore / @ts-expect-error / eslint-disable`
      : `- Silinen test dosyasi; net azalan "def test_" veya "assert" sayisi (silinen > eklenen)
- Yeni @pytest.mark.skip / skipif / xfail (yeni eklenen isaretler${gorev.bant === "lexis" ? "; lexis'te Postgres'e bagli testin SQLite'ta skipif'i YALNIZ gorev dosyasi acikca izin verdiyse ve yalniz o testlerde" : ""})
- ${gorev.bant === "lexis" ? "lexis-rapor/pyproject.toml" : "backend/pyproject.toml"} [tool.pytest.ini_options] degisikligi (testpaths/addopts/markers)
- conftest.py'de yeni collect_ignore / toplama daraltmasi
- Kaynakta yeni "# noqa" / "# type: ignore"`}
${(TEST_TASIMA_IZNI[gorev.id] ?? []).length
      ? `INSAN ONAYLI ISTISNA: su dosyalardaki beklenti DEGISIKLIGI ihlal degildir (yeni davranisa
tasima): ${TEST_TASIMA_IZNI[gorev.id].join(", ")}. Bu dosyalarda da silme / net azalma /
gevsetme / skip YINE ihlaldir; listede olmayan dosyada her degisiklik ihlaldir.`
      : ""}
Bir tanesi bile varsa testButunlugu="ihlal", gecti=false.
(docs bandinda bu bolum genelde bos diff'tir - testButunlugu="temiz".)

## 2) KIRMIZI-YESIL KANITI
Eklenen test dosyasi: ${(uygula.eklenenTestler ?? []).join(", ") || "(yok)"}
Yoksa: kirmiziYesil="uygulanamaz" (yalniz yapilandirma/dokuman goreviyse normaldir).
Varsa amac: eklenen testin ESKI kodda BASARISIZ oldugunu kanitlamak.
${gorev.bant === "frontend" ? frontendKanit : gorev.bant === "backend" ? backendKanit : gorev.bant === "lexis" ? lexisKanit : 'docs bandi: kirmiziYesil="uygulanamaz".'}

## SONUC
gecti = (testButunlugu=="temiz") VE (kirmiziYesil != "kanitlanamadi")
Gorev dalina / calisma alanina dokunma. ${KIRMIZI_HATLAR}`;
}

/* --- Denetim prompt'u --- */
function denetimPrompt(gorev, ctx) {
  return `DENETIM - gorev ${gorev.id}. Sen kodu yazan oturum DEGILSIN; isin itiraz etmek.

.claude/skills/gorev-denetle/SKILL.md dosyasini OKU ve harfiyen uygula, su uyarlamalarla:
- Calisma dizini: ${gorev.bant === "lexis" ? `"${LEXIS_KOK}" (dis depo; git komutlari "git -C" ile; bant kurallari: docker compose YASAK, HOST'ta PYTHONIOENCODING=utf-8 python -m pytest + ruff). Gorev dosyasi HUKDOK'ta: ${HUKDOK_KOK}/${GOREV_DIZIN}/${gorev.id}.md (isci Rapor'u yazdi, HUKDOK'ta commit beklenmez; "kapsam sizmasi" kontrolu lexis-rapor commit'inin diff'ine bakar). O deponun CLAUDE.md kurallari (kisi verisi, K-kararlari) denetim olcutudur.` : gorev.bant === "backend" || gorev.zatenTamam ? "repo koku (ana dizin)" : `"${wt(gorev.id)}" worktree'si (bant kurallari: docker compose YASAK, vitest worktree icinde)`}.
- Son satir sentineli YERINE yapilandirilmis cikti: sonuc="GECTI"|"RET" + sebep + bulgular[].
- Denetlenecek commit: ${ctx.commitAciklama}
${ctx.kapi && ctx.kapi.gecti === false ? `- BILGI: mekanik Kapi kirmizi cikti (${(ctx.kapi.ihlaller ?? []).join("; ") || ctx.kapi.kirmiziYesil}). Bunu dogrula ve degerlendir.` : ""}
- Bulgulari RET esigine tasimadan once gorev-denetle kurali: uslup/zevk RET sebebi DEGIL;
  yalniz gercek eksik/yanlis (kriter karsilanmamis, test kirmizi/silinmis/hileli,
  kapsam-bant ihlali, commit yok) RET'tir. Bulgulara SOMUT senaryo yaz.

Kod DEGISTIRME, commit atma, KUYRUK'a dokunma.`;
}

/* --- Tek gorevin tam zinciri (uygula->teshis->kapi->denetle->onar->teslim). --- */
async function zincirGovde(gorev) {
  const kayit = { gorev, teshisler: [] };

  // Bagimlilik runtime kontrolu: bu gece bitmeyen bagimlilik = gorev acik kalir.
  const eksikDep = (gorev.bagimli ?? []).filter((b) => !doneSet.has(b));
  if (eksikDep.length > 0) {
    kayit.atlandi = `bagimlilik bu kosuda tamamlanmadi: ${eksikDep.join(", ")}`;
    log(`${gorev.id} atlandi (${kayit.atlandi}) - KUYRUK'ta acik birakildi`);
    return kayit;
  }

  if (budget.total && budget.remaining() < BUTCE_TABANI) {
    kayit.atlandi = "butce tabani";
    log(`${gorev.id} atlandi (butce tabani) - KUYRUK'ta acik birakildi`);
    return kayit;
  }

  /* --- zatenTamam kisayolu: is yapilmis (ana oturum), denetim + isaret eksik --- */
  if (gorev.zatenTamam) {
    log(`${gorev.id}: gorev dosyasi "Durum: TAMAM" diyor - dogrudan denetime gidiyor`);
    const denetim = await agent(
      denetimPrompt(gorev, {
        commitAciklama: `git ${gorev.bant === "lexis" ? `-C "${LEXIS_KOK}" ` : ""}log --oneline -30 icinde mesajinda "${gorev.id}" gecen ILK commit'i bul ve onu denetle (HEAD olmayabilir - kuyruk chore commit'leri arada olabilir). Bulamazsan RET: "${gorev.id} icin commit bulunamadi".`,
      }),
      { label: `denetle:${gorev.id}`, phase: "Denetle", schema: DENETIM_SEMA, effort: "high" },
    );
    kayit.denetim = denetim;
    if (denetim?.sonuc === "GECTI") {
      kayit.teslim = await teslimEt(gorev, "tamam");
      if (kayit.teslim?.islem === "isaretlendi") doneSet.add(gorev.id);
    } else {
      kayit.teslim = await teslimEt(gorev, "bloke", `denetim RET: ${denetim?.sebep ?? "sonuc alinamadi"}`);
    }
    return kayit;
  }

  /* --- 1: UYGULA (+ taze-baglam teshis dongusu) --- */
  let uygula = await agent(uygulaPrompt(gorev, 1, null), {
    label: `uygula:${gorev.id}`,
    phase: "Uygula",
    schema: UYGULA_SEMA,
  });

  for (let h = 0; h < TESHIS_HAKKI; h++) {
    if (uygula?.basarili && uygula.verifyDurumu !== "kirmizi") break;
    if (uygula?.durmaSebebi === "test-degistirmek-gerekti") break; // dogru durus
    if (uygula?.durmaSebebi === "kapsam-disi-gerekti") break; // planlayici isi
    if (uygula?.durmaSebebi === "ortam") break; // teshisin cozecegi sey degil

    const teshis = await agent(
      `TESHIS - gorev ${gorev.id} takildi. TAZE bakis gerekiyor. HICBIR SEYI DEGISTIRME.

Uygulama denemesinin raporu:
- durma sebebi: ${uygula?.durmaSebebi ?? "bilinmiyor"} · tur: ${uygula?.turSayisi ?? "?"}
- son parmak izi: ${uygula?.sonParmakIzi ?? "(yok)"}
- denenen yaklasimlar:
${(uygula?.denenenYaklasimlar ?? []).map((y) => `  - ${y}`).join("\n") || "  (bildirilmedi)"}

Calisma alani: ${gorev.bant === "backend" ? "ana dizin" : gorev.bant === "lexis" ? LEXIS_KOK : wt(gorev.id)} (dokunma, incele).
Dogrulama komutlarini kosabilirsin (bant kurallarina uyarak - ${gorev.bant}).
Gorev tanimi: ${gorev.bant === "lexis" ? `${HUKDOK_KOK}/` : ""}${GOREV_DIZIN}/${gorev.id}.md

SORULAR:
1. Kok neden ne? (semptom degil sebep)
2. Denenenlerden KOKTEN farkli, makul bir yol var mi?
3. Sorun gorev TANIMINDA olabilir mi (kabul olcutu celiskili/eksik/uygulanamaz)?
   Oyleyse gorevTanimiHatali=true + insanaSoru doldur - bu, yanlis kod yazmaktan
   cok daha degerli bir cikti.`,
      { label: `teshis:${gorev.id}`, phase: "Teshis", schema: TESHIS_SEMA, effort: "high" },
    );
    kayit.teshisler.push(teshis);
    if (!teshis?.yenidenDenenmeli || teshis?.gorevTanimiHatali) break;

    uygula = await agent(uygulaPrompt(gorev, h + 2, teshis), {
      label: `uygula:${gorev.id}:d${h + 2}`,
      phase: "Uygula",
      schema: UYGULA_SEMA,
    });
  }
  kayit.uygula = uygula;

  if (!uygula?.basarili || uygula.verifyDurumu === "kirmizi" || !uygula.commitHash) {
    const sebep =
      uygula?.durmaSebebi === "test-degistirmek-gerekti"
        ? "testi degistirmeden gecilemedi - gorev tanimi gozden gecirilmeli"
        : uygula?.durmaSebebi === "kapsam-disi-gerekti"
          ? "kapsam disi dosya gerekti - gorev dosyasindaki DURUM satirina bak"
          : `uygulama yesillenmedi (${uygula?.durmaSebebi ?? "sonuc alinamadi"})`;
    kayit.teslim = gorev.bant === "backend"
      ? await teslimEt(gorev, "bloke", sebep)
      : await anaSira(() => teslimEt(gorev, "bloke", sebep));
    return kayit;
  }
  // NOT: backend zinciri zaten anaSira icindedir, teslimi dogrudan cagirir; lexis dahil diger
  // bantlar KUYRUK'a (HUKDOK ana dizini) yazdigi icin teslimi anaSira'ya sokar.

  /* --- 2: KAPI (mekanik) --- */
  const kapi = await agent(kapiPrompt(gorev, uygula), {
    label: `kapi:${gorev.id}`,
    phase: "Kapi",
    schema: KAPI_SEMA,
    effort: "high",
  });
  kayit.kapi = kapi;

  if (kapi && kapi.gecti === false) {
    const sebep =
      kapi.testButunlugu === "ihlal"
        ? `KAPI: test butunlugu ihlali (${(kapi.ihlaller ?? []).slice(0, 2).join("; ")})`
        : "KAPI: kirmizi-yesil kanitlanamadi (eklenen test eski kodda da geciyor)";
    kayit.teslim = gorev.bant === "backend"
      ? await teslimEt(gorev, "bloke", sebep)
      : await anaSira(() => teslimEt(gorev, "bloke", sebep));
    return kayit;
  }

  /* --- 3: DENETLE --- */
  const commitAciklama = `${uygula.commitHash}${kayit.onar?.commitHash ? " + onarim commit'i" : ""} (aralik: ${uygula.oncekiHead}..${aralikSonu(gorev, uygula)}${gorev.bant === "lexis" ? ", lexis-rapor deposunda" : ""})`;
  let denetim = await agent(denetimPrompt(gorev, { commitAciklama, kapi }), {
    label: `denetle:${gorev.id}`,
    phase: "Denetle",
    schema: DENETIM_SEMA,
    effort: "high",
  });
  kayit.denetim = denetim;

  /* --- 4: ONAR (tek hak) + yeniden denetim --- */
  if (denetim && denetim.sonuc === "RET") {
    const ciddi = (denetim.bulgular ?? []).filter(
      (b) => b.ciddiyet === "kritik" || b.ciddiyet === "yuksek",
    );
    const onar = await agent(
      `ONARIM - gorev ${gorev.id}. Calisma alani: ${gorev.bant === "backend" ? "ana dizin" : gorev.bant === "lexis" ? `"${LEXIS_KOK}" (dis depo; commit ORADA, HUKDOK'a dokunma; gorev dosyasi ${HUKDOK_KOK}/${GOREV_DIZIN}/${gorev.id}.md - Rapor'a onarim notu ekle, commit'leme)` : `"${wt(gorev.id)}" (worktree ZATEN VAR, yeni acma)`}.

Denetim RET verdi: ${denetim.sebep ?? "(sebep yok)"}
${ciddi.length ? `CIDDI BULGULAR:\n${ciddi.map((b, i) => `${i + 1}. [${b.ciddiyet}] ${b.dosya}${b.satir ? ":" + b.satir : ""} - ${b.iddia}\n   Senaryo: ${b.senaryo ?? "(yok)"}`).join("\n")}` : ""}

Her bulguyu ONCE DOGRULA - denetci yanilmis olabilir; iddia gercek degilse DUZELTME,
duzeltilmeyen[] icine gerekcesiyle yaz (sahte bulguyu "duzeltmek" calisan kodu bozar).
Gercek olanlari duzelt; dogrulama komutlarini yesillet (ayni dongu muhendisligi:
parmak izi tekrarliyorsa dur).

DOGRULAMA (bant: ${gorev.bant}):
${bantDogrulama(gorev)}

Commit: 'fix: denetim bulgulari giderildi (${gorev.id})' + Co-Authored-By satiri;
yalniz dokundugun dosyalar. commitHash'i doldur.

${testKurali(gorev.id)}

${KIRMIZI_HATLAR}`,
      { label: `onar:${gorev.id}`, phase: "Onar", schema: ONAR_SEMA },
    );
    kayit.onar = onar;

    if (onar?.basarili && onar.verifyDurumu === "yesil") {
      denetim = await agent(
        denetimPrompt(gorev, {
          commitAciklama: `${uygula.commitHash} + onarim ${onar.commitHash ?? ""} (aralik: ${uygula.oncekiHead}..${dogrudanBant(gorev) ? "HEAD" : dal(gorev.id)}${gorev.bant === "lexis" ? ", lexis-rapor deposunda" : ""})`,
        }),
        { label: `denetle2:${gorev.id}`, phase: "Denetle", schema: DENETIM_SEMA, effort: "high" },
      );
      kayit.denetim2 = denetim;
    }
  }

  /* --- 5: TESLIM --- */
  if (denetim?.sonuc === "GECTI") {
    kayit.teslim = gorev.bant === "backend"
      ? await teslimEt(gorev, "tamam")
      : await anaSira(() => teslimEt(gorev, "tamam"));
    if (kayit.teslim?.islem === "isaretlendi") doneSet.add(gorev.id);
  } else {
    const sebep = `denetim RET: ${denetim?.sebep ?? "sonuc alinamadi"}`;
    kayit.teslim = gorev.bant === "backend"
      ? await teslimEt(gorev, "bloke", sebep)
      : await anaSira(() => teslimEt(gorev, "bloke", sebep));
  }
  return kayit;
}

/** Backend zinciri BUTUNUYLE ana dizin mutex'inde; worktree bantlari serbest
    (yalniz teslim adimlari kendi icinde anaSira'ya girer). */
function gorevKos(gorev) {
  if (gorev.bant === "lexis" && !gorev.zatenTamam) return lexisSira(() => zincirGovde(gorev));
  if (gorev.bant === "backend" || gorev.zatenTamam) return anaSira(() => zincirGovde(gorev));
  return zincirGovde(gorev);
}

async function bantKos(bantGorevleri) {
  const out = [];
  for (const g of bantGorevleri) {
    try {
      out.push(await gorevKos(g));
    } catch (e) {
      out.push({ gorev: g, hata: String(e?.message ?? e) });
      log(`${g.id} zincir hatasi: ${String(e?.message ?? e)}`);
    }
  }
  return out;
}

for (let d = 0; d < dalgalar.length; d++) {
  if (budget.total && budget.remaining() < BUTCE_TABANI) {
    log(`Butce tabani (${BUTCE_TABANI}) - kalan dalgalar baslatilmiyor.`);
    break;
  }
  const dalga = dalgalar[d];
  log(`--- Dalga ${d + 1}/${dalgalar.length}: ${dalga.map((g) => g.id).join(" ")} ---`);

  const gruplar = { backend: [], frontend: [], docs: [] };
  for (const g of dalga) gruplar[g.bant].push(g);

  const dalgaSonuc = await parallel([
    () => bantKos(gruplar.backend),
    () => bantKos(gruplar.frontend),
    () => bantKos(gruplar.docs),
  ]);
  sonuclar.push(...dalgaSonuc.filter(Boolean).flat().filter(Boolean));
}

/* ==========================================================================
   8 - RAPOR
   ========================================================================== */

phase("Rapor");

const ozet = sonuclar.map((s) => ({
  id: s.gorev.id,
  baslik: s.gorev.baslik,
  bant: s.gorev.bant,
  zatenTamam: s.gorev.zatenTamam ?? false,
  atlandi: s.atlandi ?? null,
  zincirHatasi: s.hata ?? null,
  uygulandi: s.uygula?.basarili ?? (s.gorev.zatenTamam ? true : false),
  verify: s.uygula?.verifyDurumu ?? null,
  turSayisi: s.uygula?.turSayisi ?? 0,
  durmaSebebi: s.uygula?.durmaSebebi ?? null,
  sonParmakIzi: s.uygula?.sonParmakIzi ?? null,
  denenenYaklasimlar: s.uygula?.denenenYaklasimlar ?? [],
  commit: s.uygula?.commitHash ?? null,
  teshis: (s.teshisler ?? []).map((t) => ({
    kokNeden: t?.kokNeden ?? null,
    gorevTanimiHatali: t?.gorevTanimiHatali ?? false,
    insanaSoru: t?.insanaSoru ?? null,
  })),
  kapi: s.kapi
    ? {
        gecti: s.kapi.gecti,
        test: s.kapi.testButunlugu,
        kirmiziYesil: s.kapi.kirmiziYesil,
        ihlaller: s.kapi.ihlaller ?? [],
      }
    : null,
  denetim: s.denetim ? { sonuc: s.denetim.sonuc, sebep: s.denetim.sebep ?? null, bulgu: (s.denetim.bulgular ?? []).length } : null,
  denetim2: s.denetim2 ? { sonuc: s.denetim2.sonuc, sebep: s.denetim2.sebep ?? null } : null,
  onar: s.onar
    ? { basarili: s.onar.basarili, duzeltilen: (s.onar.duzeltilen ?? []).length, duzeltilmeyen: s.onar.duzeltilmeyen ?? [] }
    : null,
  kabulKarsilanmayan: s.uygula?.kabulKarsilanmayan ?? [],
  izinEngelleri: s.uygula?.izinEngelleri ?? [],
  notlar: s.uygula?.notlar ?? null,
  /* MEKANIK OLGULAR - ajan beyani degil, betigin bildigi (kolayilan dersi:
     ajan notlari yazildigi anda dogru, rapor aninda BAYAT olabilir). */
  isaretlendi: s.teslim?.islem === "isaretlendi",
  bloke: s.teslim?.islem === "bloke",
  blokeSebebi: s.teslim?.blokeSebebi ?? null,
  teslimHatasi: s.teslim?.islem === "yapilamadi" ? (s.teslim?.hata ?? "bilinmiyor") : null,
  mergeYapildi: Boolean(s.teslim?.mergeYapildi),
  entegrasyon: s.teslim?.entegrasyonTesti ?? null,
  worktree: dogrudanBant(s.gorev) ? null : wt(s.gorev.id),
  worktreeTemizlendi: Boolean(s.teslim?.worktreeTemizlendi),
  depo: s.gorev.bant === "lexis" ? "lexis-rapor (../lexis-rapor, push'suz)" : "hukdok",
}));

await agent(
  `SABAH RAPORU yaz: ${RAPOR_DOSYA} (Write araciyla, Turkce, UTF-8).

Bicim: "# Gece Kuyrugu (workflow) · ${TARIH}" basligi; ardindan:
- "## Ozet": X gorev alindi · Y isaretlendi · Z bloke · W atlandi (tek satir)
- "## Isaretlenenler" tablosu: gorev | bant | depo | commit | kapi | denetim | not
  (depo sutunu: bant "lexis" ise "lexis-rapor", yoksa "hukdok". lexis bandinin commit'i lexis-rapor
  DEPOSUNDADIR - sabah incelemesi ve push orada ayrica yapilir; lexis gorevinin worktree'si YOKTUR,
  verideki worktree alanini lexis icin yok say)
- "## Bloke" - EN DEGERLI BOLUM: her bloke gorev icin durma sebebi, son parmak izi,
  denenen yaklasimlar, teshisin kok nedeni, worktree yolu (korunuyorsa), onerilen
  sonraki adim.
- "## Karar bekleyenler": teshis.gorevTanimiHatali=true olanlarin insanaSoru'lari +
  kabulKarsilanmayan maddeler SORU olarak.
- "## Izin engelleri": TUM gorevlerin izinEngelleri listelerini birlestir, tekrarlari
  tekille, hangi gorevde ciktigini yaz. Bossa "yok". (.claude/settings izin listesi
  bu bolumle OLCEREK genisletilecek - baska kaynaktan genisletilmez.)
- "## Atlananlar": atlandi/zincirHatasi/teslimHatasi olanlar sebepleriyle.

KURALLAR:
- MEKANIK OLGULARI UYDURMA: isaretlendi/bloke/mergeYapildi/entegrasyon/worktreeTemizlendi
  yalniz verideki alanlardan okunur. isaretlendi=false olan gorev "tamamlandi" YAZILMAZ.
- durmaSebebi "test-degistirmek-gerekti" basarisizlik gibi yazilmaz - ayri basaraltinda
  "testi degistirmeden gecilemedi, gorev tanimi gozden gecirilmeli" denir (hattin DOGRU
  calistiginin kanitidir).
- Basariyi abartma; KUYRUK.md'ye ve gorev dosyalarina DOKUNMA (isaretlemeler yapildi).

VERI:
${JSON.stringify(ozet, null, 2)}

TAVAN NEDENIYLE ATLANAN: ${atlanan.map((g) => g.id).join(", ") || "yok"}
PLAN UYARILARI: ${(plan.uyarilar ?? []).join(" | ") || "yok"}

Dosyayi yazdiktan sonra PATHSPEC ile commit'le:
  git commit -m 'chore: gece kuyrugu raporu ${TARIH}' -m 'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>' -- ${RAPOR_DOSYA}
(Once git add ${RAPOR_DOSYA} gerekir - dosya yeni/izlenmiyor olabilir.)`,
  { label: "raporcu", phase: "Rapor", effort: "low" },
);

const isaretlenen = ozet.filter((o) => o.isaretlendi);
const blokeler = ozet.filter((o) => o.bloke || o.teslimHatasi);
const atlananlar = ozet.filter((o) => o.atlandi);

log(
  `Bitti: ${isaretlenen.length} isaretlendi · ${blokeler.length} bloke · ` +
    `${atlananlar.length} atlandi (kosu ici) · ${atlanan.length} tavan disi`,
);

return {
  tarih: TARIH,
  isaretlenen: isaretlenen.map((o) => ({ id: o.id, commit: o.commit })),
  bloke: blokeler.map((o) => ({
    id: o.id,
    sebep: o.blokeSebebi ?? o.teslimHatasi ?? o.durmaSebebi ?? "bilinmiyor",
    worktree: o.worktreeTemizlendi ? null : o.worktree,
  })),
  atlanan: atlananlar.map((o) => ({ id: o.id, sebep: o.atlandi })),
  tavanDisi: atlanan.map((g) => g.id),
  izinEngelleri: [...new Set(ozet.flatMap((o) => o.izinEngelleri ?? []))],
  rapor: RAPOR_DOSYA,
};
