#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🏢 AXA Sigorta PDF Parser Modülü
================================
AXA poliçelerini okuyan, veri çıkaran ve komisyon hesaplayan modül.
Desteklenen türler: Seyahat, İşyeri, Nakliyat, Konut/Evim, Sağlık, DASK, Trafik, Kasko
"""

import os
import re
import sys
import sqlite3
import pdfplumber
from datetime import datetime
from PyPDF2 import PdfReader

# ==============================================================================
# 🛠️ YARDIMCI FONKSİYONLAR
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
    
    currency = ""
    if "EUR" in amount_str:
        currency = " EUR"
        amount_str = amount_str.replace("EUR", "").strip()
    
    amount_str = amount_str.replace(" ", "")
    comma_count = amount_str.count(',')
    dot_count = amount_str.count('.')
    last_comma_pos = amount_str.rfind(',')
    last_dot_pos = amount_str.rfind('.')
    
    if comma_count >= 1 and last_dot_pos > last_comma_pos and last_dot_pos != -1:
        amount_str = amount_str.replace(',', '').replace('.', ',')
    elif dot_count == 1 and comma_count == 0:
        parts = amount_str.split('.')
        if len(parts) > 1 and len(parts[1]) <= 2:
            amount_str = amount_str.replace('.', ',')
    
    if ',' in amount_str:
        parts = amount_str.split(',')
        integer_part = parts[0].replace('.', '')
        decimal_part = parts[1] if len(parts) > 1 else '00'
        
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
    """Tutar çeker ve Türk formatına çevirir."""
    patterns = [
        r'ÖDENECEK\s*PRİM\s*[:\s]*([\d\.,]+)',
        r'TOPLAM\s*PRİM\s*[:\s]*([\d\.,]+)',
        r'BRÜT\s*PRİM\s*[:\s]*([\d\.,]+)',
        r'GENEL\s*TOPLAM\s*[:\s]*([\d\.,]+)',
        r'Poliçe\s*Primi\s*[:\s]*([\d\.,]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return normalize_amount_to_turkish(match.group(1))
    
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

def parse_turkish_amount(amount_str):
    """Türk formatındaki tutarı float'a çevirir: 1.234,56 -> 1234.56"""
    if not amount_str or amount_str == "-" or amount_str == "0":
        return 0.0
    
    # EUR gibi para birimlerini kaldır
    amount_str = re.sub(r'[A-Za-z\s]', '', amount_str)
    
    # Türk formatı: 1.234,56
    amount_str = amount_str.replace('.', '').replace(',', '.')
    
    try:
        return float(amount_str)
    except:
        return 0.0

# ==============================================================================
# 🔍 AXA TÜR TESPİTİ
# ==============================================================================

def identify_axa_policy_type(pdf_path):
    """PDF içeriğinden AXA poliçe türünü belirler."""
    text_raw = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:3]:
                t = page.extract_text()
                if t: text_raw += t + " "
    except:
        try:
            reader = PdfReader(pdf_path)
            for page in reader.pages[:3]:
                t = page.extract_text()
                if t: text_raw += t + " "
        except:
            return "BILINMIYOR"
    
    text_upper = text_raw.upper()
    
    # Öncelik sırasına göre kontrol
    if "İŞYERİM" in text_upper or "ISYERIM" in text_upper:
        return "İŞYERİ"
    if "NAKLİYAT" in text_upper or "EMTİA" in text_upper:
        return "NAKLİYAT"
    if "SEYAHAT SİGORTASI" in text_upper or "SEYAHAT SAĞLIK" in text_upper:
        return "SEYAHAT"
    if "EVİM PAKET" in text_upper:
        return "EVİM"
    if "ZORUNLU DEPREM" in text_upper or "DASK" in text_upper:
        return "DASK"
    if "SAĞLIĞIM" in text_upper or "TAMAMLAYICI SAĞLIK" in text_upper:
        return "SAĞLIK"
    if "SAĞLIK SİGORTASI" in text_upper or "SAĞLIK POLİÇESİ" in text_upper:
        return "SAĞLIK"
    if "KASKO POLİÇESİ" in text_upper or "KASKO SİGORTASI" in text_upper:
        return "KASKO"
    if "TRAFİK SİGORTASI" in text_upper or "ZORUNLU MALİ" in text_upper:
        return "TRAFİK"
    if "KARAYOLLARI MOTORLU" in text_upper:
        return "TRAFİK"
    if "KONUT" in text_upper and "YANGIN" in text_upper:
        return "EVİM"
    if "KASKO" in text_upper and "TRAFİK" not in text_upper:
        return "KASKO"
    if "TRAFİK" in text_upper:
        return "TRAFİK"
    
    return "BILINMIYOR"

