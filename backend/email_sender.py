"""
E-posta Gönderim Modülü - HukuDok

Microsoft Graph API kullanarak PDF ekli e-posta gönderir.
Gönderici: arsiv@lexisbio.onmicrosoft.com
"""

import os
import base64
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

from auth_graph import get_graph_token

# Logger
logger = logging.getLogger("EmailSender")

# Graph API endpoint
GRAPH = "https://graph.microsoft.com/v1.0"


def _load_env():
    """Load environment variables."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path, override=True)


def _get_email_config() -> dict:
    """
    E-posta yapılandırmasını döndürür.
    
    Returns:
        dict: enabled, sender, test_mode, test_recipient
    """
    _load_env()
    return {
        "enabled": os.getenv("EMAIL_ENABLED", "false").lower() == "true",
        "sender": os.getenv("EMAIL_SENDER", ""),
        "test_mode": os.getenv("EMAIL_TEST_MODE", "true").lower() == "true",
        "test_recipient": os.getenv("EMAIL_TEST_RECIPIENT", ""),
    }


def _encode_attachment(file_path: str) -> tuple[str, int]:
    """
    PDF dosyasını base64 olarak encode eder.
    
    Args:
        file_path: Dosya yolu
        
    Returns:
        tuple: (base64_content, file_size_bytes)
    """
    with open(file_path, "rb") as f:
        content = f.read()
    
    return base64.b64encode(content).decode("utf-8"), len(content)


def send_document_email(
    to_emails: list[str],
    subject: str,
    body_text: str,
    attachment_path: str,
    attachment_name: str,
    cc_emails: list[str] = None
) -> dict:
    """
    PDF ekli e-posta gönderir (Çoklu Gönderim ve CC Desteği).
    
    Args:
        to_emails: Alıcı e-posta adresleri listesi
        subject: E-posta konusu
        body_text: E-posta içeriği (düz metin)
        attachment_path: PDF dosyasının tam yolu
        attachment_name: E-postada görünecek dosya adı
        cc_emails: CC e-posta adresleri listesi (Opsiyonel)
        
    Returns:
        dict: {"success": bool, "message": str}
    """
    if cc_emails is None:
        cc_emails = []

    config = _get_email_config()
    
    # 1. E-posta özelliği aktif mi?
    if not config["enabled"]:
        logger.info("📧 E-posta özelliği kapalı (EMAIL_ENABLED=false)")
        return {"success": False, "message": "E-posta özelliği kapalı"}
    
    # 2. Gönderici adresi var mı?
    sender = config["sender"]
    if not sender:
        logger.error("❌ EMAIL_SENDER tanımlanmamış!")
        return {"success": False, "message": "Gönderici adresi tanımlanmamış"}
    
    # 3. Test Modu Interceptor Mantığı
    if config["test_mode"]:
        test_recipient = config["test_recipient"]
        if not test_recipient:
             logger.error("❌ Test modu açık ama EMAIL_TEST_RECIPIENT tanımlı değil!")
             return {"success": False, "message": "Test alıcısı tanımlı değil"}

        # Orijinal niyetleri kaydet
        original_to_str = ", ".join(to_emails)
        original_cc_str = ", ".join(cc_emails) if cc_emails else "Yok"
        
        # Alıcıları ez (Override)
        logger.info(f"🧪 TEST MODU: Orijinal Alıcılar [{original_to_str}] yerine [{test_recipient}] adresine gönderiliyor.")
        
        # Test Metnini Gövdeye Ekle
        body_prefix = (
            "📢 [TEST MODU BİLGİLENDİRMESİ]\n"
            "--------------------------------------------------\n"
            f"Bu e-posta normalde şu kişilere gidecekti:\n"
            f"KİME: {original_to_str}\n"
            f"CC: {original_cc_str}\n"
            "--------------------------------------------------\n\n"
        )
        body_text = body_prefix + body_text
        
        # Hedefleri değiştir
        to_emails = [test_recipient]
        cc_emails = []  # Test modunda CC gönderme (veya isterseniz test recipient'ı cc yapabilirsiniz ama gerek yok)
    
    # 4. Alıcı listesi boş mu?
    if not to_emails:
        logger.error("❌ Alıcı listesi boş!")
        return {"success": False, "message": "Alıcı listesi boş"}
    
    # 5. Dosya var mı?
    if not os.path.exists(attachment_path):
        logger.error(f"❌ Ek dosya bulunamadı: {attachment_path}")
        return {"success": False, "message": "Ek dosya bulunamadı"}
    
    try:
        # 6. Token al
        token = get_graph_token()
        
        # 7. Dosyayı encode et
        attachment_content, file_size = _encode_attachment(attachment_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Boyut kontrolü (35MB limit)
        if file_size_mb > 35:
            logger.error(f"❌ Dosya çok büyük: {file_size_mb:.2f}MB (max: 35MB)")
            return {"success": False, "message": f"Dosya çok büyük: {file_size_mb:.2f}MB"}
        
        logger.info(f"📎 Ek dosya hazırlandı: {attachment_name} ({file_size_mb:.2f}MB)")
        
        # 8. E-posta payload'ı oluştur (Multiple Recipients)
        # Graph API format: [{"emailAddress": {"address": "..."}}, ...]
        to_recipients_payload = [{"emailAddress": {"address": email.strip()}} for email in to_emails if email.strip()]
        cc_recipients_payload = [{"emailAddress": {"address": email.strip()}} for email in cc_emails if email.strip()]
        
        email_payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text", # HTML yapmak isterseniz burayı değiştirebiliriz
                    "content": body_text
                },
                "toRecipients": to_recipients_payload,
                "ccRecipients": cc_recipients_payload,
                "attachments": [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": attachment_name,
                        "contentType": "application/pdf",
                        "contentBytes": attachment_content
                    }
                ]
            },
            "saveToSentItems": "true"
        }
        
        # 9. E-posta gönder
        url = f"{GRAPH}/users/{sender}/sendMail"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        to_str = ", ".join(to_emails)
        logger.info(f"📧 E-posta gönderiliyor: {sender} → {to_str} (CC: {len(cc_emails)})")
        
        response = requests.post(url, headers=headers, json=email_payload, timeout=60)
        
        # 10. Sonucu kontrol et
        if response.status_code == 202:
            logger.info(f"✅ E-posta başarıyla gönderildi.")
            return {"success": True, "message": "E-posta gönderildi"}
        else:
            error_detail = response.text[:500] if response.text else "Bilinmeyen hata"
            logger.error(f"❌ E-posta gönderilemedi: {response.status_code} - {error_detail}")
            return {"success": False, "message": f"Hata: {response.status_code}"}
            
    except Exception as e:
        logger.error(f"❌ E-posta gönderim hatası: {e}")
        return {"success": False, "message": str(e)}


def send_batch_document_email(
    to_emails: list[str],
    subject: str,
    body_text: str,
    attachments: list[dict],
    cc_emails: list[str] = None
) -> dict:
    """
    Birden fazla dosya ekli e-posta gönderir.
    
    Args:
        to_emails: Alıcı listesi
        subject: Konu
        body_text: Gövde
        attachments: [{"path": "/tam/yol.pdf", "name": "dosya.pdf"}] listesi
        cc_emails: CC listesi
    """
    if cc_emails is None: cc_emails = []
    
    config = _get_email_config()
    if not config["enabled"]:
        return {"success": False, "message": "E-posta özelliği kapalı"}
        
    sender = config["sender"]
    if not sender:
        return {"success": False, "message": "Gönderici adresi tanımlanmamış"}
        
    # Test Modu
    if config["test_mode"]:
        test_recipient = config["test_recipient"]
        if not test_recipient:
            return {"success": False, "message": "Test alıcısı tanımlı değil"}
            
        orig_to = ", ".join(to_emails)
        orig_cc = ", ".join(cc_emails) if cc_emails else "Yok"
        
        body_prefix = (
            "📢 [TEST MODU - TOPLU GÖNDERİM]\n"
            "--------------------------------------------------\n"
            f"KİME: {orig_to}\n"
            f"CC: {orig_cc}\n"
            "--------------------------------------------------\n\n"
        )
        body_text = body_prefix + body_text
        to_emails = [test_recipient]
        cc_emails = []

    if not to_emails:
        return {"success": False, "message": "Alıcı listesi boş"}

    try:
        token = get_graph_token()
        attachment_list = []
        total_size_mb = 0.0
        
        for item in attachments:
            f_path = item.get("path")
            f_name = item.get("name")
            
            if not f_path or not os.path.exists(f_path):
                logger.warning(f"⚠️ Toplu gönderim: Dosya bulunamadı ({f_path}), atlanıyor.")
                continue
                
            b64, size = _encode_attachment(f_path)
            total_size_mb += (size / (1024 * 1024))
            
            attachment_list.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": f_name,
                "contentType": "application/pdf", 
                "contentBytes": b64
            })
            
        if total_size_mb > 34: # 35MB limit, 1MB margin
            return {"success": False, "message": f"Toplam dosya boyutu çok yüksek: {total_size_mb:.2f}MB (Limit: 34MB)"}
            
        if not attachment_list:
            return {"success": False, "message": "Eklenecek geçerli dosya bulunamadı."}

        # Payload
        to_payload = [{"emailAddress": {"address": e.strip()}} for e in to_emails if e.strip()]
        cc_payload = [{"emailAddress": {"address": e.strip()}} for e in cc_emails if e.strip()]
        
        email_payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body_text},
                "toRecipients": to_payload,
                "ccRecipients": cc_payload,
                "attachments": attachment_list
            },
            "saveToSentItems": "true"
        }
        
        url = f"{GRAPH}/users/{sender}/sendMail"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        logger.info(f"📧 Toplu E-posta: {len(attachment_list)} dosya → {to_emails[0]}...")
        response = requests.post(url, headers=headers, json=email_payload, timeout=90)
        
        if response.status_code == 202:
            logger.info("✅ Toplu e-posta başarıyla gönderildi.")
            return {"success": True, "message": f"{len(attachment_list)} dosya gönderildi"}
        else:
            err = response.text[:200]
            logger.error(f"❌ Toplu e-posta hatası: {response.status_code} - {err}")
            return {"success": False, "message": f"Hata: {response.status_code}"}

    except Exception as e:
        logger.error(f"❌ Toplu gönderim hatası: {e}")
        return {"success": False, "message": str(e)}


import google.generativeai as genai
import re

def _generate_ai_email_body(recipient_name: str, context: dict) -> str:
    """
    Gemini kullanarak kişiselleştirilmiş e-posta metni oluşturur.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("⚠️ GEMINI_API_KEY bulunamadı, standart şablon kullanılacak.")
        return None

    try:
        genai.configure(api_key=api_key)
        
        # Daha hızlı yanıt için Flash modelini kullan
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")
        model = genai.GenerativeModel(model_name)
        
        prompt = f"""
Sen kurumsal bir hukuk bürosunda çalışan profesyonel bir asistansın.
Aşağıdaki bilgilere göre {recipient_name} isimli avukata/muhataba gönderilmek üzere kısa, nazik ve profesyonel bir e-posta metni yaz.

Baglam:
- Müvekkil: {context.get('muvekkil_text')}
- Belge Türü: {context.get('belge_turu')}
- Tarih: {context.get('tarih_str')}
{f"- Tebliğ Tarihi: {context.get('teblig_tarihi_str')}" if context.get('teblig_tarihi_str') else ""}
- Konu: HukuDok sistemi üzerinden otomatik arşivlenen belgenin bildirimi.

Kurallar:
1. Hitap: "Sayın {recipient_name}," şeklinde başla.
2. İçerik: Belgenin ekte sunulduğunu belirt.
3. Eğer Tebliğ Tarihi ({context.get("teblig_tarihi_str")}) doluysa, bu tarihi "tebliğ tarihi" olarak mutlaka metinde geçir.
4. Dil: Kurumsal, doğal ve saygılı bir Türkçe kullan. Robotik olmasın.
5. Kapanış: "Saygılarımızla," ve altına "HukuDok Belge Arşiv Sistemi" imzasını ekle.
6. Not: En alta "---" çizgisinden sonra "Bu e-posta yapay zeka desteğiyle oluşturulmuştur." notunu ekle.
7. Metin dışında (konu başlığı vs) hiçbir şey yazma, sadece e-posta gövdesini ver.
"""
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Eğer model konu başlığı vs eklediyse temizle
        if "Konu:" in text[:50]:
            text = text.split("\n", 1)[1].strip()
            
        return text
    except Exception as e:
        logger.error(f"❌ Gemini AI e-posta oluşturma hatası: {e}")
        return None


