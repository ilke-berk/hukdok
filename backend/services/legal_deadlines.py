"""Kanuni süre motoru — tebliğ tarihinden son güne, dayanağıyla birlikte (G084).

Süre bildirimlerinin hesap çekirdeği. Girdi: aşama + tebliğ tarihi. Çıktı: son gün,
kural adı, kanun dayanağı ve uygulanan kaydırmaların listesi. Kullanıcı kararı gereği
süre otomatik hesaplanır ama **her uyarı dayanağını taşır** — bu yüzden `Deadline`
sonucu değil, sonucun NEDEN o gün olduğunu da döndürür.

**Saf modül — bilinçli:** DB, config, ağ, saat dilimi kütüphanesi YOK; `models` import
EDİLMEZ (saflık `test_g084_kanuni_sureler.py` içinde AST ile kilitlenir). Hukuki
doğruluk tek dosyada denetlenir, testi ucuzdur. Tek çağıran G085 gece tarayıcısıdır.

Hesap zinciri (sıra önemlidir):

1. **Ham son gün — HMK m. 92/2:** süre hafta olarak belirlenmişse "başladığı güne son
   hafta içinde karşılık gelen günün tatil saatinde" biter. Tebliğ günü sayılmaz;
   iki haftalık süre pratikte tebliğ + 14 gündür (aynı hafta günü).
2. **Adli tatil — HMK m. 102 + 104:** adli tatil her yıl 20 Temmuz'da başlar,
   31 Ağustos'ta sona erer. Süre bu aralıkta biterse "ayrıca bir karar olmaksızın
   adli tatilin bittiği günden itibaren bir hafta uzatılmış sayılır" → son gün
   7 Eylül'dür (31 Ağustos + bir hafta; "1 Eylül'den itibaren bir hafta" okuması da
   aynı güne çıkar).
3. **Tatile rastlama — HMK m. 93:** "Resmî tatil günleri süreye dâhildir. Sürenin son
   gününün resmî tatil gününe rastlaması hâlinde, süre tatili takip eden ilk iş günü
   çalışma saati sonunda biter." Hafta sonu da aynı şekilde ileri kaydırılır.

Bilinçli sınırlar (tahmin yasağı — mahkeme adı motorundaki kuralın kardeşi):

* **Takvimi olmayan yıl için tatil UYDURULMAZ.** Dini bayramlar yıl bazlı tabloda
  ELLE tutulur (`_DINI_BAYRAMLAR`). Tablosu olmayan bir yıla düşen son gün için
  hafta sonu/resmî tatil kaydırması HİÇ uygulanmaz: WARNING loglanır ve sonuç
  `takvim_dogrulandi=False` ile işaretlenir. Adli tatil uzaması bu durumda da
  uygulanır — onun tarihleri takvim tablosuna değil HMK m. 102'ye bağlıdır.
* **Arefe günleri (yarım gün) tatil SAYILMAZ.** Ramazan/Kurban arefesi ve 28 Ekim
  öğleden sonrası yarım gündür; adliye o gün açıktır, süre o gün dolabilir.
* **HMK m. 103 istisnaları bilinmez.** Adli tatilde görülen dava ve işlerde (ihtiyati
  tedbir, delil tespiti, iş davaları…) 104. madde uzaması İŞLEMEZ. Modül davanın adli
  tatile tabi olduğunu VARSAYAR; istisna bilinen çağıran `adli_tatile_tabi=False`
  geçer.
* Sonuç **bilgilendirmedir, süre takibinin yerine geçmez** — uyarı metnine bu şerhi
  koymak çağıranın (G085) işidir.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kural seti — her kural kanun maddesiyle şerhlidir
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Kural:
    """Tek bir kanuni süre kuralı: adı, dayanağı, uzunluğu."""

    ad: str
    dayanak: str
    hafta: int

    @property
    def gun(self) -> int:
        """HMK m. 92/2: hafta olarak belirlenen süre son haftanın aynı gününde biter."""
        return self.hafta * 7


# HMK m. 345/1: "İstinaf yoluna başvuru süresi iki haftadır. Bu süre, ilamın usulen
# taraflardan her birine tebliğiyle işlemeye başlar."
ISTINAF_BASVURU = Kural(
    ad="İstinaf başvuru süresi",
    dayanak="HMK m. 345/1 (iki hafta, ilamın tebliğinden itibaren)",
    hafta=2,
)

# HMK m. 361/1: "Temyiz yoluna başvuru süresi iki haftadır. Bu süre, ilamın usulen
# taraflardan her birine tebliğiyle işlemeye başlar."
TEMYIZ_BASVURU = Kural(
    ad="Temyiz başvuru süresi",
    dayanak="HMK m. 361/1 (iki hafta, kararın tebliğinden itibaren)",
    hafta=2,
)

# HMK m. 127/1: "Cevap dilekçesini verme süresi, dava dilekçesinin davalıya
# tebliğinden itibaren iki haftadır." (Mahkemenin bir aylık ek süresi bu motorun
# kapsamı DIŞINDADIR: elle verilen bir karara bağlıdır, tebliğ tarihinden türetilemez.)
CEVAP_DILEKCESI = Kural(
    ad="Cevap dilekçesi süresi",
    dayanak="HMK m. 127/1 (iki hafta, dava dilekçesinin tebliğinden itibaren)",
    hafta=2,
)

KURALLAR: Tuple[Kural, ...] = (ISTINAF_BASVURU, TEMYIZ_BASVURU, CEVAP_DILEKCESI)

# Aşama → o aşamadaki kararın tebliğiyle işlemeye başlayan süre.
# Aşama etiketleri `managers.stage_decisions.DECISION_STAGES` ile aynı sözlüktendir
# (YEREL | ISTINAF | TEMYIZ | KARAR_DUZELTME) — ikinci bir kopya TUTULMAZ, burada
# yalnız "hangi aşamanın tebliği hangi süreyi başlatır" eşlemesi vardır:
#   * YEREL kararın tebliği   → istinaf süresi
#   * İSTİNAF kararın tebliği → temyiz süresi
#   * TEMYIZ / KARAR_DUZELTME → kanuni süre YOK (karar düzeltme 6100 sayılı HMK'da
#     kaldırıldı; bu aşamalar için tebliğden süre TÜRETİLMEZ → None)
# DAVA_DILEKCESI, aşama tarihçesinde bulunmayan ama cevap süresini başlatan tebliğdir;
# çağıran bu etiketi açıkça verir.
STAGE_KURAL: Dict[str, Kural] = {
    "YEREL": ISTINAF_BASVURU,
    "ISTINAF": TEMYIZ_BASVURU,
    "DAVA_DILEKCESI": CEVAP_DILEKCESI,
}

# ---------------------------------------------------------------------------
# Adli tatil — HMK m. 102 / 104
# ---------------------------------------------------------------------------

ADLI_TATIL_BASLANGIC = (7, 20)   # 20 Temmuz (dâhil)
ADLI_TATIL_BITIS = (8, 31)       # 31 Ağustos (dâhil)
ADLI_TATIL_SONRASI_SON_GUN = (9, 7)  # 31 Ağustos + bir hafta


def adli_tatil_icinde(gun: date) -> bool:
    """Verilen gün adli tatile (20 Temmuz – 31 Ağustos, iki uç dâhil) rastlıyor mu?"""
    return ADLI_TATIL_BASLANGIC <= (gun.month, gun.day) <= ADLI_TATIL_BITIS


# ---------------------------------------------------------------------------
# Resmî tatil takvimi — yıl bazlı, dini bayramlar ELLE
# ---------------------------------------------------------------------------

# Her yıl tekrarlayan, tarihi sabit resmî tatiller (2429 sayılı Kanun).
# Yarım günler (28 Ekim öğleden sonra, arefeler) BİLİNÇLİ YOKTUR — bkz. modül şerhi.
_SABIT_TATILLER: Tuple[Tuple[Tuple[int, int], str], ...] = (
    ((1, 1), "Yılbaşı"),
    ((4, 23), "Ulusal Egemenlik ve Çocuk Bayramı"),
    ((5, 1), "Emek ve Dayanışma Günü"),
    ((5, 19), "Atatürk'ü Anma, Gençlik ve Spor Bayramı"),
    ((7, 15), "Demokrasi ve Millî Birlik Günü"),
    ((8, 30), "Zafer Bayramı"),
    ((10, 29), "Cumhuriyet Bayramı"),
)

# Dini bayramlar — (başlangıç ayı, günü), süre (gün), ad.
# KAYNAK: Diyanet İşleri Başkanlığı dinî günler takvimi. Hesaplanmaz, ELLE girilir;
# bu tabloda OLMAYAN yıl için tahmin üretilmez (bkz. `_ilk_is_gunu`).
# BAKIM NOTU: yeni yıl eklenirken tarihler Diyanet takviminden İNSAN eliyle doğrulanır;
# tek düzeltme noktası burasıdır.
_DINI_BAYRAMLAR: Dict[int, Tuple[Tuple[Tuple[int, int], int, str], ...]] = {
    2024: (((4, 10), 3, "Ramazan Bayramı"), ((6, 16), 4, "Kurban Bayramı")),
    2025: (((3, 30), 3, "Ramazan Bayramı"), ((6, 6), 4, "Kurban Bayramı")),
    2026: (((3, 20), 3, "Ramazan Bayramı"), ((5, 27), 4, "Kurban Bayramı")),
    2027: (((3, 9), 3, "Ramazan Bayramı"), ((5, 16), 4, "Kurban Bayramı")),
}

#: Takvimi doğrulanmış yıllar. Bunun dışındaki bir yıla düşen son gün kaydırılmaz.
TAKVIMLI_YILLAR = frozenset(_DINI_BAYRAMLAR)


@lru_cache(maxsize=None)
def resmi_tatiller(yil: int) -> Dict[date, str]:
    """Bir yılın resmî tatil günleri (gün → tatilin adı).

    Takvimi olmayan yıl için BOŞ sözlük döner — "tatil yok" demek değildir, "bilinmiyor"
    demektir; kaydırma kararını `_ilk_is_gunu` `TAKVIMLI_YILLAR`a bakarak verir.
    """
    if yil not in TAKVIMLI_YILLAR:
        return {}

    tatiller: Dict[date, str] = {}
    for (ay, gun), ad in _SABIT_TATILLER:
        tatiller[date(yil, ay, gun)] = ad

    # Bayram bir sonraki yıla taşabilir; hem bu yılın hem önceki yılın kayıtları taranır.
    for kaynak_yil in (yil - 1, yil):
        for (ay, gun), sure, ad in _DINI_BAYRAMLAR.get(kaynak_yil, ()):
            baslangic = date(kaynak_yil, ay, gun)
            for offset in range(sure):
                bayram_gunu = baslangic + timedelta(days=offset)
                if bayram_gunu.year == yil:
                    tatiller[bayram_gunu] = f"{ad} ({offset + 1}. gün)"
    return tatiller


def _tatil_sebebi(gun: date) -> Optional[str]:
    """Gün çalışılmayan bir güne mi rastlıyor? Rastlıyorsa sebebi, yoksa None."""
    if gun.weekday() == 5:
        return "hafta sonu (Cumartesi)"
    if gun.weekday() == 6:
        return "hafta sonu (Pazar)"
    ad = resmi_tatiller(gun.year).get(gun)
    if ad:
        return f"resmî tatil ({ad})"
    return None


# ---------------------------------------------------------------------------
# Sonuç
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Deadline:
    """Hesaplanmış kanuni süre — son gün + neden o gün olduğunun tam izi."""

    son_gun: date
    kural_adi: str
    dayanak: str
    #: Uygulanan kaydırma/uzatmalar, uygulandıkları sırayla (boş = ham süre aynen).
    kaydirmalar: Tuple[str, ...] = field(default_factory=tuple)
    #: False ise son günün yılının resmî tatil takvimi YOK; kaydırma uygulanmadı.
    takvim_dogrulandi: bool = True
    #: HMK m. 92/2 ile bulunan, hiçbir kaydırma uygulanmamış gün (izlenebilirlik).
    ham_son_gun: Optional[date] = None
    #: Süreyi başlatan tebliğ tarihi.
    teblig_tarihi: Optional[date] = None


def _ilk_is_gunu(gun: date) -> Tuple[date, Tuple[str, ...], bool]:
    """HMK m. 93: son gün tatile rastlarsa tatili takip eden ilk iş gününe kaydır.

    Takvimi doğrulanmamış yıla düşen gün KAYDIRILMAZ (tahmin yasağı) — gün aynen,
    `takvim_dogrulandi=False` ile döner.
    """
    kaydirmalar: list[str] = []
    imlec = gun
    # Üst üste en fazla dokuz çalışılmayan gün olabilir (bayram + hafta sonu);
    # sayaç sonsuz döngüye karşı sigortadır.
    for _ in range(15):
        if imlec.year not in TAKVIMLI_YILLAR:
            return imlec, tuple(kaydirmalar), False
        sebep = _tatil_sebebi(imlec)
        if sebep is None:
            return imlec, tuple(kaydirmalar), True
        imlec = imlec + timedelta(days=1)
        kaydirmalar.append(f"{sebep} → {imlec.isoformat()} (HMK m. 93)")
    return imlec, tuple(kaydirmalar), True


def _normalize_stage(stage: str) -> str:
    """Aşama etiketini karşılaştırılabilir hale getirir (İ/ı tuzağı dâhil)."""
    ham = stage.strip().replace("ı", "i").replace("İ", "I")
    return ham.upper().replace(" ", "_").replace("-", "_")


def deadline_for(
    stage: Optional[str],
    teblig_tarihi: Optional[date],
    *,
    adli_tatile_tabi: bool = True,
) -> Optional[Deadline]:
    """Aşama + tebliğ tarihinden kanuni son günü hesaplar.

    `None` döner:
      * `teblig_tarihi` yoksa — boş veriden süre UYDURULMAZ,
      * aşamanın tebliğinden işleyen bir kanuni süre yoksa (TEMYIZ, KARAR_DUZELTME)
        ya da aşama etiketi tanınmıyorsa.

    `adli_tatile_tabi=False`: HMK m. 103 kapsamındaki (adli tatilde görülen) dava ve
    işlerde 104. madde uzaması uygulanmaz.
    """
    if teblig_tarihi is None or not stage:
        return None

    kural = STAGE_KURAL.get(_normalize_stage(stage))
    if kural is None:
        return None

    return deadline_for_kural(kural, teblig_tarihi, adli_tatile_tabi=adli_tatile_tabi)


def deadline_for_kural(
    kural: Kural,
    teblig_tarihi: Optional[date],
    *,
    adli_tatile_tabi: bool = True,
) -> Optional[Deadline]:
    """Aşamadan bağımsız, doğrudan kurala göre hesap (cevap dilekçesi gibi aşamasız süreler)."""
    if teblig_tarihi is None:
        return None

    # 1) HMK m. 92/2 — ham son gün
    ham_son_gun = teblig_tarihi + timedelta(days=kural.gun)
    kaydirmalar: list[str] = []
    son_gun = ham_son_gun

    # 2) HMK m. 104 — adli tatil uzaması
    if adli_tatile_tabi and adli_tatil_icinde(son_gun):
        uzatilmis = date(son_gun.year, *ADLI_TATIL_SONRASI_SON_GUN)
        kaydirmalar.append(
            f"adli tatil ({son_gun.isoformat()} tatile rastladı) → "
            f"{uzatilmis.isoformat()} (HMK m. 102/104: bir hafta uzama)"
        )
        son_gun = uzatilmis

    # 3) HMK m. 93 — tatile rastlayan son günün kaydırılması
    son_gun, tatil_kaydirmalari, takvim_dogrulandi = _ilk_is_gunu(son_gun)
    kaydirmalar.extend(tatil_kaydirmalari)

    if not takvim_dogrulandi:
        logger.warning(
            "Resmî tatil takvimi yok (yıl=%s): %s kaydırmasız döndürüldü, "
            "sonuç 'takvim doğrulanmadı' işaretli.",
            son_gun.year,
            kural.ad,
        )

    return Deadline(
        son_gun=son_gun,
        kural_adi=kural.ad,
        dayanak=kural.dayanak,
        kaydirmalar=tuple(kaydirmalar),
        takvim_dogrulandi=takvim_dogrulandi,
        ham_son_gun=ham_son_gun,
        teblig_tarihi=teblig_tarihi,
    )
