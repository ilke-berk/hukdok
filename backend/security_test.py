import requests
import jwt
import datetime
import sys
import os

# Add local directory to path to import api (for sanitizer test)
sys.path.append(os.getcwd())

API_URL = "http://localhost:8000"
FAKE_SECRET = "im_a_hacker"

def create_fake_token():
    """Generates a token signed with a fake secret (HS256) instead of Microsoft's key (RS256)"""
    payload = {
        "tid": "44f029f8-f2f7-4910-8c38-998dca5fad02", # LexisBio (Valid Tenant)
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        "name": "Hacker",
        "email": "hacker@evil.com",
        "preferred_username": "hacker@evil.com"
    }
    # Sign with HS256 using our own secret
    # The server expects RS256 signed by Microsoft
    token = jwt.encode(payload, FAKE_SECRET, algorithm="HS256")
    return token

def test_fake_token():
    print("\n🛡️ TEST 1: SAHTE TOKEN SALDIRISI (Fake Token Attack)")
    print("---------------------------------------------------")
    print("Senaryo: Saldırgan kendi imzaladığı sahte bir 'Yönetici' kartı ile içeri girmeye çalışıyor.")
    
    token = create_fake_token()
    print(f"⚠️  Oluşturulan Sahte Token: {token[:30]}...")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # Try to access a protected endpoint
        response = requests.get(f"{API_URL}/api/config/lawyers", headers=headers)
        
        if response.status_code == 401:
            print("✅ BAŞARILI: Sunucu sahte token'ı reddetti (401 Unauthorized).")
            print("   (AuthVerifier, imzanın Microsoft'a ait olmadığını anladı.)")
        elif response.status_code == 200:
            print("❌ BAŞARISIZ: Sunucu sahte token'ı kabul etti! (GÜVENLİK AÇIĞI VAR)")
        else:
            print(f"ℹ️  Sonuç: Beklenmeyen durum kodu: {response.status_code}")
            
    except Exception as e:
        print(f"⚠️ Hata: API'ye ulaşılamadı. Sunucu çalışıyor mu? ({e})")

def test_filename_sanitization():
    print("\n🛡️ TEST 2: DOSYA ADI ENJEKSİYONU (Path Traversal)")
    print("---------------------------------------------------")
    print("Senaryo: Saldırgan '../../windows/system32/hack.exe' adında bir dosya yüklemeye çalışıyor.")
    
    try:
        from api import sanitize_filename
        
        malicious_filename = "../../windows/system32/hack.exe"
        print(f"⚠️  Girdi Dosya Adı:  {malicious_filename}")
        
        try:
            cleaned_filename = sanitize_filename(malicious_filename)
            print(f"✅ Çıktı Dosya Adı:  {cleaned_filename}")
            
            if ".." not in cleaned_filename and "/" not in cleaned_filename and "\\" not in cleaned_filename:
                print("✅ BAŞARILI: Tehlikeli karakterler temizlendi.")
            else:
                 print("❌ BAŞARISIZ: Dosya adı hala tehlikeli karakterler içeriyor!")
                 
        except Exception as e:
            # Usually raises HTTPException for invalid extensions
            print(f"✅ BAŞARILI: Fonksiyon şüpheli dosyayı reddetti/hata fırlattı: {e}")

    except ImportError:
        print("⚠️  Uyarı: 'api.py' içe aktarılamadı (Doğru klasörde misiniz?)")
    except Exception as e:
        print(f"⚠️  Test Hatası: {e}")

if __name__ == "__main__":
    print("🔒 GÜVENLİK DOĞRULAMA TESTİ BAŞLATILIYOR...")
    test_fake_token()
    test_filename_sanitization()
    print("\n---------------------------------------------------")
    print("Test tamamlandı.")
