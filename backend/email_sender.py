"""
E-posta Gönderim Modülü - HukuDok

Microsoft Graph API kullanarak PDF ekli e-posta gönderir.
Gönderici: arsiv@lexisbio.onmicrosoft.com
"""

import os
import re
import base64
import logging
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

from sharepoint.auth_graph import get_graph_token

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
        dict: sender
    """
    _load_env()
    return {
        "sender": os.getenv("EMAIL_SENDER", ""),
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
    cc_emails: list[str] = None,
    extra_attachments: list[dict] = None
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
        extra_attachments: Ek belgeler listesi [{"path": str, "name": str}] (Opsiyonel)

    Returns:
        dict: {"success": bool, "message": str}
    """
    if cc_emails is None:
        cc_emails = []

    config = _get_email_config()

    # 1. Gönderici adresi var mı?
    sender = config["sender"]
    if not sender:
        logger.error("❌ EMAIL_SENDER tanımlanmamış!")
        return {"success": False, "message": "Gönderici adresi tanımlanmamış"}
    
    # 3. Alıcı listesi boş mu?
    if not to_emails:
        logger.error("❌ Alıcı listesi boş!")
        return {"success": False, "message": "Alıcı listesi boş"}

    # 4. Dosya var mı?
    if not os.path.exists(attachment_path):
        logger.error(f"❌ Ek dosya bulunamadı: {attachment_path}")
        return {"success": False, "message": "Ek dosya bulunamadı"}

    try:
        # 5. Token al
        token = get_graph_token()

        # 6. Dosyayı encode et
        attachment_content, file_size = _encode_attachment(attachment_path)
        file_size_mb = file_size / (1024 * 1024)

        # Boyut kontrolü - tek dosya limiti: 70MB, toplam limit: 70MB
        MAX_SINGLE_MB = 70
        MAX_TOTAL_MB = 70

        if file_size_mb > MAX_SINGLE_MB:
            logger.error(f"❌ Ana dosya çok büyük: {file_size_mb:.2f}MB (max: {MAX_SINGLE_MB}MB)")
            return {"success": False, "message": f"Ana dosya çok büyük: {file_size_mb:.2f}MB (max: {MAX_SINGLE_MB}MB)"}

        logger.info(f"📎 Ana dosya hazırlandı: {attachment_name} ({file_size_mb:.2f}MB)")

        # Ana eke ek olarak extra dosyaları encode et
        attachments_payload = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": attachment_name,
                "contentType": "application/pdf",
                "contentBytes": attachment_content
            }
        ]
        total_size_mb = file_size_mb

        if extra_attachments:
            for extra in extra_attachments:
                extra_path = extra.get("path", "")
                extra_name = extra.get("name", "ek_belge")
                if extra_path and os.path.exists(extra_path):
                    extra_content, extra_size = _encode_attachment(extra_path)
                    extra_size_mb = extra_size / (1024 * 1024)

                    # Tek ek boyut kontrolü
                    if extra_size_mb > MAX_SINGLE_MB:
                        logger.warning(f"⚠️ Ek belge çok büyük, atlandı: {extra_name} ({extra_size_mb:.2f}MB)")
                        continue

                    # Toplam boyut kontrolü
                    if total_size_mb + extra_size_mb > MAX_TOTAL_MB:
                        logger.warning(f"⚠️ Toplam ek boyutu limiti aşılıyor, atlandı: {extra_name} (toplam: {total_size_mb + extra_size_mb:.2f}MB)")
                        continue

                    # MIME türünü uzantıya göre belirle
                    ext = Path(extra_path).suffix.lower()
                    mime_map = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                                ".png": "image/png", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                ".doc": "application/msword", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
                    content_type = mime_map.get(ext, "application/octet-stream")
                    attachments_payload.append({
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": extra_name,
                        "contentType": content_type,
                        "contentBytes": extra_content
                    })
                    total_size_mb += extra_size_mb
                    logger.info(f"📎 Ek belge eklendi: {extra_name} ({extra_size_mb:.2f}MB, toplam: {total_size_mb:.2f}MB)")
                else:
                    logger.warning(f"⚠️ Ek belge bulunamadı, atlandı: {extra_path}")

        # 7. E-posta payload'ı oluştur (Multiple Recipients)
        # Graph API format: [{"emailAddress": {"address": "..."}}, ...]
        to_recipients_payload = [{"emailAddress": {"address": email.strip()}} for email in to_emails if email.strip()]
        cc_recipients_payload = [{"emailAddress": {"address": email.strip()}} for email in cc_emails if email.strip()]

        email_payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body_text
                },
                "toRecipients": to_recipients_payload,
                "ccRecipients": cc_recipients_payload,
                "attachments": attachments_payload
            },
            "saveToSentItems": "true"
        }
        
        # 8. E-posta gönder
        url = f"{GRAPH}/users/{sender}/sendMail"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        to_str = ", ".join(to_emails)
        logger.info(f"📧 E-posta gönderiliyor: {sender} → {to_str} (CC: {len(cc_emails)})")
        
        response = None
        for attempt in range(2):
            try:
                response = requests.post(url, headers=headers, json=email_payload, timeout=60)
                if response.status_code == 202:
                    break
                if attempt == 0:
                    logger.warning(f"⚠️ İlk denemede başarısız (HTTP {response.status_code}), 30 sn sonra tekrar deneniyor...")
                    time.sleep(30)
            except requests.exceptions.RequestException as e:
                if attempt == 0:
                    logger.warning(f"⚠️ Bağlantı hatası, 30 sn sonra tekrar deneniyor: {e}")
                    time.sleep(30)
                else:
                    raise

        # 9. Sonucu kontrol et
        if response is not None and response.status_code == 202:
            logger.info(f"✅ E-posta başarıyla gönderildi.")
            return {"success": True, "message": "E-posta gönderildi"}
        elif response is not None:
            error_detail = response.text[:500] if response.text else "Bilinmeyen hata"
            logger.error(f"❌ E-posta gönderilemedi: {response.status_code} - {error_detail}")
            return {"success": False, "message": f"Hata: {response.status_code}"}
            
    except Exception as e:
        logger.error(f"❌ E-posta gönderim hatası: {e}")
        return {"success": False, "message": str(e)}