# ==============================================================================
# ⚙️ AXA PARSER FONKSİYONLARI
# ==============================================================================

def process_seyahat(pdf_path, filename):
    """Seyahat poliçesi parser."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]:
                text += page.extract_text() + " || "
    except:
        return None
    
    content = clean_text(text)
    
    insured_name = "-"
    name_match = re.search(r'Sigortalının\s*Adı\s*Soyadı\s*[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*(?:Sigortalının\s*Adresi|Adres|Kimlik|RİSK))', content, re.IGNORECASE)
    if name_match:
        insured_name = name_match.group(1).strip()
    
    date = "-"
    d_match = re.search(r'(?:Başlangıç|Tanzim)\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if d_match:
        date = d_match.group(1)
    
    policy_no = "-"
    pol = re.search(r'Poliçe\s*No\s*[:\s]*(\d{7,})', content, re.IGNORECASE)
    if pol:
        policy_no = pol.group(1)
    
    cust_no = "-"
    cust = re.search(r'Müşteri\s*No\s*[:\s]*(\d{6,15})', content, re.IGNORECASE)
    if cust:
        cust_no = cust.group(1)
    
    amount = "0"
    amount_match = re.search(r'Ödenecek\s*Prim\s*[:\s]*([\d,]+)', content, re.IGNORECASE)
    if amount_match:
        amount = amount_match.group(1) + " EUR"
    
    return {
        "SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no,
        "POLİÇE NO": policy_no, "TÜR": "SEYAHAT", "PLAKA": "-",
        "MARKA": "-", "TUTAR": amount, "ŞİRKET": "AXA"
    }

def process_isyeri(pdf_path, filename):
    """İşyeri poliçesi parser."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]:
                text += page.extract_text() + " || "
    except:
        return None
    
    content = clean_text(text)
    
    insured_name = "-"
    name_match = re.search(r'Sigortalının\s*Adı\s*Soyadı\s*[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*Sigortalının\s*Adresi)', content, re.IGNORECASE)
    if name_match:
        insured_name = name_match.group(1).strip()
    
    date = "-"
    d_match = re.search(r'(?:Başlangıç|Tanzim)\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if d_match:
        date = d_match.group(1)
    
    policy_no = "-"
    pol = re.search(r'Poliçe\s*No\s*[:\s]*(\d{7,})', content, re.IGNORECASE)
    if pol:
        policy_no = pol.group(1)
    
    cust_no = "-"
    cust = re.search(r'Müşteri\s*No\s*[:\s]*(\d{6,15})', content, re.IGNORECASE)
    if cust:
        cust_no = cust.group(1)
    
    faaliyet = "-"
    f_match = re.search(r'Faaliyet\s*Konusu\s*[:\s]*([A-ZÇĞİÖŞÜ\s]+?)(?=\s*Yapı\s*Tarzı)', content, re.IGNORECASE)
    if f_match:
        faaliyet = f_match.group(1).strip()
    
    amount = extract_amount(content)
    
    return {
        "SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no,
        "POLİÇE NO": policy_no, "TÜR": "İŞYERİ", "PLAKA": "-",
        "MARKA": faaliyet, "TUTAR": amount, "ŞİRKET": "AXA"
    }

def process_nakliyat(pdf_path, filename):
    """Nakliyat poliçesi parser."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]:
                text += page.extract_text() + " || "
    except:
        return None
    
    content = clean_text(text)
    
    insured_name = "-"
    name_match = re.search(r'Sigortalının\s*Adı\s*Soyadı\s*[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*Sigortalının\s*Adresi)', content, re.IGNORECASE)
    if name_match:
        insured_name = name_match.group(1).strip()
    
    date = "-"
    d_match = re.search(r'(?:Başlangıç|Tanzim)\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if d_match:
        date = d_match.group(1)
    
    policy_no = "-"
    pol = re.search(r'Poliçe\s*No\s*[:\s]*(\d{7,})', content, re.IGNORECASE)
    if pol:
        policy_no = pol.group(1)
    
    cust_no = "-"
    cust = re.search(r'Müşteri\s*No\s*[:\s]*(\d{6,15})', content, re.IGNORECASE)
    if cust:
        cust_no = cust.group(1)
    
    plate = "-"
    pl_match = re.search(r'(?:Kamyon|Çekici|Araç)\s*Plakası\s*[:\s]*([0-9]{2}\s*[A-Z]{1,4}\s*\d{2,5})', content, re.IGNORECASE)
    if pl_match:
        plate = pl_match.group(1).replace(" ", "")
    
    amount = extract_amount(content)
    
    return {
        "SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no,
        "POLİÇE NO": policy_no, "TÜR": "NAKLİYAT", "PLAKA": plate,
        "MARKA": "-", "TUTAR": amount, "ŞİRKET": "AXA"
    }

def process_konut(pdf_path, filename):
    """Konut/Evim poliçesi parser."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]:
                text += page.extract_text() + " || "
    except:
        return None
    
    content = clean_text(text)
    
    insured_name = "-"
    name_match = re.search(r'Sigortalının\s*Adı\s*Soyadı\s*[:\s]*([A-ZÇĞİÖŞÜ\s\.]+?)(?=\s*Sigortalının\s*Adresi)', content, re.IGNORECASE)
    if name_match:
        insured_name = name_match.group(1).strip()
    
    if insured_name == "-" or len(insured_name) < 3:
        sm = re.search(r'Sayın\s+([A-ZÇĞİÖŞÜ\s]{3,50})', content)
        if sm:
            insured_name = sm.group(1).strip()
    
    date = "-"
    d_match = re.search(r'(?:Başlangıç|Tanzim)\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if d_match:
        date = d_match.group(1)
    
    policy_no = "-"
    pol = re.search(r'Poliçe\s*No\s*[:\s]*(\d{7,})', content, re.IGNORECASE)
    if pol:
        policy_no = pol.group(1)
    
    cust_no = "-"
    cust = re.search(r'Müşteri\s*No\s*[:\s]*(\d{6,15})', content, re.IGNORECASE)
    if cust:
        cust_no = cust.group(1)
    
    amount = extract_amount(content)
    
    return {
        "SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no,
        "POLİÇE NO": policy_no, "TÜR": "EVİM", "PLAKA": "-",
        "MARKA": "-", "TUTAR": amount, "ŞİRKET": "AXA"
    }

def process_saglik(pdf_path, filename):
    """Sağlık poliçesi parser."""
    text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages[:3]:
            text += page.extract_text() + " "
    except:
        return None
    
    content = clean_text(text)
    
    date = "-"
    date_match = re.search(r'(?:BAŞLANGIÇ|TANZİM)\s*TARİHİ.*?(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if date_match:
        date = date_match.group(1)
    
    policy_no = "-"
    pol_match = re.search(r'Poliçe\s*No\s*[:\-\s]*(\d{7,})', content, re.IGNORECASE)
    if pol_match:
        policy_no = pol_match.group(1)
    else:
        f_num = re.search(r'(\d{7,})', filename)
        if f_num:
            policy_no = f_num.group(1)
    
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
        if lbl_match:
            insured_name = lbl_match.group(1).strip()
    
    blacklist = ["ADRES", "TELEFON", "MÜŞTERİ", "ACENTE", "SİGORTA", "İSTANBUL", "TÜRKİYE", "NO:"]
    if any(x in insured_name for x in blacklist):
        for bad in blacklist:
            insured_name = insured_name.replace(bad, "")
    
    amount = extract_amount(content)
    
    return {
        "SİGORTALI": insured_name.strip(), "TARİH": date, "MÜŞTERİ NO": cust_no,
        "POLİÇE NO": policy_no, "TÜR": "SAĞLIK", "PLAKA": "-",
        "MARKA": "-", "TUTAR": amount, "ŞİRKET": "AXA"
    }

def process_dask(pdf_path, filename):
    """DASK poliçesi parser."""
    text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages[:2]:
            text += page.extract_text() + " "
    except:
        return None
    
    content = clean_text(text)
    
    insured_name = "-"
    name_match = re.search(r'SİGORTA\s*ETTİREN\s*BİLGİLERİ.*?Adı\s*Soyadı[/:]?\s*Unvanı?\s*[:\s]*([A-ZÇĞİÖŞÜ\.,\s]{3,80})(?=\s*(?:TCKN|VKN|Cep|Sabit|E-posta))', content, re.IGNORECASE | re.DOTALL)
    if name_match:
        insured_name = name_match.group(1).strip()
    
    date = "-"
    date_match = re.search(r'Başlangıç\s*Tarihi\s*[:\s]*(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if date_match:
        date = date_match.group(1)
    
    policy_no = "-"
    sirket_pol = re.search(r'Sigorta\s*Şirketi\s*Poliçe\s*No\s*[:\s]*(\d+)', content, re.IGNORECASE)
    if sirket_pol:
        policy_no = sirket_pol.group(1)
    
    amount = extract_amount(content)
    
    return {
        "SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": "-",
        "POLİÇE NO": policy_no, "TÜR": "DASK", "PLAKA": "-",
        "MARKA": "-", "TUTAR": amount, "ŞİRKET": "AXA"
    }

def process_vehicle(pdf_path, filename, p_type="TRAFİK"):
    """Araç poliçesi parser (Trafik/Kasko)."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:2]:
                text += page.extract_text() + " || "
    except:
        return None
    
    content = clean_text(text)
    
    insured_name = "-"
    name_match = re.search(r'Sigortalının\s*Adı\s*Soyadı\s*[:\s]+([A-ZÇĞİÖŞÜ\s\.\-]+?)(?=\s*(?:Sigortalının\s*Adresi|Adres|Kimlik|Vergi))', text.replace("||", " "), re.IGNORECASE)
    if name_match:
        insured_name = re.sub(r'[\|:.]', '', name_match.group(1)).strip()
        if len(insured_name) < 3:
            insured_name = "-"
    
    date = "-"
    date_match = re.search(r'Başlangıç\s*Tarihi.*?(\d{2}/\d{2}/\d{4})', content, re.IGNORECASE)
    if date_match:
        date = date_match.group(1)
    
    cust_no = "-"
    cust_match = re.search(r'Müşteri\s*No\s*[:\s]*(\d{5,15})', content, re.IGNORECASE)
    if cust_match:
        cust_no = cust_match.group(1)
    
    policy_no = "-"
    pol_match = re.search(r'(?<!Eski\s)Poli[çc]e\s*No\s*[:\s]*(\d{8,9})', content, re.IGNORECASE)
    if pol_match:
        policy_no = pol_match.group(1)
    
    plate = "-"
    plate_match = re.search(r'Plaka\s*No.*?\s*([0-9]{2}\s*[A-Z]{1,5}\s*[0-9]{2,5})', content, re.IGNORECASE)
    if plate_match:
        plate = plate_match.group(1).replace(" ", "")
    
    brand = "-"
    brand_match = re.search(r'Marka\s*[:\s]*([A-ZÇĞİÖŞÜ\s\(\)\-]{3,30})(?=\s*(?:Model|Tipi|Kullanım))', text.replace("||", " "), re.IGNORECASE)
    if brand_match:
        raw = brand_match.group(1).strip()
        brand = re.sub(r'MARKA', '', raw, flags=re.IGNORECASE).strip()
        if "SİGORTA" in brand:
            brand = "-"
    
    amount = extract_amount(content)
    
    # Net Prim çek - AXA poliçelerinde "Net Prim" veya "Net Prim:" formatında
    net_prim = "0"
    net_match = re.search(r'Net\s*Prim\s*[:\s]*([0-9.,]+)(?:\s*TL)?', content, re.IGNORECASE)
    if net_match:
        net_prim = normalize_amount_to_turkish(net_match.group(1))
    else:
        # Alternatif format: tabloda "Net Prim" satırı
        net_match2 = re.search(r'Net\s*Prim[^0-9]*([0-9]{1,3}(?:[.,][0-9]{3})*[.,][0-9]{2})', text, re.IGNORECASE)
        if net_match2:
            net_prim = normalize_amount_to_turkish(net_match2.group(1))
    
    return {
        "SİGORTALI": insured_name, "TARİH": date, "MÜŞTERİ NO": cust_no,
        "POLİÇE NO": policy_no, "TÜR": p_type, "PLAKA": plate,
        "MARKA": brand, "TUTAR": amount, "NET_PRIM": net_prim, "ŞİRKET": "AXA"
    }

# ==============================================================================
# 💰 KOMİSYON HESAPLAMA
# ==============================================================================

def hesapla_komisyon(kisi: str, tur: str, net_prim: float):
    """
    Komisyon Hesaplama Fonksiyonu
    =============================
    
    Args:
        kisi: YAŞAR, KAMİL, TEZER, CMC
        tur: TRAFİK, KASKO, SEYAHAT, İŞYERİ, EVİM, SAĞLIK, NAKLİYAT, DASK
        net_prim: Net prim (PDF'den çekilmiş)
    
    Returns:
        dict: komisyon_orani, komisyon, odeme_orani, odenen
    
    Komisyon Oranları:
    ------------------
    1. Trafik Sigortası: %10 (herkes için)
       Net Prim × 0.10 = Komisyon
    
    2. Tezer için diğer tüm branşlar: %13
       (Kasko, İşyeri, Konut, Sağlık, Nakliye, DASK, Seyahat)
       Net Prim × 0.13 = Komisyon
    
    3. Yaşar, Kamil, CMC için diğer branşlar: %15
       (İşyeri, Konut, Sağlık, Nakliye, Kasko, DASK, Seyahat)
       Net Prim × 0.15 = Komisyon
    
    Ödeme Oranları:
    ---------------
    - Yaşar: Komisyonun %60'ı
    - Kamil, Tezer, CMC: Komisyonun %50'si
    """
    kisi_upper = kisi.upper().strip()
    tur_upper = tur.upper().strip()
    
    # KOMİSYON ORANI BELİRLEME
    # ========================
    
    # 1. Trafik Sigortası: Herkes için %10
    if tur_upper == "TRAFİK":
        komisyon_orani = 0.10
    
    # 2. DASK: Herkes için Net Prim / 7.25
    elif tur_upper == "DASK":
        komisyon_orani = 1 / 7.25  # Net Prim / 7.25
    
    # 3. Tezer için diğer tüm branşlar: %13
    elif kisi_upper == "TEZER":
        komisyon_orani = 0.13
    
    # 4. Yaşar, Kamil, CMC için diğer branşlar: %15
    else:
        komisyon_orani = 0.15
    
    # Komisyon = Net Prim × Komisyon Oranı
    komisyon = net_prim * komisyon_orani
    
    # ÖDEME ORANI BELİRLEME
    # =====================
    
    if kisi_upper == "YAŞAR":
        odeme_orani = 0.60  # Yaşar: %60
    else:
        odeme_orani = 0.50  # Kamil, Tezer, CMC: %50
    
    # Ödenen = Komisyon × Ödeme Oranı
    odenen = komisyon * odeme_orani
    
    return {
        'komisyon_orani': komisyon_orani,
        'komisyon': round(komisyon, 2),
        'odeme_orani': odeme_orani,
        'odenen': round(odenen, 2)
    }

# ==============================================================================
# 🚀 ANA İŞLEME FONKSİYONU
# ==============================================================================

def process_axa_pdf(pdf_path, filename=None):
    """
    AXA PDF'ini işle ve veri çıkar.
    
    Returns:
        dict: Poliçe verileri veya None
    """
    if filename is None:
        filename = os.path.basename(pdf_path)
    
    # Tür tespit
    policy_type = identify_axa_policy_type(pdf_path)
    
    if policy_type == "BILINMIYOR":
        return None
    
    # Parser seç ve çalıştır
    parser_map = {
        'SEYAHAT': process_seyahat,
        'İŞYERİ': process_isyeri,
        'NAKLİYAT': process_nakliyat,
        'EVİM': process_konut,
        'SAĞLIK': process_saglik,
        'DASK': process_dask,
        'TRAFİK': lambda p, f: process_vehicle(p, f, "TRAFİK"),
        'KASKO': lambda p, f: process_vehicle(p, f, "KASKO")
    }
    
    parser = parser_map.get(policy_type)
    if parser:
        return parser(pdf_path, filename)
    
    return None

# ==============================================================================
# 🧪 TEST
# ==============================================================================

if __name__ == "__main__":
    # Test komisyon hesaplama
    print("=== KOMİSYON HESAPLAMA TESTİ ===")
    
    test_cases = [
        ("YAŞAR", "TRAFİK", 1000),
        ("YAŞAR", "KASKO", 10000),
        ("KAMİL", "KASKO", 10000),
        ("TEZER", "TRAFİK", 1000),
        ("TEZER", "KASKO", 10000),
    ]
    
    for kisi, tur, net_prim in test_cases:
        result = hesapla_komisyon(kisi, tur, net_prim)
        print(f"{kisi} - {tur}: NetPrim={net_prim}, Komisyon={result['komisyon']}, Ödenen={result['odenen']}")
