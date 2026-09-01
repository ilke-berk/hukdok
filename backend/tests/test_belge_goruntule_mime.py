"""Görüntüleme MIME tipi arşivde servis edilen dosyadan tahmin edilir (2026-09-02).

Arıza: /api/documents/{id}/download?inline=true tipi ORİJİNAL dosya adından
tahmin ediyordu. .udf/.tif orijinalli belgelerin arşiv kopyası dönüştürülmüş
PDF'tir; tip orijinalden gelince tarayıcı içeriği açamayacağını sanıp blob'u
GUID adla indiriyordu ("bazıları açılıyor bazıları iniyor" şikâyeti). Tip ve
inline adı artık stored_filename'den türetilir; attachment davranışı değişmedi.

conftest sözleşmesi: DB'ye/ağa inilmez — SessionLocal, tenant sorgusu ve
SharePoint indirmesi fake'lenir, route fonksiyonu doğrudan çağrılır.
"""
from routes import documents as documents_route


class _Doc:
    def __init__(self, original, stored):
        self.original_filename = original
        self.stored_filename = stored


class _FakeDB:
    def close(self):
        pass


def _serve(monkeypatch, original, stored, inline):
    monkeypatch.setattr(documents_route, "SessionLocal", lambda: _FakeDB())
    monkeypatch.setattr(
        documents_route,
        "get_tenant_owned_document",
        lambda db, doc_id, tenant_id, user: _Doc(original, stored),
    )
    import sharepoint.sharepoint_uploader_graph as spg

    monkeypatch.setattr(
        spg,
        "download_file_from_sharepoint",
        lambda folder, name: (b"%PDF-1.7 icerik", "application/pdf"),
    )
    return documents_route.download_document(doc_id=1, inline=inline, tenant_id="t", user={})


def test_udf_orijinalli_pdf_arsiv_inline_pdf_doner(monkeypatch):
    resp = _serve(
        monkeypatch,
        "Ek_Beyan_Dilekçesi.udf",
        "2020-01-22_BEYAN_26-754_S.Bakanligi.pdf",
        inline=True,
    )
    assert resp.media_type == "application/pdf"
    cd = resp.headers["content-disposition"]
    assert cd.startswith("inline")
    # Ad da içerikle tutarlı: arşiv adı (ve stem'deki noktalar tipi bozmaz)
    assert "2020-01-22_BEYAN_26-754_S.Bakanligi.pdf" in cd


def test_tif_orijinalli_pdf_arsiv_inline_pdf_doner(monkeypatch):
    resp = _serve(monkeypatch, "Ek_Beyan_Dilekçesi (1).tif", "X_2.pdf", inline=True)
    assert resp.media_type == "application/pdf"


def test_pending_udf_arsiv_inline_octet_stream_kalir(monkeypatch):
    """Dönüşümü geceye kalan belge arşivde .udf durur — tarayıcı gösteremez,
    inmesi doğru davranıştır; inline istekte bile octet-stream kalır."""
    resp = _serve(monkeypatch, "dilekce.udf", "2026-08-18_DAVADLK_26-550.udf", inline=True)
    assert resp.media_type == "application/octet-stream"


def test_attachment_davranisi_degismedi(monkeypatch):
    resp = _serve(monkeypatch, "Ek_Beyan_Dilekçesi.udf", "X.pdf", inline=False)
    assert resp.media_type == "application/octet-stream"
    cd = resp.headers["content-disposition"]
    assert cd.startswith("attachment")
    # İndirme adı orijinal kalır (ASCII'ye normalize edilmiş haliyle)
    assert "Ek_Beyan_Dilekcesi.udf" in cd