def _generate_ai_email_body(recipient_name: str, context: dict, sender_name: str = None) -> str:
    """
    Gemini kullanarak kişiselleştirilmiş e-posta metni oluşturur.
    """
    _load_env() # Garantiye al: Ortam değişkenlerini her üretimden önce yükle
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("❌ GEMINI_API_KEY bulunamadı! Ortam değişkenleri yüklenememiş olabilir.")
        return None

    try:
        genai.configure(api_key=api_key)
        
        # Daha hızlı yanıt için Flash modelini kullan
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")
        model = genai.GenerativeModel(model_name)
        
        imza = f"{sender_name}\nHukuDok Belge Arşiv Sistemi" if sender_name else "HukuDok Belge Arşiv Sistemi"
        prompt = f"""
Sen kurumsal bir hukuk bürosunda çalışan profesyonel bir asistansın.
Aşağıdaki bilgilere göre {recipient_name} isimli avukata/muhataba gönderilmek üzere nazik ve profesyonel bir e-posta metni yaz.

Baglam:
- Müvekkil: {context.get('muvekkil_text')}
- Belge Türü: {context.get('belge_turu')}
- Tarih: {context.get('tarih_str')}
{f"- Tebliğ Tarihi: {context.get('teblig_tarihi_str')}" if context.get('teblig_tarihi_str') else ""}
- Konu: HukuDok sistemi üzerinden otomatik arşivlenen belgenin bildirimi.

Kurallar:
1. Hitap: "Sayın {recipient_name}," şeklinde başla.
2. İçerik: Hangi müvekkile ait hangi belgenin (belge türü ve tarihi ile birlikte) ekte sunulduğunu açıkça, tam cümleler kurarak belirt (Örneğin: "X isimli müvekkilinize ait Y tarihli Z belgesi ekte bilginize sunulmuştur."). Sadece "Belge ektedir" gibi çok kısa cevaplar YAZMA.
3. Eğer Tebliğ Tarihi ({context.get("teblig_tarihi_str")}) doluysa, bu tarihi "tebliğ tarihi" olarak mutlaka metinde geçir.
4. Dil: Kurumsal, doğal ve saygılı bir Türkçe kullan. Robotik olmasın.
5. Kapanış: "Saygılarımızla," ve altına tam olarak şu imzayı ekle: "{imza}"
6. Metin dışında (konu başlığı vs) hiçbir şey yazma, sadece e-posta gövdesini ver.
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


def generate_email_preview(recipient_name: str, context: dict, sender_name: str = None) -> str:
    """
    AI e-posta önizlemesi oluşturur (gönderim yapmaz).
    Fallback: standart şablon döndürür.
    """
    body = _generate_ai_email_body(recipient_name, context, sender_name=sender_name)
    if not body:
        teblig_tarihi_str = context.get("teblig_tarihi_str", "")
        muvekkil_text = context.get("muvekkil_text", "Müvekkil")
        tarih_str = context.get("tarih_str", "")
        belge_turu = context.get("belge_turu", "Belge")
        extra_info = f"\nBelgenin tebliğ tarihi: {teblig_tarihi_str}\n" if teblig_tarihi_str else ""
        imza = f"{sender_name}\nHukuDok Belge Arşiv Sistemi" if sender_name else "HukuDok Belge Arşiv Sistemi"
        body = f"""Sayın {recipient_name},

