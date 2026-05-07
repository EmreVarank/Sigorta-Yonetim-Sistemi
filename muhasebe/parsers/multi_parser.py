import os
import re
import sys
import json
import sqlite3
import pandas as pd
import pdfplumber
from datetime import datetime
from PyPDF2 import PdfReader

# C# karakter sorunu için
if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

# ==============================================================================
# 🗄️ SQLİTE VERİTABANI FONKSİYONLARI
# ==============================================================================

def init_database(db_path):
    """SQLite veritabanını ve tabloyu oluşturur."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS policeler (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sigortali TEXT,
                tarih TEXT,
                musteri_no TEXT,
                police_no TEXT UNIQUE,
                tur TEXT,
                sirket TEXT,
                plaka TEXT,
                marka TEXT,
                tutar TEXT,
                aciklama TEXT,
                referans TEXT,
                iletisim TEXT,
                kayit_tarihi DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            # Police_no üzerinde unique constraint var, ekstra index performans için
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_police_no ON policeler(police_no)')
            
            conn.commit()
        return True
    except Exception as e:
        if sys.stdout:
            print(f"VERİTABANI OLUŞTURMA HATASI: {type(e).__name__}: {str(e)}")
        return False

def insert_police_data(db_path, data_list):
    """Poliçe verilerini SQLite'a ekler (duplikasyon kontrolü ile)."""
    added_count = 0
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            for data in data_list:
                police_no = str(data.get('POLİÇE NO', '')).strip()
                
                # Güvenlik: Boş veya geçersiz poliçe numaralarını atla
                if not police_no or police_no in ("-", "nan", "None"):
                    if sys.stdout:
                        print(f"LOG: Geçersiz poliçe no atlandı: {data.get('SİGORTALI', 'Bilinmeyen')}")
                    continue
                
                try:
                    cursor.execute('''
                    INSERT INTO policeler 
                    (sigortali, tarih, musteri_no, police_no, tur, sirket, plaka, marka, tutar, aciklama, referans, iletisim)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        data.get('SİGORTALI', ''),
                        data.get('TARİH', ''),
                        data.get('MÜŞTERİ NO', ''),
                        police_no,
                        data.get('TÜR', ''),
                        data.get('ŞİRKET', ''),
                        data.get('PLAKA', ''),
                        data.get('MARKA', ''),
                        data.get('TUTAR', ''),
                        data.get('AÇIKLAMA', ''),
                        data.get('REFERANS', ''),
                        data.get('İLETİŞİM', '')
                    ))
                    added_count += 1
                except sqlite3.IntegrityError:
                    # UNIQUE constraint ihlali - poliçe zaten var
                    if sys.stdout:
                        print(f"LOG: Duplikasyon atlandı (DB): {police_no}")
                    continue
            
            conn.commit()
        return added_count
    except Exception as e:
        if sys.stdout:
            print(f"VERİTABANI HATASI: {type(e).__name__}: {str(e)}")
        return added_count

# ==============================================================================
# 🛠️ YARDIMCI METİN FONKSİYONLARI
# ==============================================================================

def clean_text(text):
    """Metni temizler ve tek satır haline getirir."""
    if not text: return ""
    text = text.replace("\n", " ")
    return re.sub(r'\s+', ' ', text).strip()

def normalize_amount_to_turkish(amount_str):
    """Tutarı Türk formatına çevirir: 1.234,56"""
    if not amount_str or amount_str == "0" or amount_str == "-":
        return amount_str
    
    # EUR gibi para birimlerini koru
    currency = ""
    if "EUR" in amount_str:
        currency = " EUR"
        amount_str = amount_str.replace("EUR", "").strip()
    
    # Boşlukları temizle
    amount_str = amount_str.replace(" ", "")
    
    # Virgül ve nokta sayısını kontrol et
    comma_count = amount_str.count(',')
    dot_count = amount_str.count('.')
    
    # Son virgül ve noktanın pozisyonunu bul
    last_comma_pos = amount_str.rfind(',')
    last_dot_pos = amount_str.rfind('.')
    
    # DURUM 1: ABD formatı - son nokta virgülden SONRA: 19,320.11 veya 1,234.56
    # Virgül binlik ayırıcı, nokta ondalık ayırıcı
    if comma_count >= 1 and last_dot_pos > last_comma_pos and last_dot_pos != -1:
        # Tüm virgülleri kaldır, noktayı virgüle çevir
        amount_str = amount_str.replace(',', '').replace('.', ',')
    
    # DURUM 2: Türk formatı - son virgül noktadan SONRA: 1.234,56
    # Nokta binlik ayırıcı, virgül ondalık ayırıcı (zaten doğru)
    elif comma_count >= 1 and last_comma_pos > last_dot_pos and last_comma_pos != -1:
        # Zaten Türk formatı, sadece binlik ayırıcıları düzelt
        pass
    
    # DURUM 3: Tek nokta var: 1234.56 → ABD formatı
    elif dot_count == 1 and comma_count == 0:
        parts = amount_str.split('.')
        if len(parts) > 1 and len(parts[1]) <= 2:  # Ondalık kısım 2 basamak veya daha az
            amount_str = amount_str.replace('.', ',')
    
    # DURUM 4: Tek virgül var: 1234,56 → Türk formatı (zaten doğru)
    # Hiçbir şey yapma
    
    # Binlik ayırıcıları düzelt
    if ',' in amount_str:
        parts = amount_str.split(',')
        integer_part = parts[0]
        decimal_part = parts[1] if len(parts) > 1 else '00'
        
        # Mevcut noktalardı temizle
        integer_part = integer_part.replace('.', '')
        
        # Binlik gruplama yap (sağdan sola)
        if len(integer_part) > 3:
            result = []
            for i, digit in enumerate(reversed(integer_part)):
                if i > 0 and i % 3 == 0:
                    result.append('.')
                result.append(digit)
            integer_part = ''.join(reversed(result))
        
        amount_str = f"{integer_part},{decimal_part}"
    
    return amount_str + currency

def extract_amount(text):
    """Tutar çeker ve Türk formatına çevirir (GÜVENLİ VERSİYON)."""
    hdi_match = re.search(r'TOPLAM\s*PRİM\s*[:\s]*([\d\.,]+)', text, re.IGNORECASE)
    if hdi_match: return normalize_amount_to_turkish(hdi_match.group(1))

    ethica_match = re.search(r'ÖDENECEK\s*PRİM\s*[:\s]*([\d\.,]+)', text, re.IGNORECASE)
    if ethica_match: return normalize_amount_to_turkish(ethica_match.group(1))

    quick_brut = re.search(r'BRÜT\s*PRİM\s*[:\s]*([\d\.,]+)', text, re.IGNORECASE)
    if quick_brut: return normalize_amount_to_turkish(quick_brut.group(1))

    dask_match = re.search(r'Poliçe\s*Primi\s*[:\s]*([\d\.,]+)', text, re.IGNORECASE)
    if dask_match: return normalize_amount_to_turkish(dask_match.group(1))

    match = re.search(r'(?:ÖDENECEK|GENEL\s*TOPLAM|TOPLAM|BRÜT)\s*PRİM[İ]?[:\s]*([\d\.,]+)\s*(?:TL|TRL)?', text, re.IGNORECASE)
    if match: return normalize_amount_to_turkish(match.group(1).strip())

    matches = re.findall(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*TL', text)
    valid_amounts = []
    for m in matches:
        clean_val = m.replace(".", "").replace(",", ".")
        try:
            val = float(clean_val)
            if 10 < val < 50000000:
                valid_amounts.append(m)
        except: continue
    if valid_amounts:
        return normalize_amount_to_turkish(max(valid_amounts, key=lambda x: len(x)))

    return "0"

def get_text_robust(pdf_path):
    text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages[:2]:
            t = page.extract_text()
            if t: text += t + " "
    except: pass
    if len(text) < 50:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:2]:
                    t = page.extract_text()
                    if t: text += t + " "
        except: pass
    return text

# ==============================================================================
# 🔍 1. ADIM: GELİŞMİŞ TÜR TESPİTİ
# ==============================================================================
def identify_policy_type(pdf_path):
    """PDF içeriğinden poliçe türünü belirler (SADECE İÇERİKTEN)"""
    
    # PDF içeriğini al - Doğa için daha fazla sayfa tara
    text_raw = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # İlk 5 sayfayı tara (Doğa bilgisi 2. veya 3. sayfada olabilir)
            # Bellek koruması: Her sayfa işlendikten sonra bellekten temizlenir
            for i, page in enumerate(pdf.pages[:5]):
                try:
                    t = page.extract_text()
                    if t: text_raw += t + " "
                except Exception as page_err:
                    if sys.stdout:
                        print(f"LOG: Sayfa {i+1} okunamadı ({os.path.basename(pdf_path)}): {str(page_err)[:50]}")
    except Exception as e:
        if sys.stdout:
            print(f"LOG: PDF okuma hatası ({os.path.basename(pdf_path)}): {type(e).__name__}")
        text_raw = get_text_robust(pdf_path)
    
    # "ESKİ SİGORTA ŞİRKETİ" satırlarını temizle (Önemli!)
    text_cleaned = re.sub(r'ESKİ\s+SİGORTA\s+ŞİRKET[İI][:\s]+[A-ZÇĞİÖŞÜa-zçğıöşü\s]+', '', text_raw, flags=re.IGNORECASE)
    text_cleaned = re.sub(r'ESKİ\s+ŞİRKET[:\s]+[A-ZÇĞİÖŞÜa-zçğıöşü\s]+', '', text_cleaned, flags=re.IGNORECASE)
    text_cleaned = re.sub(r'ÖNCEKİ\s+SİGORTA[:\s]+[A-ZÇĞİÖŞÜa-zçğıöşü\s]+', '', text_cleaned, flags=re.IGNORECASE)
    text_cleaned = re.sub(r'ÖNCEKİ\s+POLİÇE\s+ŞİRKET[İI][:\s]+[A-ZÇĞİÖŞÜa-zçğıöşü\s]+', '', text_cleaned, flags=re.IGNORECASE)
    # ALLIANZ için ek temizlik - "Önceki Sigorta Şirketi: ALLIANZ" veya "Önceki Sigortacı" kalıpları
    text_cleaned = re.sub(r'ÖNCEKİ\s+SİGORTACI[:\s]+[A-ZÇĞİÖŞÜa-zçğıöşü\s]+', '', text_cleaned, flags=re.IGNORECASE)
    text_cleaned = re.sub(r'Önceki\s+Sigorta\s+Şirketi[:\s]+[A-ZÇĞİÖŞÜa-zçğıöşü\s]+', '', text_cleaned, flags=re.IGNORECASE)
    
    # İlk 30 satırda ara (Üst kısımda genelde asıl şirket bilgisi var)
    lines_first = text_cleaned.split('\n')[:30]
    text_first_upper = ' '.join(lines_first).upper()
    text_upper = text_cleaned.upper()
    
    # =========================================================================
    # ŞİRKET TESPİTİ - ÖNCELİK SIRASI ÖNEMLİ!
    # 1) Önce spesifik şirket adları (ilk 30 satırda) - AXA, HDI, RAY vb.
    # 2) Sonra ALLIANZ (tüm metinde - footer'da olabilir)
    # =========================================================================
    
    # --- AXA ve diğer spesifik şirketler (ilk 30 satırda) ---
    if "RAY SİGORTA" in text_first_upper: return "TRAFİK_RAY"
    if "HEPİYİ" in text_first_upper or "HEPIYI" in text_first_upper: return "TRAFİK_HEPİYİ"
    if "ETHICA SİGORTA" in text_first_upper or "ETHİCA SİGORTA" in text_first_upper: return "TRAFİK_ETHICA"
    if "HDI SİGORTA" in text_first_upper or "HDI SIGORTA" in text_first_upper or "0850 222 8 434" in text_first_upper:
        # HDI Yeni format kontrolü - "Başlangıç-Bitiş Tarihi" veya "Ad Soyad / Ünvan" varsa yeni format
        # Upper olmayan text'te ara (encoding problemi yüzünden)
        text_first_raw = ' '.join(lines_first)
        if "Başlangıç-Bitiş" in text_first_raw or "Ad Soyad / Ünvan" in text_first_raw:
            return "TRAFİK_HDI_YENI"
        return "TRAFİK_HDI"
    if "SOMPO" in text_first_upper: return "TRAFİK_SOMPO"
    if "QUICK" in text_first_upper: return "TRAFİK_QUICK"
    # DOĞA SİGORTA - PDF'teki 'Sigorta' kelimesi hem İngilizce I hem Türkçe İ olabilir
    if ("DOĞA SİGORTA" in text_first_upper or "DOGA SIGORTA" in text_first_upper or 
        "DOĞA SIGORTA" in text_first_upper or "DOGA SİGORTA" in text_first_upper): return "TRAFİK_DOĞA"
    
    # Bulamazsa tüm metne bak (ama temizlenmiş versiyonda)
    text_upper = text_cleaned.upper()

    # Şirket belirleme (tüm metinde)
    if "RAY SİGORTA" in text_upper: return "TRAFİK_RAY"
    if "HEPİYİ" in text_upper or "HEPIYI" in text_upper: return "TRAFİK_HEPİYİ"
    if "ETHICA SİGORTA" in text_upper or "ETHİCA SİGORTA" in text_upper:
        if "TRAFİK" in text_upper or "ZORUNLU MALİ" in text_upper: return "TRAFİK_ETHICA"
    if "HDI SİGORTA" in text_upper or "HDI SIGORTA" in text_upper or "0850 222 8 434" in text_upper:
        # HDI Yeni format kontrolü - "Başlangıç-Bitiş Tarihi" veya "Ad Soyad / Ünvan" varsa yeni format
        if "Başlangıç-Bitiş" in text_cleaned or "Ad Soyad / Ünvan" in text_cleaned:
            return "TRAFİK_HDI_YENI"
        return "TRAFİK_HDI"
    if "SOMPO" in text_upper and ("TRAFİK" in text_upper or "KARAYOLLARI" in text_upper): return "TRAFİK_SOMPO"
    if "QUICK" in text_upper and ("TRAFİK" in text_upper or "KARAYOLLARI" in text_upper): return "TRAFİK_QUICK"
    # DOĞA SİGORTA - PDF'teki 'Sigorta' kelimesi hem İngilizce I hem Türkçe İ olabilir
    # Önce şirket tespiti yap (poliçe türü kontrolünden ÖNCE!)
    if ("DOĞA SİGORTA" in text_upper or "DOGA SIGORTA" in text_upper or 
        "DOĞA SIGORTA" in text_upper or "DOGA SİGORTA" in text_upper):
        if "TRAFİK" in text_upper or "KARAYOLLARI" in text_upper: return "TRAFİK_DOĞA"

    # Poliçe türü belirleme (içerikten) - ŞİRKET TESPİTİNDEN ÖNCE!
    # ÖNCELİK SIRASI ÖNEMLİ! Önce spesifik, sonra genel kontroller
    
    # 1. Çok spesifik türler önce
    if "İŞYERİM" in text_upper or "ISYERIM" in text_upper: return "İŞYERİ"
    if "NAKLİYAT" in text_upper or "EMTİA" in text_upper: return "NAKLİYAT"
    
    # 2. SEYAHAT - Sadece çok spesifik kontroller
    if "SEYAHAT SİGORTASI" in text_upper: return "SEYAHAT"
    if "SEYAHAT SAĞLIK SİGORTASI" in text_upper: return "SEYAHAT"
    
    # 3. EVİM PAKET - DASK'tan önce kontrol et
    if "EVİM PAKET" in text_upper: return "EVİM"
    
    # 4. DASK - "ZORUNLU DEPREM SİGORTASI" spesifik olarak ara
    if "ZORUNLU DEPREM" in text_upper: return "DASK"
    # DASK - Sadece "DASK" kelimesi geçiyorsa (spesifik kontrol)
    if "DASK" in text_upper: return "DASK"
    
    # 5. Sağlık - Spesifik kontroller
    if "SAĞLIĞIM" in text_upper or "TAMAMLAYICI SAĞLIK" in text_upper: return "SAĞLIK"
    if "SAĞLIK SİGORTASI" in text_upper or "SAĞLIK POLİÇESİ" in text_upper: return "SAĞLIK"
    if "ÖZEL SAĞLIK" in text_upper: return "SAĞLIK"
    
    # 6. KASKO - Spesifik kontroller
    if "KASKO POLİÇESİ" in text_upper or "KASKO SİGORTASI" in text_upper: return "KASKO"
    if "KASKO" in text_upper and "TRAFİK" not in text_upper: return "KASKO"
    
    # 7. TRAFİK kontrolleri - Sadece çok spesifik kontroller
    if "TRAFİK SİGORTASI" in text_upper: return "TRAFİK"
    if "ZORUNLU MALİ" in text_upper: return "TRAFİK"
    if "KARAYOLLARI MOTORLU" in text_upper: return "TRAFİK"
    
    # 8. EVİM - Genel (KONUT + YANGIN)
    if "KONUT" in text_upper and "YANGIN" in text_upper: return "EVİM"
    if "KONUT SİGORTASI" in text_upper: return "EVİM"
    
    # --- ALLIANZ - Tüm metinde kontrol et (şirket adı footer'da olabilir) ---
    # ÖNEMLİ: TÜR BELİRLEMEDEN SONRA kontrol edilmeli!
    # ALLIANZ varsa ama yukarıda tür belirlenemediyse, sadece KASKO/TRAFİK ayırımı yap
    if "ALLIANZ" in text_upper or "ALLİANZ" in text_upper or "ALLIANZSIGORTA" in text_upper:
        # Önce spesifik ALLIANZ KASKO kontrolü
        if "ALLIANZ KASKO" in text_upper or "GENİŞLETİLMİŞ KASKO" in text_upper:
            return "KASKO"
        # KASKO - Genel kontrol (TRAFİK içermeyen)
        if "KASKO" in text_upper and "TRAFİK" not in text_upper:
            return "KASKO"
        # TRAFİK kontrolü - sadece açık TRAFİK göstergeleri varsa
        if "TRAFİK SİGORTASI" in text_upper or "ZORUNLU MALİ" in text_upper or "KARAYOLLARI MOTORLU" in text_upper:
            return "TRAFİK"

    return "BILINMIYOR"

# ==============================================================================
# ⚙️ PARSING MOTORLARI (REGEX)
# ==============================================================================

def process_hdi_trafik(pdf_path, filename):
    full_text = ""
    lines = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]:
                text = page.extract_text()
                if text:
                    full_text += text + " "
                    lines.extend(text.split('\n'))
    except Exception as e:
        if sys.stdout:
            print(f"LOG: HDI PDF okuma hatası ({filename}): {type(e).__name__}")
        return None
    
    if not full_text.strip():
        if sys.stdout:
            print(f"LOG: HDI PDF boş içerik ({filename})")
        return None
    
    tr_map = {ord('i'): 'İ', ord('ı'): 'I', ord('ğ'): 'Ğ', ord('ü'): 'Ü', ord('ş'): 'Ş', ord('ö'): 'Ö', ord('ç'): 'Ç'}
    content = clean_text(full_text).translate(tr_map).upper()
    insured_name = "-"
    for i, line in enumerate(lines):
        line_clean = line.strip().translate(tr_map).upper()
        if "ADI SOYADI" in line_clean and "UNVANI" in line_clean:
            candidate = line_clean.replace("ADI SOYADI", "").replace("UNVANI", "").replace("/", "").replace(":", "").strip()
            if len(candidate) > 3: insured_name = candidate
            elif i + 1 < len(lines):
                next_line = lines[i+1].strip().translate(tr_map).upper()
                invalid_starts = ["T.C.", "ADRES", "NO:", "MERKEZ", "POLİÇE", "PLAKA", "MÜŞTERİ", "VERGİ"]
                if len(next_line) > 3 and not any(next_line.startswith(x) for x in invalid_starts): insured_name = next_line
            break
    if insured_name != "-":
        parts = insured_name.split()
        clean_parts = [part for part in parts if not any(char.isdigit() for char in part) and "/" not in part and ":" not in part]
        insured_name = " ".join(clean_parts) if clean_parts else insured_name.split(" NO")[0]

    amount = "0"
    search_keywords = ["TOPLAM PRİM", "TOPLAM PRIM", "ÖDENECEK", "GENEL TOPLAM"]
    start_index = -1
    for kw in search_keywords:
        idx = content.find(kw)
        if idx != -1:
            start_index = idx
            break
    if start_index != -1:
        search_area = content[start_index : start_index + 100]
        money_match = re.search(r'(\d{1,3}(?:\.\d{3})*,\d{2})', search_area)
        if money_match: amount = normalize_amount_to_turkish(money_match.group(1))
    if amount == "0":
        all_matches = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})', content)
        if all_matches: amount = normalize_amount_to_turkish(all_matches[-1])

    date = "-"
    date_match = re.search(r'BAŞLANGIÇ\s*TARİHİ\s*[:\s]*(\d{2}/\d{2}/\d{4})', content)
    if date_match: date = date_match.group(1)
    policy_no = "-"
    pol_match = re.search(r'POLİÇE\s*NO\s*[:\s]*(\d{10,}[-\d]*)', content)
    if pol_match: policy_no = pol_match.group(1)
    cust_no = "-"
    cust_match = re.search(r'MÜŞTERİ\s*NO\s*[:\.\s]*(\d{6,})', content)
    if cust_match: cust_no = cust_match.group(1)
    plate = "-"
    pl_match = re.search(r'PLAKA\s*NO.*?\s*(\d{2,3}\s*[A-Z]{1,4}\s*\d{2,5})', content)
    if pl_match: plate = pl_match.group(1).replace(" ", "")
    brand = "-"
    brand_match = re.search(r'MODEL\s*/\s*MARKA\s*[:\s]*\d{4}\s+([A-ZÇĞİÖŞÜ\s\-]+)', content)
    if brand_match: brand = brand_match.group(1).strip().split(" ")[0]
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": "TRAFİK", "PLAKA": plate, "MARKA": brand, "TUTAR": amount, "ŞİRKET": "HDI"}

def hdi_yeni_police(pdf_path, filename):
    """HDI Yeni Format Trafik Poliçesi (2026 format)"""
    full_text = ""
    lines = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]:
                text = page.extract_text()
                if text:
                    full_text += text + " "
                    lines.extend(text.split('\n'))
    except: return None
    
    tr_map = {ord('i'): 'İ', ord('ı'): 'I', ord('ğ'): 'Ğ', ord('ü'): 'Ü', ord('ş'): 'Ş', ord('ö'): 'Ö', ord('ç'): 'Ç'}
    content = clean_text(full_text).translate(tr_map).upper()
    
    # Sigortalı Adı - Yeni formatta "Ad Soyad / Ünvan ISIM SOYISIM"
    insured_name = "-"
    for i, line in enumerate(lines):
        line_clean = line.strip().translate(tr_map).upper()
        # "Ad Soyad / Ünvan" başlığını bul ve aynı satırda isim var
        if "AD SOYAD" in line_clean and ("/" in line_clean or "UNVAN" in line_clean):
            # Başlık sonrası kısmı al
            parts = line_clean.split("UNVAN")
            if len(parts) > 1:
                candidate = parts[1].strip()
            else:
                # "/" sonrası al
                if "/" in line_clean:
                    candidate = line_clean.split("/")[-1].strip()
                else:
                    candidate = line_clean.replace("AD SOYAD", "").strip()
            
            if len(candidate) > 3 and "SIGORTA" not in candidate and "KIMLIK" not in candidate:
                insured_name = candidate
                break
    
    if insured_name != "-":
        # "ÜNVAN" kelimesini temizle
        insured_name = insured_name.replace("ÜNVAN", "").strip()
        parts = insured_name.split()
        clean_parts = [part for part in parts if not any(char.isdigit() for char in part) and "/" not in part]
        insured_name = " ".join(clean_parts) if clean_parts else insured_name
    
    # Tutar - "Toplam Ödenecek Prim"
    amount = "0"
    amount_match = re.search(r'TOPLAM\s+ÖDENECEK\s+PRİM\s+([\d\.\,]+)\s*TL', content)
    if amount_match:
        amount = normalize_amount_to_turkish(amount_match.group(1))
    else:
        # Alternatif: "TOPLAM PRİM" ara
        search_keywords = ["TOPLAM PRİM", "TOPLAM PRIM", "ÖDENECEK"]
        for kw in search_keywords:
            idx = content.find(kw)
            if idx != -1:
                search_area = content[idx : idx + 100]
                money_match = re.search(r'([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})', search_area)
                if money_match:
                    amount = normalize_amount_to_turkish(money_match.group(1))
                    break
    
    # Tarih - "Başlangıç-Bitiş Tarihi 06/01/2026-06/01/2027"
    date = "-"
    date_match = re.search(r'BAŞLANGIÇ[\-\s]*BİTİŞ\s*TARİHİ\s+([\d]{2}/[\d]{2}/[\d]{4})', content)
    if not date_match:
        # Alternatif: "BASLANGIC-BITIS TARIHI" (Türkçe karakter olmadan)
        date_match = re.search(r'BA[SŞ]LANGI[ÇC][\-\s]*B[İI]T[İI][SŞ]\s*TAR[İI]H[İI]\s+([\d]{2}/[\d]{2}/[\d]{4})', content)
    if date_match:
        date = date_match.group(1)
    
    # Poliçe No
    policy_no = "-"
    pol_match = re.search(r'POLİÇE\s*NO\s+([\d]{10,})', content)
    if pol_match:
        policy_no = pol_match.group(1)
    
    # Müşteri No - HDI Yeni formatta müşteri numarası yok (sadece maskeli T.C. Kimlik var)
    cust_no = "-"
    
    # Plaka
    plate = "-"
    pl_match = re.search(r'PLAKA\s*NO\s+([\d]{2}[A-Z]{1,4}[\d]{2,5})', content)
    if pl_match:
        plate = pl_match.group(1)
    
    # Marka - "Marka CHERY" formatında
    brand = "-"
    brand_match = re.search(r'MARKA\s+([A-ZÇĞİÖŞÜ]+)', content)
    if not brand_match:
        # Case-insensitive arama
        brand_match = re.search(r'(?:MARKA|Marka)\s+([A-ZÇĞİÖŞÜa-z]+)', full_text)
    if brand_match:
        brand = brand_match.group(1).strip().upper()
    
    return {
        "SİGORTALI": insured_name,
        "TARİH": date,
        "MÜŞTERİ NO": cust_no,
        "POLİÇE NO": policy_no,
        "TÜR": "TRAFİK",
        "PLAKA": plate,
        "MARKA": brand,
        "TUTAR": amount,
        "ŞİRKET": "HDI"
    }

def process_ethica_trafik(pdf_path, filename):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]: text += page.extract_text() + " "
    except: return None
    tr_map = {ord('i'): 'İ', ord('ı'): 'I', ord('ğ'): 'Ğ', ord('ü'): 'Ü', ord('ş'): 'Ş', ord('ö'): 'Ö', ord('ç'): 'Ç'}
    content = clean_text(text).translate(tr_map).upper()
    insured_name = "-"
    name_match = re.search(r'SİGORTALININ\s*ADI\s*SOYADI.*?:[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*(?:SİGORTALININ\s*ADRESİ|T\.C\.|ADRES))', content)
    if name_match: insured_name = name_match.group(1).strip()
    date = "-"
    date_match = re.search(r'BAŞLANGIÇ\s*TARİHİ\s*[:\s]*(\d{2}/\d{2}/\d{4})', content)
    if date_match: date = date_match.group(1)
    policy_no = "-"
    pol_match = re.search(r'POLİÇE\s*NO\s*[:\s]*(\d{8,})', content)
    if pol_match: policy_no = pol_match.group(1)
    cust_no = "-"
    cust_match = re.search(r'MÜŞTERİ\s*NO\s*[:\s]*(\d{6,})', content)
    if cust_match: cust_no = cust_match.group(1)
    plate = "-"
    pl_match = re.search(r'PLAKA\s*NO\s*[:\s]*(\d{2,3}\s*[A-Z]{1,4}\s*\d{2,5})', content)
    if pl_match: plate = pl_match.group(1).replace(" ", "")
    brand = "-"
    brand_match = re.search(r'(?<!TİPİ)\s+MARKA\s*[:\s]*([A-ZÇĞİÖŞÜ]+)', content)
    if brand_match: brand = brand_match.group(1).strip()
    else:
        brand_alt = re.search(r'MARKA\s*[:\s]*([A-ZÇĞİÖŞÜ]+?)(?=\s+MODEL)', content)
        if brand_alt: brand = brand_alt.group(1).strip()
    amount = "0"
    amount_match = re.search(r'ÖDENECEK\s*PRİM\s*[:\s]*([\d\.,]+)', content)
    if amount_match: amount = normalize_amount_to_turkish(amount_match.group(1))
    else: amount = extract_amount(content)
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": "TRAFİK", "PLAKA": plate, "MARKA": brand, "TUTAR": amount, "ŞİRKET": "ETHİCA"}

def process_quick_trafik(pdf_path, filename):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:3]:
                t = page.extract_text()
                if t: text += t + "\n"
    except: return None
    tr_map = {ord('i'): 'İ', ord('ı'): 'I', ord('ğ'): 'Ğ', ord('ü'): 'Ü', ord('ş'): 'Ş', ord('ö'): 'Ö', ord('ç'): 'Ç'}
    content = clean_text(text).translate(tr_map).upper()
    insured_name = "-"
    name_match = re.search(r'SİGORTALI.*?(?:ADI/ÜNVANI)\s*[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*(?:ADRESİ|TELEFON|E-POSTA))', content)
    if name_match: insured_name = name_match.group(1).strip()
    else:
        name_alt = re.search(r'SİGORTALI\s*[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*(?:ADRESİ))', content)
        if name_alt: insured_name = name_alt.group(1).strip()
    date = "-"
    date_match = re.search(r'POLİÇE\s*BAŞLANGIÇ\s*TARİHİ\s*[:\s]*(\d{2}/\d{2}/\d{4})', content)
    if date_match: date = date_match.group(1)
    policy_no = "-"
    pol_match = re.search(r'POLİÇE\s*NO\s*[:\s]*(\d{10,})', content)
    if pol_match: policy_no = pol_match.group(1)
    plate = "-"
    pl_match = re.search(r'PLAKA\s*NO.*?\s*(\d{2}\s*[A-Z]{1,4}\s*\d{2,5})', content)
    if pl_match: plate = pl_match.group(1).replace(" ", "")
    amount = extract_amount(content)
    
    # ÇAPA YÖNTEMİ
    brand = "-"
    raw_values = re.findall(r':\s*([^\n]+)', text)
    clean_values = []
    for v in raw_values:
        v_clean = v.strip().translate(tr_map).upper()
        if len(v_clean) > 1: clean_values.append(v_clean)
    year_index = -1
    for i, val in enumerate(clean_values):
        if val.isdigit() and len(val) == 4 and val.startswith(("20", "19")):
            if "/" not in val and "." not in val:
                year_index = i
                break
    if year_index != -1:
        if year_index > 0:
            prev_val = clean_values[year_index - 1]
            blacklist = ["OTOMOBİL", "KAMYONET", "HUSUSİ", "TİCARİ", "BENZİN", "DİZEL", "MANUEL", "OTOMATİK", "YOK", "HAYIR", "EVET"]
            if not any(b in prev_val for b in blacklist) and not prev_val.isdigit():
                brand = prev_val
        if brand == "-" or len(brand) < 2:
            if year_index + 1 < len(clean_values):
                next_val = clean_values[year_index + 1]
                brand = next_val.split()[0]
    if len(brand) > 20 or (any(c.isdigit() for c in brand) and " " not in brand): brand = "-"

    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": "-", "POLİÇE NO": policy_no, "TÜR": "TRAFİK", "PLAKA": plate, "MARKA": brand, "TUTAR": amount, "ŞİRKET": "QUICK"}

def process_sompo_trafik(pdf_path, filename):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) > 0: text += pdf.pages[0].extract_text() + " "
            if len(pdf.pages) > 1: text += pdf.pages[1].extract_text() + " "
    except Exception as e:
        if sys.stdout:
            print(f"LOG: SOMPO PDF okuma hatası ({filename}): {type(e).__name__}")
        return None
    
    if not text.strip():
        if sys.stdout:
            print(f"LOG: SOMPO PDF boş içerik ({filename})")
        return None
    content = clean_text(text)
    insured_name = "-"
    name_match = re.search(r'ADI\s*SOYADI\s*/\s*ÜNVANI.*?[:]\s*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*(?:TC\s*KİMLİK|ADRESİ|ADRES))', content, re.IGNORECASE)
    if name_match: insured_name = name_match.group(1).strip()
    else:
        name_alt = re.search(r'SİGORTALI.*?[:\s]([A-ZÇĞİÖŞÜ\s]{5,30})', content)
        if name_alt: insured_name = name_alt.group(1).strip()
    date = "-"
    date_matches = re.findall(r'(\d{2}/\d{2}/\d{4})', content)
    if date_matches: date = date_matches[0]
    policy_no = "-"
    pol_match = re.search(r'\b(3\d{14})\b', content)
    if pol_match: policy_no = pol_match.group(1)
    else:
        pol_lbl = re.search(r'POLİÇE\s*NO\s*[:\s]*(\d{10,})', content, re.IGNORECASE)
        if pol_lbl: policy_no = pol_lbl.group(1)
    cust_no = "-"
    cust_match = re.search(r'\b(8\d{9})\b', content)
    if cust_match: cust_no = cust_match.group(1)
    else:
        digits_10 = re.findall(r'\b([1-9]\d{9})\b', content)
        for num in digits_10:
            if not num.startswith("5"): cust_no = num; break
    plate = "-"
    pl_match = re.search(r'Plaka\s*No\s*[:\s]*([0-9]{2}\s*[A-Z]{1,4}\s*\d{2,5})', content, re.IGNORECASE)
    if pl_match: plate = pl_match.group(1).replace(" ", "")
    brand = "-"
    egm_match = re.search(r'EGM\s*Marka\s*Bilgisi\s*[:\s]*([A-ZÇĞİÖŞÜ\s\(\)\-]+?)(?=\s*(?:EGM|Model|Trafik))', content, re.IGNORECASE)
    if egm_match: brand = egm_match.group(1).strip()
    if brand == "-" or len(brand) < 2:
        br_match = re.search(r'Marka/Tip\s*[:\s]*([A-ZÇĞİÖŞÜ0-9\s\(\)\-\.]+?)(?=\s*(?:Kullanım|Model|Trafik|EGM|Plaka))', content, re.IGNORECASE)
        if br_match: brand = br_match.group(1).strip().split(" ")[0]
    amount = extract_amount(content)
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": "TRAFİK", "PLAKA": plate, "MARKA": brand, "TUTAR": amount, "ŞİRKET": "SOMPO"}

def process_doga_trafik(pdf_path, filename):
    full_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:5]:
                t = page.extract_text()
                if t: full_text += t + " "
    except Exception as e:
        if sys.stdout:
            print(f"LOG: DOĞA PDF okuma hatası ({filename}): {type(e).__name__}")
    
    if not full_text.strip():
        if sys.stdout:
            print(f"LOG: DOĞA PDF boş içerik ({filename})")
        return None
    tr_map = {ord('i'): 'İ', ord('ı'): 'I', ord('ğ'): 'Ğ', ord('ü'): 'Ü', ord('ş'): 'Ş', ord('ö'): 'Ö', ord('ç'): 'Ç'}
    content = clean_text(full_text).translate(tr_map).upper()
    insured_name = "-"
    try:
        with pdfplumber.open(pdf_path) as pdf:
            first_page_lines = pdf.pages[0].extract_text().split('\n')
            for i, line in enumerate(first_page_lines):
                line_clean = line.strip().translate(tr_map).upper()
                if line_clean == "SİGORTALI" or line_clean == "SIGORTALI":
                    if i + 1 < len(first_page_lines):
                        candidate = first_page_lines[i+1].strip().translate(tr_map).upper()
                        invalid_words = ["MAH", "MAHALLESİ", "CAD", "SOK", "SK", "NO:", "AP", "DAİRE"]
                        if len(candidate) > 3 and not any(w in candidate.split() for w in invalid_words):
                            insured_name = candidate; break
    except: pass
    if insured_name == "-":
        name_match = re.search(r'SİGORTALI\s+([A-ZÇĞİÖŞÜ\s]{3,40}?)(?=\s+(?:MAH\.|MAHALLESİ|CD\.|CADDE|SK\.|SOKAK|AP\.|NO:))', content)
        if name_match: insured_name = name_match.group(1).strip()
    plate = "-"
    pl_match = re.search(r'PLAKA\s*[:\s]*(\d{2,3}\s*[A-Z]{1,4}\s*\d{2,5})', content)
    if not pl_match: pl_match = re.search(r'PLAKA\s+(\d{2,3}\s*[A-Z]{1,4}\s*\d{2,5})', content)
    if pl_match: plate = pl_match.group(1).replace(" ", "")
    policy_no = "-"
    prod_match = re.search(r'ÜRÜN\s*NO\s*[:\/]*\s*(\d{8,})', content)
    if prod_match: policy_no = prod_match.group(1)
    if policy_no == "-":
        pol_match = re.search(r'POLİÇE\s*NO\s*[:\s]*(\d{8,})', content)
        if pol_match: policy_no = pol_match.group(1)
    date = "-"
    date_match = re.search(r'(?:BAŞLAMA|BAŞLANGIÇ)\s*TARİHİ\s*[:\s]*(\d{2}[/.-]\d{2}[/.-]\d{4})', content)
    if not date_match: date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', content)
    if date_match: date = date_match.group(1).replace(".", "/").replace("-", "/")
    cust_no = "-"
    cust_match = re.search(r'MÜŞTERİ\s*NO\s*[:\s]*(\d{6,15})', content)
    if cust_match: cust_no = cust_match.group(1)
    brand = "-"
    egm_match = re.search(r'EGM\s*ARAÇ\s*BİLGİLERİ.*?MARKA\s*[:\s]*([A-ZÇĞİÖŞÜ]+)', content)
    if not egm_match: egm_match = re.search(r'MARKA\s*[:\s]*([A-ZÇĞİÖŞÜ\s]+?)(?=\s+MOTOR)', content)
    if egm_match: brand = egm_match.group(1).strip()
    amount = extract_amount(content)
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": "TRAFİK", "PLAKA": plate, "MARKA": brand, "TUTAR": amount, "ŞİRKET": "DOĞA"}

def process_hepiyi_trafik(pdf_path, filename):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]: text += page.extract_text() + " "
    except: return None
    tr_map = {ord('i'): 'İ', ord('ı'): 'I', ord('ğ'): 'Ğ', ord('ü'): 'Ü', ord('ş'): 'Ş', ord('ö'): 'Ö', ord('ç'): 'Ç'}
    content = clean_text(text).translate(tr_map).upper()
    insured_name = "-"
    name_match = re.search(r'SİGORTALI ADI SOYADI/ÜNVANI\s*[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*(?:KİMLİK|SİGORTALI ADRESİ|T\.C\.))', content)
    if name_match: insured_name = name_match.group(1).strip()
    plate = "-"
    pl_match = re.search(r'PLAKA\s*[:\s]*(\d{2,3}\s*[A-Z]{1,4}\s*\d{2,5})', content)
    if pl_match: plate = pl_match.group(1).replace(" ", "")
    brand = "-"
    br_match = re.search(r'MARKA\s*[:\s]*([A-Z0-9\s\-\.]+?)(?=\s*MOTOR|TİPİ)', content)
    if br_match: brand = br_match.group(1).strip()
    date = "-"
    date_triplet = re.search(r'(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})', content)
    if date_triplet: date = date_triplet.group(2)
    else:
        d_match = re.search(r'BAŞLAMA TARİHİ.*?(\d{2}/\d{2}/\d{4})', content)
        if d_match: date = d_match.group(1)
    policy_no = "-"
    p_match = re.search(r'POLİÇE NO\s*(\d{10,})', content)
    if not p_match: p_match = re.search(r'POLİÇE NO.*?(\d{10,})', content)
    if p_match: policy_no = p_match.group(1)
    cust_no = "-"
    c_match = re.search(r'MÜŞTERİ NO\.\s*(\d+)', content)
    if not c_match: c_match = re.search(r'MÜŞTERİ NO.*?(\d{6,})', content)
    if c_match: cust_no = c_match.group(1)
    amount = "0"
    amt_match = re.search(r'BRÜT PRİM\s*([\d\.,]+)', content)
    if amt_match: amount = normalize_amount_to_turkish(amt_match.group(1))
    else: amount = extract_amount(content)
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": "TRAFİK", "PLAKA": plate, "MARKA": brand, "TUTAR": amount, "ŞİRKET": "HEPİYİ"}

def process_ray_trafik(pdf_path, filename):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:3]:
                extracted = page.extract_text()
                if extracted: text += extracted + " "
    except: return None
    tr_map = {ord('i'): 'İ', ord('ı'): 'I', ord('ğ'): 'Ğ', ord('ü'): 'Ü', ord('ş'): 'Ş', ord('ö'): 'Ö', ord('ç'): 'Ç'}
    content = clean_text(text).translate(tr_map).upper()
    insured_name = "-"
    stop_words = r"(?:T\.C\.|TC\.|KİMLİK|ADRES|SİGORTA|VERGİ|MÜŞTERİ|PLAKA|ZEYL)"
    name_match = re.search(r'AD\s*SOYAD\/?Ü?N?V?A?N?.*?[:]\s*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*' + stop_words + r'|:)', content)
    if name_match:
        raw_name = name_match.group(1).strip()
        unwanted = ["T.C.", "KİMLİK", "ADRES", "SİGORTA", "VERGİ"]
        for word in unwanted:
            if word in raw_name: raw_name = raw_name.split(word)[0].strip()
        if raw_name.endswith("ADRESİ"): raw_name = raw_name.replace("ADRESİ", "").strip()
        if len(raw_name) > 2: insured_name = raw_name
    if insured_name == "-":
        alt_match = re.search(r'AD\s*SOYAD\/ÜNVAN\s*[:]\s*([A-ZÇĞİÖŞÜ\s\.]+)', content)
        if alt_match: insured_name = alt_match.group(1).strip()
    brand = "-"
    br_match = re.search(r'MARKASI\s*[:]\s*([A-Z0-9\s\.\-]+?)(?=\s*TİPİ)', content)
    if br_match: brand = br_match.group(1).strip()
    if brand == "-" or len(brand) < 2:
        egm_match = re.search(r'EGM\s*MARKA\s*[:]\s*([A-Z0-9\s\.\-]+?)(?=\s*EGM)', content)
        if egm_match: brand = egm_match.group(1).strip()
    policy_no = "-"
    pol_match = re.search(r'POLİÇE.*?YENİLEME.*?NO\s*[:\s]*([\d\/]+)', content)
    if pol_match: policy_no = pol_match.group(1)
    cust_no = "-"
    c_match = re.search(r'SİGORTALI.*?M\.?NO.*?[:]\s*(\d+)', content)
    if c_match: cust_no = c_match.group(1)
    plate = "-"
    pl_match = re.search(r'PLAKA\s*NO\s*[:]\s*([\d]{2,3}\s*[A-Z]{1,4}\s*[\d]{2,5})', content)
    if pl_match: plate = pl_match.group(1).replace(" ", "")
    date = "-"
    date_match = re.search(r'BAŞLANGIÇ\s*TARİHİ\s*[:\s]*(\d{2}/\d{2}/\d{4})', content)
    if date_match: date = date_match.group(1)
    amount = "0"
    amt_match = re.search(r'TOPLAM\s*BRÜT\s*PR[İI]M\s*[:\s]*([\d\.,]+)', content)
    if amt_match: amount = normalize_amount_to_turkish(amt_match.group(1))
    else:
        amt_alt = re.search(r'BRÜT\s*PR[İI]M\s*[:\s]*([\d\.,]+)', content)
        if amt_alt: amount = normalize_amount_to_turkish(amt_alt.group(1))
        else: amount = extract_amount(content)
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": "TRAFİK", "PLAKA": plate, "MARKA": brand, "TUTAR": amount, "ŞİRKET": "RAY"}

def process_allianz_trafik(pdf_path, filename):
    """Allianz Trafik Poliçesi - Karayolları Motorlu Araçlar Zorunlu Mali Sorumluluk"""
    full_text = ""
    lines = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:3]:
                text = page.extract_text()
                if text:
                    full_text += text + " "
                    lines.extend(text.split('\n'))
    except Exception as e:
        if sys.stdout:
            print(f"LOG: ALLIANZ TRAFİK PDF okuma hatası ({filename}): {type(e).__name__}")
        return None
    
    if not full_text.strip():
        if sys.stdout:
            print(f"LOG: ALLIANZ TRAFİK PDF boş içerik ({filename})")
        return None
    
    tr_map = {ord('i'): 'İ', ord('ı'): 'I', ord('ğ'): 'Ğ', ord('ü'): 'Ü', ord('ş'): 'Ş', ord('ö'): 'Ö', ord('ç'): 'Ç'}
    content = clean_text(full_text).translate(tr_map).upper()
    content_raw = clean_text(full_text)
    
    # Sigortalı Adı - "Adı Soyadı : İSİM SOYİSİM"
    insured_name = "-"
    for line in lines:
        if "Adı Soyadı" in line and ":" in line:
            parts = line.split(":")
            if len(parts) > 1:
                candidate = parts[1].strip()
                # Sadece harf ve boşluk içeren kısmı al
                name_parts = []
                for word in candidate.split():
                    if word.isalpha() or word.replace(".", "").isalpha():
                        name_parts.append(word)
                    elif name_parts:  # İsimden sonra numara gelirse dur
                        break
                if name_parts:
                    insured_name = " ".join(name_parts)
                    break
    
    # Poliçe No - "Poliçe No : 0001-0210-63424647"
    policy_no = "-"
    pol_match = re.search(r'Poliçe\s*No\s*[:\s]*(\d{4}-\d{4}-\d{8})', content_raw, re.IGNORECASE)
    if pol_match:
        policy_no = pol_match.group(1)
    else:
        pol_match2 = re.search(r'POLİÇE\s*NO\s*[:\s]*([\d\-]{10,})', content)
        if pol_match2:
            policy_no = pol_match2.group(1)
    
    # Başlangıç Tarihi - "Başlangıç Tarihi : 20/01/2026 12:00"
    date = "-"
    date_match = re.search(r'Başlangıç\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content_raw, re.IGNORECASE)
    if date_match:
        date = date_match.group(1)
    
    # Plaka No - "Plaka No : 66 LL 208"
    plate = "-"
    pl_match = re.search(r'Plaka\s*No\s*[:\s]*(\d{2,3}\s*[A-ZÇĞİÖŞÜ]{1,4}\s*\d{2,5})', content_raw, re.IGNORECASE)
    if pl_match:
        plate = pl_match.group(1).replace(" ", "")
    
    # Marka - "Marka : TOFAS-FIAT (100)"
    brand = "-"
    brand_match = re.search(r'Marka\s*[:\s]*([A-ZÇĞİÖŞÜa-zçğıöşü\-]+)', content_raw)
    if brand_match:
        brand = brand_match.group(1).strip().upper()
        # Parantez içindeki kodu temizle
        brand = re.sub(r'\s*\(\d+\)', '', brand).strip()
    
    # Tutar - "Ödenecek Prim 6,865.44 TL" veya "PEŞİNAT : 20/01/2026 6,865.44 TL"
    amount = "0"
    # Önce direkt Ödenecek Prim satırını dene
    amt_match = re.search(r'Ödenecek\s*Prim\s+(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', content_raw, re.IGNORECASE)
    if amt_match:
        amount = normalize_amount_to_turkish(amt_match.group(1))
    else:
        # Alternatif: PEŞİNAT satırından çek (tarihten sonra tutar)
        amt_match2 = re.search(r'PEŞİNAT\s*:?\s*\d{2}/\d{2}/\d{4}\s+(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', content_raw)
        if amt_match2:
            amount = normalize_amount_to_turkish(amt_match2.group(1))
        else:
            amount = extract_amount(content)
    
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": "-", "POLİÇE NO": policy_no, "TÜR": "TRAFİK", "PLAKA": plate, "MARKA": brand, "TUTAR": amount, "ŞİRKET": "ALLIANZ"}

def process_allianz_kasko(pdf_path, filename):
    """Allianz Kasko Poliçesi - Genişletilmiş Kasko"""
    full_text = ""
    lines = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:4]:
                text = page.extract_text()
                if text:
                    full_text += text + " "
                    lines.extend(text.split('\n'))
    except Exception as e:
        if sys.stdout:
            print(f"LOG: ALLIANZ KASKO PDF okuma hatası ({filename}): {type(e).__name__}")
        return None
    
    if not full_text.strip():
        if sys.stdout:
            print(f"LOG: ALLIANZ KASKO PDF boş içerik ({filename})")
        return None
    
    tr_map = {ord('i'): 'İ', ord('ı'): 'I', ord('ğ'): 'Ğ', ord('ü'): 'Ü', ord('ş'): 'Ş', ord('ö'): 'Ö', ord('ç'): 'Ç'}
    content = clean_text(full_text).translate(tr_map).upper()
    content_raw = clean_text(full_text)
    
    # Sigortalı Adı - Farklı formatlar
    insured_name = "-"
    # Format 1: "Sigortalı Adı/Unvanı : Tarkan Şahin"
    name_match = re.search(r'Sigortalı\s*Adı/Unvanı\s*[:\s]*([A-ZÇĞİÖŞÜa-zçğıöşü\s\.]+?)(?=\s*TCKN|T\.C\.|VKN|\d{10})', content_raw)
    if name_match:
        insured_name = name_match.group(1).strip()
    else:
        # Format 2: "Sayın Tarkan Şahin ,"
        sayin_match = re.search(r'Sayın\s+([A-ZÇĞİÖŞÜa-zçğıöşü\s\.]+?)\s*[,\.]', content_raw)
        if sayin_match:
            insured_name = sayin_match.group(1).strip()
    
    # Poliçe No - "Poliçe No: 0001-0210-63400081"
    policy_no = "-"
    pol_match = re.search(r'Poliçe\s*No[:\s]*(\d{4}-\d{4}-\d{8})', content_raw, re.IGNORECASE)
    if pol_match:
        policy_no = pol_match.group(1)
    else:
        # Alternatif format
        pol_match2 = re.search(r"no'lu\s*Allianz\s*Kasko.*?(\d{4}-\d{4}-\d{8})", content_raw, re.IGNORECASE)
        if pol_match2:
            policy_no = pol_match2.group(1)
        else:
            pol_match3 = re.search(r'(\d{4}-\d{4}-\d{8})', content_raw)
            if pol_match3:
                policy_no = pol_match3.group(1)
    
    # Başlangıç Tarihi - "Başlangıç Tarihi : 03/01/2026 12:00"
    date = "-"
    date_match = re.search(r'Başlangıç\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content_raw, re.IGNORECASE)
    if date_match:
        date = date_match.group(1)
    
    # Plaka No - "Plaka No : 34 HSB 518"
    plate = "-"
    pl_match = re.search(r'Plaka\s*No\s*[:\s]*(\d{2,3}\s*[A-ZÇĞİÖŞÜ]{1,4}\s*\d{2,5})', content_raw, re.IGNORECASE)
    if pl_match:
        plate = pl_match.group(1).replace(" ", "")
    else:
        # Alternatif: "34 HSB 518 plakalı" formatı
        pl_match2 = re.search(r'(\d{2}\s*[A-ZÇĞİÖŞÜ]{2,4}\s*\d{2,4})\s*plakalı', content_raw, re.IGNORECASE)
        if pl_match2:
            plate = pl_match2.group(1).replace(" ", "")
    
    # Marka - "Marka : VOLKSWAGEN (153)"
    brand = "-"
    brand_match = re.search(r'Marka\s*[:\s]*([A-ZÇĞİÖŞÜa-zçğıöşü\-]+)', content_raw)
    if brand_match:
        brand = brand_match.group(1).strip().upper()
        brand = re.sub(r'\s*\(\d+\)', '', brand).strip()
    else:
        # Alternatif: "VOLKSWAGEN (153) marka" formatı
        brand_match2 = re.search(r'([A-ZÇĞİÖŞÜ]+)\s*\(\d+\)\s*marka', content_raw, re.IGNORECASE)
        if brand_match2:
            brand = brand_match2.group(1).strip().upper()
    
    # Tutar - "ÖDENECEK PRİM : 21,372.17 TL" veya "Brüt Prim : 21,372.17 TL"
    amount = "0"
    amt_match = re.search(r'ÖDENECEK\s*PRİM\s*[:\s]*([\d\.,]+)\s*TL', content_raw, re.IGNORECASE)
    if amt_match:
        amount = normalize_amount_to_turkish(amt_match.group(1))
    else:
        amt_match2 = re.search(r'Brüt\s*Prim\s*[:\s]*([\d\.,]+)\s*TL', content_raw, re.IGNORECASE)
        if amt_match2:
            amount = normalize_amount_to_turkish(amt_match2.group(1))
        else:
            amt_match3 = re.search(r'Toplam\s*Prim\s*[:\s]*([\d\.,]+)\s*TL', content_raw, re.IGNORECASE)
            if amt_match3:
                amount = normalize_amount_to_turkish(amt_match3.group(1))
            else:
                amount = extract_amount(content)
    
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": "-", "POLİÇE NO": policy_no, "TÜR": "KASKO", "PLAKA": plate, "MARKA": brand, "TUTAR": amount, "ŞİRKET": "ALLIANZ"}

def process_seyahat(pdf_path, filename):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]: text += page.extract_text() + " || "
    except: return None
    content = clean_text(text)
    insured_name = "-"
    name_match = re.search(r'Sigortalının\s*Adı\s*Soyadı\s*[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*(?:Sigortalının\s*Adresi|Adres|Kimlik|RİSK))', content, re.IGNORECASE)
    if name_match: insured_name = name_match.group(1).strip()
    date = "-"
    d_match = re.search(r'(?:Başlangıç|Tanzim)\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if d_match: date = d_match.group(1)
    policy_no = "-"
    pol = re.search(r'Poliçe\s*No\s*[:\s]*(\d{7,})', content, re.IGNORECASE)
    if pol: policy_no = pol.group(1)
    cust_no = "-"
    cust = re.search(r'Müşteri\s*No\s*[:\s]*(\d{6,15})', content, re.IGNORECASE)
    if cust: cust_no = cust.group(1)
    amount = "0"
    amount_match = re.search(r'Ödenecek\s*Prim\s*[:\s]*([\d,]+)', content, re.IGNORECASE)
    if amount_match: amount = amount_match.group(1) + " EUR"
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": "SEYAHAT", "PLAKA": "-", "MARKA": "-", "TUTAR": amount, "ŞİRKET": "AXA"}

def process_isyeri(pdf_path, filename):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]: text += page.extract_text() + " || "
    except: return None
    content = clean_text(text)
    insured_name = "-"
    name_match = re.search(r'Sigortalının\s*Adı\s*Soyadı\s*[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*Sigortalının\s*Adresi)', content, re.IGNORECASE)
    if name_match: insured_name = name_match.group(1).strip()
    date = "-"
    d_match = re.search(r'(?:Başlangıç|Tanzim)\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if d_match: date = d_match.group(1)
    policy_no = "-"
    pol = re.search(r'Poliçe\s*No\s*[:\s]*(\d{7,})', content, re.IGNORECASE)
    if pol: policy_no = pol.group(1)
    cust_no = "-"
    cust = re.search(r'Müşteri\s*No\s*[:\s]*(\d{6,15})', content, re.IGNORECASE)
    if cust: cust_no = cust.group(1)
    faaliyet = "-"
    f_match = re.search(r'Faaliyet\s*Konusu\s*[:\s]*([A-ZÇĞİÖŞÜ\s]+?)(?=\s*Yapı\s*Tarzı)', content, re.IGNORECASE)
    if f_match: faaliyet = f_match.group(1).strip()
    amount = extract_amount(content)
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": "İŞYERİ", "PLAKA": "-", "MARKA": faaliyet, "TUTAR": amount, "ŞİRKET": "AXA"}

def process_nakliyat(pdf_path, filename):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]: text += page.extract_text() + " || "
    except: return None
    content = clean_text(text)
    insured_name = "-"
    name_match = re.search(r'Sigortalının\s*Adı\s*Soyadı\s*[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*Sigortalının\s*Adresi)', content, re.IGNORECASE)
    if name_match: insured_name = name_match.group(1).strip()
    date = "-"
    d_match = re.search(r'(?:Başlangıç|Tanzim)\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if d_match: date = d_match.group(1)
    policy_no = "-"
    pol = re.search(r'Poliçe\s*No\s*[:\s]*(\d{7,})', content, re.IGNORECASE)
    if pol: policy_no = pol.group(1)
    cust_no = "-"
    cust = re.search(r'Müşteri\s*No\s*[:\s]*(\d{6,15})', content, re.IGNORECASE)
    if cust: cust_no = cust.group(1)
    plate = "-"
    pl_match = re.search(r'(?:Kamyon|Çekici|Araç)\s*Plakası\s*[:\s]*([0-9]{2}\s*[A-Z]{1,4}\s*\d{2,5})', content, re.IGNORECASE)
    if pl_match: plate = pl_match.group(1).replace(" ", "")
    amount = extract_amount(content)
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": "NAKLİYAT", "PLAKA": plate, "MARKA": "-", "TUTAR": amount, "ŞİRKET": "AXA"}

def process_konut(pdf_path, filename):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]: text += page.extract_text() + " || "
    except: return None
    content = clean_text(text)
    insured_name = "-"
    name_match = re.search(r'Sigortalının\s*Adı\s*Soyadı\s*[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*Sigortalının\s*Adresi)', content, re.IGNORECASE)
    if name_match: insured_name = name_match.group(1).strip()
    if insured_name == "-" or len(insured_name) < 3:
        sm = re.search(r'Sayın\s+([A-ZÇĞİÖŞÜ\s]{3,50})', content)
        if sm: insured_name = sm.group(1).strip()
    date = "-"
    d_match = re.search(r'(?:Başlangıç|Tanzim)\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if d_match: date = d_match.group(1)
    policy_no = "-"
    pol = re.search(r'Poliçe\s*No\s*[:\s]*(\d{7,})', content, re.IGNORECASE)
    if pol: policy_no = pol.group(1)
    cust_no = "-"
    cust = re.search(r'Müşteri\s*No\s*[:\s]*(\d{6,15})', content, re.IGNORECASE)
    if cust: cust_no = cust.group(1)
    amount = extract_amount(content)
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": "EVİM", "PLAKA": "-", "MARKA": "-", "TUTAR": amount, "ŞİRKET": "AXA"}

def process_saglik(pdf_path, filename):
    text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages[:3]: text += page.extract_text() + " "
    except: return None
    content = clean_text(text)
    date = "-"
    date_match = re.search(r'(?:BAŞLANGIÇ|TANZİM)\s*TARİHİ.*?(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if date_match: date = date_match.group(1)
    policy_no = "-"
    pol_match = re.search(r'Poliçe\s*No\s*[:\-\s]*(\d{7,})', content, re.IGNORECASE)
    if pol_match: policy_no = pol_match.group(1)
    else:
        f_num = re.search(r'(\d{7,})', filename)
        if f_num: policy_no = f_num.group(1)
    insured_name = "-"
    cust_no = "-"
    table_match = re.search(r'(\d{7,})\s+([A-ZÇĞİÖŞÜ\s]{3,40})\s+(?:KE|EŞ|ÇOCUK)', content)
    if table_match:
        raw_no = table_match.group(1)
        if "6552" not in raw_no:
            cust_no = raw_no
            insured_name = table_match.group(2).strip()
    if insured_name == "-":
        lbl_match = re.search(r'(?:ADI\s*SOYADI|SİGORTALI)\s*[:]*\s*([A-ZÇĞİÖŞÜ\s]{3,40})(?=\s+(?:ADRES|TELEFON))', content, re.IGNORECASE)
        if lbl_match: insured_name = lbl_match.group(1).strip()
    blacklist = ["ADRES", "TELEFON", "MÜŞTERİ", "ACENTE", "SİGORTA", "İSTANBUL", "TÜRKİYE", "NO:"]
    if any(x in insured_name for x in blacklist):
        for bad in blacklist: insured_name = insured_name.replace(bad, "")
    amount = extract_amount(content)
    return {"SİGORTALI": insured_name.strip(), "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": "SAĞLIK", "PLAKA": "-", "MARKA": "-", "TUTAR": amount, "ŞİRKET": "AXA"}

def process_dask(pdf_path, filename):
    text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages[:2]: text += page.extract_text() + " "
    except: return None
    content = clean_text(text)
    
    # SİGORTA ETTİREN BİLGİLERİ altındaki Adı Soyadı
    insured_name = "-"
    name_match = re.search(r'SİGORTA\s*ETTİREN\s*BİLGİLERİ.*?Adı\s*Soyadı[/:]?\s*Unvanı?\s*[:\s]*([A-ZÇĞİÖŞÜ\.,\s]{3,80})(?=\s*(?:TCKN|VKN|Cep|Sabit|E-posta))', content, re.IGNORECASE | re.DOTALL)
    if name_match: insured_name = name_match.group(1).strip()
    
    date = "-"
    date_match = re.search(r'Başlangıç\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if date_match: date = date_match.group(1)
    
    # Sigorta Şirketi Poliçe No (SIGORTACI / ARACI BİLGİLERİ kısmındaki)
    policy_no = "-"
    sirket_pol = re.search(r'Sigorta\s*Şirketi\s*Poliçe\s*No\s*[:\s]*(\d+)', content, re.IGNORECASE)
    if sirket_pol: policy_no = sirket_pol.group(1)
    
    amount = extract_amount(content)
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": "-", "POLİÇE NO": policy_no, "TÜR": "DASK", "PLAKA": "-", "MARKA": "-", "TUTAR": amount, "ŞİRKET": "AXA"}

def process_vehicle(pdf_path, filename, p_type):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]: text += page.extract_text() + " || "
    except: return None
    content = clean_text(text)
    insured_name = "-"
    # İki nokta olsun ya da olmasın, ismi yakala
    name_match = re.search(r'Sigortalının\s*Adı\s*Soyadı\s*[:\s]+([A-ZÇĞİÖŞÜ\s\.\-]+?)(?=\s*(?:Sigortalının\s*Adresi|Adres|Kimlik|Vergi))', text.replace("||", " "), re.IGNORECASE)
    if name_match: 
        insured_name = re.sub(r'[\|:.]', '', name_match.group(1)).strip()
        # Sadece "L" gibi tek harf kalmışsa, dosya adından kullan
        if len(insured_name) < 3: insured_name = "-"
    date = "-"
    date_match = re.search(r'Başlangıç\s*Tarihi.*?(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if date_match: date = date_match.group(1)
    cust_no = "-"
    cust_match = re.search(r'Müşteri\s*No\s*[:\s]*(\d{5,15})', content, re.IGNORECASE)
    if cust_match: cust_no = cust_match.group(1)
    policy_no = "-"
    pol_match = re.search(r'(?<!Eski\s)Poli[çc]e\s*No\s*[:\s]*(\d{8,9})', content, re.IGNORECASE)
    if pol_match: policy_no = pol_match.group(1)
    plate = "-"
    plate_match = re.search(r'Plaka\s*No.*?\s*([0-9]{2}\s*[A-Z]{1,5}\s*[0-9]{2,5})', content, re.IGNORECASE)
    if plate_match: plate = plate_match.group(1).replace(" ", "")
    brand = "-"
    brand_match = re.search(r'Marka\s*[:\s]*([A-ZÇĞİÖŞÜ\s\(\)\-]{3,30})(?=\s*(?:Model|Tipi|Kullanım))', text.replace("||", " "), re.IGNORECASE)
    if brand_match:
        raw = brand_match.group(1).strip()
        brand = re.sub(r'MARKA', '', raw, flags=re.IGNORECASE).strip()
        if "SİGORTA" in brand: brand = "-"
    amount = extract_amount(content)
    return {"SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no, "POLİÇE NO": policy_no, "TÜR": p_type, "PLAKA": plate, "MARKA": brand, "TUTAR": amount, "ŞİRKET": "AXA"}

# ==============================================================================
# 🚀 ANA ÇALIŞTIRMA BLOĞU
# ==============================================================================
def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Eksik parametre."}))
        return
    
    # --- ARAMA MODU (C# Tarafından Çağrıldığında) ---
    if sys.argv[1].upper() == "SEARCH":
        if len(sys.argv) < 3:
            print(json.dumps({"status": "error", "message": "Veritabanı yolu gerekli."}))
            return
        
        db_path = sys.argv[2]
        if not os.path.exists(db_path):
            print(json.dumps({"status": "error", "message": "Veritabanı dosyası bulunamadı!"}))
            return
        
        search_params = {}
        for i in range(3, len(sys.argv)):
            if "=" in sys.argv[i]:
                key, value = sys.argv[i].split("=", 1)
                if value.strip(): search_params[key.lower()] = value.strip()
        
        if not search_params:
            print(json.dumps({"status": "error", "message": "Arama kriteri belirtilmedi."}))
            return
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            where_conditions = []
            params = []
            
            if "musteri_no" in search_params:
                where_conditions.append("musteri_no LIKE ? AND musteri_no != '-'")
                params.append(f"%{search_params['musteri_no']}%")
            if "isim" in search_params:
                where_conditions.append("sigortali LIKE ? AND sigortali != '-'")
                params.append(f"%{search_params['isim']}%")
            if "police_no" in search_params:
                where_conditions.append("police_no LIKE ? AND police_no != '-'")
                params.append(f"%{search_params['police_no']}%")
            if "plaka" in search_params:
                where_conditions.append("plaka LIKE ? AND plaka != '-'")
                params.append(f"%{search_params['plaka']}%")
            if "tarih_baslangic" in search_params and "tarih_bitis" in search_params:
                where_conditions.append("tarih BETWEEN ? AND ? AND tarih != '-'")
                params.extend([search_params['tarih_baslangic'], search_params['tarih_bitis']])
            elif "tarih" in search_params:
                where_conditions.append("tarih LIKE ? AND tarih != '-'")
                params.append(f"%{search_params['tarih']}%")
            if "tur" in search_params:
                where_conditions.append("tur LIKE ?")
                params.append(f"%{search_params['tur']}%")
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            query = f"""
            SELECT sigortali, tarih, musteri_no, police_no, tur, sirket, plaka, marka, tutar, aciklama
            FROM policeler 
            WHERE {where_clause}
            ORDER BY kayit_tarihi DESC
            LIMIT 100
            """
            cursor.execute(query, params)
            results = cursor.fetchall()
            conn.close()
            
            data = []
            for row in results:
                data.append({
                    'SİGORTALI': row[0], 'TARİH': row[1], 'MÜŞTERİ NO': row[2], 'POLİÇE NO': row[3],
                    'TÜR': row[4], 'ŞİRKET': row[5], 'PLAKA': row[6], 'MARKA': row[7], 
                    'TUTAR': row[8], 'AÇIKLAMA': row[9]
                })
            
            print(json.dumps({"status": "success", "count": len(data), "data": data, "message": f"{len(data)} sonuç bulundu."}))
            
        except Exception as e:
            print(json.dumps({"status": "error", "message": f"Sorgu hatası: {str(e)}"}))
        return

    # --- NORMAL MOD - PDF İŞLEME ve KAYIT ---
    if len(sys.argv) < 4:
        print(json.dumps({"status": "error", "message": "Eksik parametre. Kullanım: engine.exe <Kaynak> <Çıktı> <Kullanıcı>"}))
        return

    source_folder = sys.argv[1]
    output_folder = sys.argv[2]
    user_name = sys.argv[3]
    excel_name = "POLİÇELER.xlsx"
    excel_path = os.path.join(output_folder, excel_name)
    # 4. parametre varsa (C# tarafından gönderilen DB yolu), onu kullan
    if len(sys.argv) >= 5:
        db_path = sys.argv[4]
    else:
        db_name = "POLICELER.db"
        db_path = os.path.join(output_folder, db_name)
    
    if not init_database(db_path):
        print(json.dumps({"status": "error", "message": "Veritabanı oluşturulamadı!"}))
        return
    
    if not os.path.exists(source_folder):
        print(json.dumps({"status": "error", "message": "Kaynak klasör bulunamadı!"}))
        return

    # 1. Mevcut Verileri Oku
    existing_policies = set()
    existing_records = set()  # SİGORTALI+TARİH için
    df_existing_master = pd.DataFrame()
    if os.path.exists(excel_path):
        try:
            df_existing_master = pd.read_excel(excel_path)
            if "POLİÇE NO" in df_existing_master.columns:
                for idx, row in df_existing_master.iterrows():
                    p_no = str(row.get("POLİÇE NO", "")).strip()
                    if p_no and p_no not in ("-", "nan", "None"):
                        existing_policies.add(p_no)
                    # Alternatif kontrol: SİGORTALI + TARİH + TÜR kombinasyonu
                    sigortali = str(row.get("SİGORTALI", "")).strip()
                    tarih = str(row.get("TARİH", "")).strip()
                    tur = str(row.get("TÜR", "")).strip()
                    if sigortali and tarih and tur:
                        existing_records.add(f"{sigortali}_{tarih}_{tur}")
        except Exception as e:
            if sys.stdout: print(f"LOG: Excel okuma uyarısı: {str(e)}", flush=True)

    # 2. PDF'leri İşle
    files = [f for f in os.listdir(source_folder) if f.lower().endswith('.pdf')]
    current_batch_data = []

    for file in files:
        file_path = os.path.join(source_folder, file)
        doc_type = identify_policy_type(file_path)
        data = None

        try:
            if doc_type == "TRAFİK_HDI": data = process_hdi_trafik(file_path, file)
            elif doc_type == "TRAFİK_HDI_YENI": data = hdi_yeni_police(file_path, file)
            elif doc_type == "TRAFİK_ETHICA": data = process_ethica_trafik(file_path, file)
            elif doc_type == "TRAFİK_SOMPO": data = process_sompo_trafik(file_path, file)
            elif doc_type == "TRAFİK_QUICK": data = process_quick_trafik(file_path, file)
            elif doc_type == "TRAFİK_DOĞA": data = process_doga_trafik(file_path, file)
            elif doc_type == "TRAFİK_HEPİYİ": data = process_hepiyi_trafik(file_path, file)
            elif doc_type == "TRAFİK_RAY": data = process_ray_trafik(file_path, file)
            elif doc_type == "TRAFİK_ALLIANZ": data = process_allianz_trafik(file_path, file)
            elif doc_type == "KASKO_ALLIANZ": data = process_allianz_kasko(file_path, file)
            elif doc_type == "SEYAHAT": data = process_seyahat(file_path, file)
            elif doc_type == "SAĞLIK": data = process_saglik(file_path, file)
            elif doc_type == "EVİM": data = process_konut(file_path, file)
            elif doc_type == "NAKLİYAT": data = process_nakliyat(file_path, file)
            elif doc_type == "İŞYERİ": data = process_isyeri(file_path, file)
            elif doc_type == "DASK": data = process_dask(file_path, file)
            elif doc_type == "TRAFİK": data = process_vehicle(file_path, file, "TRAFİK")
            elif doc_type == "KASKO": data = process_vehicle(file_path, file, "KASKO")
            else: data = {"SİGORTALI": file, "TÜR": "TANIMSIZ", "TUTAR": "-", "ŞİRKET": "-", "POLİÇE NO": "-", "TARİH": "-", "MÜŞTERİ NO": "-", "PLAKA": "-", "MARKA": "-"}

            if data:
                if data.get('SİGORTALI') == "-" or data.get('SİGORTALI') is None:
                    data['SİGORTALI'] = file.replace(".pdf", "")[:25]
                data["AÇIKLAMA"] = user_name
                p_no = str(data.get('POLİÇE NO', '')).strip()
                
                # Duplikasyon kontrolü 1: POLİÇE NO ile
                if p_no and p_no not in ("-", "nan", "None") and p_no in existing_policies:
                    if sys.stdout: print(f"LOG:{data['SİGORTALI']} - {data['TÜR']} -> MEVCUT (POLİÇE NO: {p_no})", flush=True)
                    continue
                
                # Duplikasyon kontrolü 2: SİGORTALI + TARİH + TÜR ile (poliçe no yoksa)
                sigortali = str(data.get('SİGORTALI', '')).strip()
                tarih = str(data.get('TARİH', '')).strip()
                tur = str(data.get('TÜR', '')).strip()
                record_key = f"{sigortali}_{tarih}_{tur}"
                if record_key in existing_records:
                    if sys.stdout: print(f"LOG:{data['SİGORTALI']} - {data['TÜR']} -> MEVCUT (İçerik)", flush=True)
                    continue
                
                # Aynı batch içinde tekrar kontrolü
                if p_no and p_no not in ("-", "nan", "None"):
                    batch_has_duplicate = any(str(item.get('POLİÇE NO', '')).strip() == p_no for item in current_batch_data)
                    if batch_has_duplicate:
                        if sys.stdout: print(f"LOG:{data['SİGORTALI']} - {data['TÜR']} -> TEKRAR (Batch)", flush=True)
                        continue
                    existing_policies.add(p_no)
                
                # Batch içinde içerik kontrolü
                batch_has_content = any(f"{str(item.get('SİGORTALI', '')).strip()}_{str(item.get('TARİH', '')).strip()}_{str(item.get('TÜR', '')).strip()}" == record_key for item in current_batch_data)
                if batch_has_content:
                    if sys.stdout: print(f"LOG:{data['SİGORTALI']} - {data['TÜR']} -> TEKRAR (İçerik Batch)", flush=True)
                    continue
                
                existing_records.add(record_key)
                current_batch_data.append(data)
                if sys.stdout: print(f"LOG:{data['SİGORTALI']} - {data['TÜR']} ({data['TUTAR']}) -> LİSTEYE ALINDI", flush=True)
        except Exception as e:
            if sys.stdout: print(f"LOG:{file} -> HATA: {str(e)}", flush=True)
            continue

    # 3. Kaydet
    if current_batch_data:
        df_new_entries = pd.DataFrame(current_batch_data)
        bad_words = ["Sigortalının", "Adı", "Soyadı", "Adresi", ":", "Müşteri", "Unvanı", "NO", "ACENTE", "Sigc", "Sayın"]
        if "SİGORTALI" in df_new_entries.columns:
            for bad in bad_words:
                 df_new_entries["SİGORTALI"] = df_new_entries["SİGORTALI"].astype(str).str.replace(bad, "", regex=True, flags=re.IGNORECASE).str.strip()

        cols_order = ["SİGORTALI", "TARİH", "MÜŞTERİ NO", "POLİÇE NO", "TÜR", "ŞİRKET", "PLAKA", "MARKA", "TUTAR", "AÇIKLAMA", "REFERANS", "İLETİŞİM"]
        for c in cols_order:
            if c not in df_new_entries.columns: df_new_entries[c] = "-"
        df_new_entries = df_new_entries[cols_order]

        try:
            if not df_existing_master.empty: df_final = pd.concat([df_existing_master, df_new_entries], ignore_index=True)
            else: df_final = df_new_entries
            
            # Sıra numarası ekle (başlık hariç, ilk PDF = 1)
            df_final.insert(0, 'SIRA', range(1, len(df_final) + 1))
            
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name="TÜM POLİÇELER")
                ws = writer.sheets["TÜM POLİÇELER"]
                
                # Tüm sütunları içeriğe göre otomatik ayarla
                column_widths = {
                    'A': 8,   # SIRA - yeni sütun
                    'B': 35,  # SİGORTALI - uzun isimler için
                    'C': 12,  # TARİH
                    'D': 15,  # MÜŞTERİ NO
                    'E': 18,  # POLİÇE NO
                    'F': 12,  # TÜR
                    'G': 12,  # ŞİRKET
                    'H': 15,  # PLAKA
                    'I': 20,  # MARKA
                    'J': 15,  # TUTAR
                    'K': 15,  # AÇIKLAMA
                    'L': 15,  # REFERANS
                    'M': 15   # İLETİŞİM
                }
                
                for col, width in column_widths.items():
                    ws.column_dimensions[col].width = width

            db_added = insert_police_data(db_path, current_batch_data)
            print(json.dumps({
                "status": "success", "added": len(df_new_entries), "db_added": db_added,
                "message": f"{len(df_new_entries)} yeni kayıt eklendi.\nExcel: Tek Liste Güncellendi.\nSQLite: Güncellendi.",
                "path": excel_path, "db_path": db_path
            }))
        except Exception as e:
            print(json.dumps({"status": "error", "message": f"Dosya yazma hatası: {str(e)}"}))
    else:
        print(json.dumps({"status": "success", "added": 0, "message": "Eklenecek yeni poliçe bulunamadı."}))

if __name__ == "__main__":
    main()