def send_document_notification(
    avukat_kodu: str,
    filename: str,
    pdf_path: str,
    metadata: dict = None,
    custom_to: list[str] = None,
    custom_cc: list[str] = None
) -> dict:
    """
    Belge bildirimi gönderir - Her alıcı için özelleştirilmiş AI destekli metin oluşturur.
    """
    config = _get_email_config()
    
    if not config["enabled"]:
        return {"success": False, "message": "E-posta özelliği kapalı"}
    
    # --- ALICI LİSTESİ HAZIRLIĞI ---
    to_emails_raw = custom_to if custom_to else []
    cc_emails_raw = custom_cc if custom_cc else []
    
    # Eğer hiç alıcı yoksa ve test modundaysak placeholder ekle
    if not to_emails_raw and config["test_mode"]:
        to_emails_raw = ["Test Avukatı <test_placeholder@lexis.com>"]
        logger.info("⚠️ Alıcı listesi boş, test için placeholder eklendi.")
    elif not to_emails_raw:
        return {"success": False, "message": "Alıcı listesi boş"}

    # --- METADATA HAZIRLIĞI ---
    if metadata is None: metadata = {}
    
    # Helper: Title Case
    def to_title_case_turkish(text: str) -> str:
        if not text: return text
        words = text.split()
        result = []
        for word in words:
            if word:
                first = word[0].upper()
                rest = word[1:].lower() if len(word) > 1 else ""
                rest = rest.replace("I", "ı").replace("İ", "i")
                result.append(first + rest)
        return " ".join(result)

    # Verileri hazırla
    muvekkil_adi = to_title_case_turkish(metadata.get("muvekkil_adi", "Bilinmeyen Müvekkil"))
    belge_turu = metadata.get("belge_turu", "Belge")
    tarih = metadata.get("tarih", "")
    
    # Tarih formatlama fonksiyonu (YYYY-MM-DD -> DD.MM.YYYY)
    def format_date_tr(date_str: str) -> str:
        if not date_str: return ""
        if "-" in date_str:
            parts = date_str.split("-")
            if len(parts) == 3: return f"{parts[2]}.{parts[1]}.{parts[0]}"
        return date_str

    tarih_str = format_date_tr(tarih)
    teblig_tarihi_str = format_date_tr(metadata.get("teblig_tarihi"))

    # Müvekkil metni
    muvekkiller_raw = metadata.get("muvekkiller", [])
    if muvekkiller_raw and isinstance(muvekkiller_raw, list) and len(muvekkiller_raw) > 1:
        formatted_names = [to_title_case_turkish(m) for m in muvekkiller_raw if m]
        if len(formatted_names) > 1:
            muvekkil_text = ", ".join(formatted_names[:-1]) + " ve " + formatted_names[-1] + " isimli müvekkillerin"
            subject_client = f"{formatted_names[0]} (+{len(formatted_names)-1})"
        else:
            muvekkil_text = f"{formatted_names[0]} isimli müvekkilin"
            subject_client = formatted_names[0]
    else:
        muvekkil_text = f"{muvekkil_adi} isimli müvekkilin"
        subject_client = muvekkil_adi

    context = {
        "muvekkil_text": muvekkil_text,
        "belge_turu": belge_turu,
        "tarih_str": tarih_str,
        "teblig_tarihi_str": teblig_tarihi_str
    }
    
    subject = f"[HukuDok] {belge_turu} - {subject_client}"
    
    # --- GÖNDERİM DÖNGÜSÜ (Bireysel Gönderim) ---
    results = []
    
    # Format: "Ad Soyad <email@domain.com>" veya sadece "email@domain.com"
    email_regex = re.compile(r'(.*)<(.+)>')
    
    for recipient_str in to_emails_raw:
        recipient_name = "İlgili"
        recipient_email = recipient_str.strip()
        
        # Ayrıştır: "Ahmet Yılmaz <ahmet@test.com>" -> name="Ahmet Yılmaz", email="ahmet@test.com"
        match = email_regex.match(recipient_str)
        if match:
            recipient_name = match.group(1).strip()
            recipient_email = match.group(2).strip()
        
        # İsim boşsa fallback
        if not recipient_name:
            recipient_name = "Avukat"
            
        logger.info(f"🤖 AI E-posta hazırlanıyor: {recipient_name} ({recipient_email})")
        
        # 1. AI ile Metin Oluştur
        body = _generate_ai_email_body(recipient_name, context)
        
        # 2. AI Başarısız Olursa Şablon Kullan
        if not body:
            logger.info("ℹ️ Standart şablon kullanılıyor.")
            extra_info = ""
            if context.get("teblig_tarihi_str"):
                extra_info = f"\nBelgenin tebliğ tarihi: {context.get('teblig_tarihi_str')}\n"
            
            body = f"""Sayın {recipient_name},

{muvekkil_text} {tarih_str} tarihli {belge_turu} belgesi ektedir.
{extra_info}
Saygılarımızla,
HukuDok Belge Arşiv Sistemi

---
Bu e-posta otomatik olarak gönderilmiştir.
"""
        
        # 3. Gönder
        # CC sadece ilk e-postada gitsin mi? Yoksa hepsinde mi?
        # Genelde bireysel atılıyorsa CC'ler de her birine eklenir (klasik mail merge mantığı).
        # Ancak bu CC'deki kişiye N tane mail gitmesine sebep olur.
        # Bu sorunu çözmek için: Eğer birden fazla alıcı varsa, CC'yi sadece İLK alıcıya ekle.
        # VEYA kullanıcı bunu biliyordur. Hata yapmamak için hepsine ekliyoruz (Standart davranış).
        # Şimdilik hepsine ekliyoruz.
        
        # CC listesini temizle (sadece email kısmını al)
        clean_cc_list = []
        for cc_str in cc_emails_raw:
            cc_match = email_regex.match(cc_str)
            if cc_match:
                clean_cc_list.append(cc_match.group(2).strip())
            else:
                clean_cc_list.append(cc_str.strip())

        res = send_document_email(
            to_emails=[recipient_email],
            subject=subject,
            body_text=body,
            attachment_path=pdf_path,
            attachment_name=filename,
            cc_emails=clean_cc_list
        )
        results.append(res)

    # Sonuçları özetle
    success_count = sum(1 for r in results if r.get("success"))
    if success_count == len(results):
        return {"success": True, "message": f"{success_count} e-posta gönderildi."}
    elif success_count > 0:
        return {"success": True, "message": f"{success_count}/{len(results)} gönderildi."}
    else:
        return {"success": False, "message": "Hiçbir e-posta gönderilemedi."}


# Test fonksiyonu
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 50)
    print("E-posta Gönderim Test")
    print("=" * 50)
    
    config = _get_email_config()
    print(f"Enabled: {config['enabled']}")
    print(f"Sender: {config['sender']}")
    print(f"Test Mode: {config['test_mode']}")
    print(f"Test Recipient: {config['test_recipient']}")