{muvekkil_text} {tarih_str} tarihli {belge_turu} belgesi ektedir.
{extra_info}
Saygılarımızla,
{imza}
"""
    return body


def send_document_notification(
    avukat_kodu: str,
    filename: str,
    pdf_path: str,
    metadata: dict = None,
    custom_to: list[str] = None,
    custom_cc: list[str] = None,
    custom_message: str = None,
    custom_messages: dict = None,
    extra_attachment_paths: list[dict] = None,
    sender_name: str = None,
) -> dict:
    """
    Belge bildirimi gönderir - Her alıcı için özelleştirilmiş AI destekli metin oluşturur.
    custom_message verilirse AI üretimi atlanır ve bu metin kullanılır.
    extra_attachment_paths: ek belgelerin [{path, name}] sözlük listesi.
    """
    config = _get_email_config()

    # --- ALICI LİSTESİ HAZIRLIĞI ---
    to_emails_raw = custom_to if custom_to else []
    cc_emails_raw = custom_cc if custom_cc else []
    
    if not to_emails_raw:
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
    
    subject = f"[HukDok] {belge_turu} - {subject_client}" + (f" | {sender_name}" if sender_name else "")
    
    # --- GÖNDERİM DÖNGÜSÜ (Bireysel Gönderim) ---
    results = []
    
    # Format: "Ad Soyad <email@domain.com>" veya sadece "email@domain.com"
    email_regex = re.compile(r'(.*)<(.+)>')
    
    for i, recipient_str in enumerate(to_emails_raw):
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
            
        # 1. Mesaj kaynağını belirle (öncelik: per-alıcı map > genel mesaj > AI)
        recipient_specific_message = (custom_messages or {}).get(recipient_email)
        active_message = recipient_specific_message or custom_message

        if active_message:
            # "HukuDok Belge Arşiv Sistemi" imzasının önüne sender_name ekle
            if sender_name and sender_name not in active_message and "HukuDok Belge Arşiv Sistemi" in active_message:
                body = active_message.replace(
                    "HukuDok Belge Arşiv Sistemi",
                    f"{sender_name}\nHukuDok Belge Arşiv Sistemi"
                )
            else:
                body = active_message
            logger.info(f"✏️ Kullanıcı mesajı kullanılıyor: {recipient_name} ({recipient_email})")
        else:
            logger.info(f"🤖 AI E-posta hazırlanıyor: {recipient_name} ({recipient_email})")
            body = _generate_ai_email_body(recipient_name, context, sender_name=sender_name)

        # 2. AI Başarısız Olursa Şablon Kullan
        if not body:
            logger.info("ℹ️ Standart şablon kullanılıyor.")
            extra_info = ""
            if context.get("teblig_tarihi_str"):
                extra_info = f"\nBelgenin tebliğ tarihi: {context.get('teblig_tarihi_str')}\n"

            imza = f"{sender_name}\nHukuDok Belge Arşiv Sistemi" if sender_name else "HukuDok Belge Arşiv Sistemi"
            body = f"""Sayın {recipient_name},

{muvekkil_text} {tarih_str} tarihli {belge_turu} belgesi ektedir.
{extra_info}
Saygılarımızla,
{imza}
"""

        # 3. CC listesini temizle (sadece email kısmını al)
        clean_cc_list = []
        for cc_str in cc_emails_raw:
            cc_match = email_regex.match(cc_str)
            if cc_match:
                clean_cc_list.append(cc_match.group(2).strip())
            else:
                clean_cc_list.append(cc_str.strip())

        # 4. Ek belgeleri hazırla
        extra_attach_list = None
        if extra_attachment_paths:
            extra_attach_list = [
                {"path": p.get("path"), "name": p.get("name")}
                for p in extra_attachment_paths
                if p and p.get("path") and os.path.exists(p.get("path"))
            ]

        res = send_document_email(
            to_emails=[recipient_email],
            subject=subject,
            body_text=body,
            attachment_path=pdf_path,
            attachment_name=filename,
            cc_emails=clean_cc_list if i == 0 else [],
            extra_attachments=extra_attach_list
        )
        results.append(res)

    # Sonuçları özetle
    success_count = sum(1 for r in results if r.get("success"))
    if success_count == len(results):
        return {"success": True, "message": f"{success_count} e-posta gönderildi."}
    elif success_count > 0:
        return {"success": True, "message": f"{success_count}/{len(results)} gönderildi."}
    else:
        first_error = next((r.get("message", "") for r in results if not r.get("success")), "")
        return {"success": False, "message": first_error or "Hiçbir e-posta gönderilemedi."}
