#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Muhasebe - Komisyon Hesaplama, Sabitler ve Yardımcı Fonksiyonlar
"""

import os
import sys

# Parsers klasörünü path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'parsers'))


def get_application_path():
    """EXE veya script'in bulunduğu gerçek klasörü döndürür"""
    if getattr(sys, 'frozen', False):
        # PyInstaller ile oluşturulmuş EXE
        return os.path.dirname(sys.executable)
    else:
        # Normal Python script
        return os.path.dirname(os.path.abspath(__file__))


PARSER_AVAILABLE = False

try:
    # multi_parser.py'den tüm parser fonksiyonlarını al
    from multi_parser import (
        identify_policy_type,
        process_hdi_trafik,
        hdi_yeni_police,
        process_ethica_trafik,
        process_quick_trafik,
        process_sompo_trafik,
        process_doga_trafik,
        process_hepiyi_trafik,
        process_ray_trafik,
        process_vehicle,
        process_seyahat,
        process_isyeri,
        process_nakliyat,
        process_konut,
        process_saglik,
        process_dask,
        normalize_amount_to_turkish,
        clean_text
    )
    PARSER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Uyarı: multi_parser.py modülü bulunamadı: {e}")

try:
    # axa_parser'dan komisyon hesaplama fonksiyonlarını al
    from axa_parser import (
        process_axa_pdf,
        hesapla_komisyon,
        parse_turkish_amount
    )
except ImportError as e:
    print(f"⚠️ Uyarı: axa_parser.py modülü bulunamadı: {e}")
    # Varsayılan hesapla_komisyon fonksiyonu
    def hesapla_komisyon(kisi, tur, net_prim):
        """
        Komisyon Hesaplama Kuralları:
        ==============================
        Komisyon = Net Prim × Komisyon Oranı
        Ödenen = Komisyon × Ödeme Oranı

        Komisyon Oranları:
        ------------------
        - Trafik: %10 (herkes için)
        - DASK: %7.25 (herkes için)
        - Tezer için diğer branşlar (Kasko, İşyeri, Konut, Sağlık, Nakliye): %13
        - Diğer kişiler için diğer branşlar: %15

        Ödeme Oranları:
        ---------------
        - Yaşar: %60
        - Kamil, Tezer, CMC: %50
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

        # Komisyon hesaplama
        komisyon = net_prim * komisyon_orani

        # ÖDEME ORANI BELİRLEME
        # =====================
        if kisi_upper == "YAŞAR":
            odeme_orani = 0.60  # Yaşar: %60
        else:
            odeme_orani = 0.50  # Kamil, Tezer, CMC: %50

        # Ödenen komisyon hesaplama
        odenen = komisyon * odeme_orani

        return {
            'komisyon_orani': komisyon_orani,
            'komisyon': round(komisyon, 2),
            'odeme_orani': odeme_orani,
            'odenen': round(odenen, 2)
        }

    def parse_turkish_amount(val):
        try:
            return float(str(val).replace('.', '').replace(',', '.'))
        except:
            return 0.0


# Cari PDF parser fonksiyonu
def process_cari_pdf(pdf_path):
    """Cari PDF'den isim, tutar ve tarih bilgilerini çeker"""
    try:
        import pdfplumber
        import re

        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + " "

            result = {
                'isim': '',
                'tutar': 0.0,
                'tarih': ''
            }

            # Özel PDF karakterlerini temizle (cid:xxx)
            text = re.sub(r'\(cid:\d+\)', '', text)

            # İsim: "Prim Ödeyen : FERHAT AYKAÇ Müşteri No"
            isim_match = re.search(r'Prim\s*[ÖOo]deyen\s*:\s*(.+?)\s*M[üu]şteri', text, re.IGNORECASE)
            if isim_match:
                result['isim'] = isim_match.group(1).strip()

            # Tutar: "31650.-TL'lik prim tutarı" veya "8500.-TL"
            tutar_match = re.search(r'(\d+[\d.,]*)\s*\.?-?\s*TL', text)
            if tutar_match:
                tutar_str = tutar_match.group(1).replace('.', '').replace(',', '.')
                try:
                    result['tutar'] = float(tutar_str)
                except:
                    result['tutar'] = 0.0

            # Tarih: "Tahsilat Tarihi : 21.08.2025"
            tarih_match = re.search(r'Tahsilat\s*Tarihi\s*:\s*(\d{1,2}\.\d{1,2}\.\d{4})', text)
            if tarih_match:
                result['tarih'] = tarih_match.group(1)

            return result
    except Exception as e:
        print(f"Cari PDF okuma hatası: {e}")
        return None


def get_cari_data_for_month(cari_folder, ay_numarasi):
    """Belirli bir ay için cari verilerini döndür - pdf_path dahil"""
    import os

    cari_list = []

    if not os.path.exists(cari_folder):
        return cari_list

    for filename in os.listdir(cari_folder):
        if filename.lower().endswith('.pdf'):
            pdf_path = os.path.join(cari_folder, filename)
            data = process_cari_pdf(pdf_path)

            if data and data['tarih']:
                # Tarihten ay numarasını çıkar
                try:
                    parts = data['tarih'].split('.')
                    if len(parts) >= 2:
                        pdf_ay = int(parts[1])
                        if pdf_ay == ay_numarasi:
                            # PDF dosya yolunu da ekle
                            data['pdf_path'] = pdf_path
                            cari_list.append(data)
                except:
                    pass

    return cari_list


# PDF işleme fonksiyonu - tüm şirketleri destekler
def process_pdf(pdf_path, filename):
    """PDF'yi işle ve veri döndür - All.py mantığı ile"""
    if not PARSER_AVAILABLE:
        return None

    try:
        # Poliçe türünü tespit et
        policy_type = identify_policy_type(pdf_path)

        # Parser seçimi
        data = None

        if policy_type == "TRAFİK_HDI":
            data = process_hdi_trafik(pdf_path, filename)
        elif policy_type == "TRAFİK_HDI_YENI":
            data = hdi_yeni_police(pdf_path, filename)
        elif policy_type == "TRAFİK_ETHICA":
            data = process_ethica_trafik(pdf_path, filename)
        elif policy_type == "TRAFİK_QUICK":
            data = process_quick_trafik(pdf_path, filename)
        elif policy_type == "TRAFİK_SOMPO":
            data = process_sompo_trafik(pdf_path, filename)
        elif policy_type == "TRAFİK_DOĞA":
            data = process_doga_trafik(pdf_path, filename)
        elif policy_type == "TRAFİK_HEPİYİ":
            data = process_hepiyi_trafik(pdf_path, filename)
        elif policy_type == "TRAFİK_RAY":
            data = process_ray_trafik(pdf_path, filename)
        elif policy_type == "TRAFİK":
            # Genel trafik - doğrudan process_vehicle kullan
            data = process_vehicle(pdf_path, filename, "TRAFİK")
        elif policy_type == "KASKO":
            # KASKO - doğrudan process_vehicle kullan
            data = process_vehicle(pdf_path, filename, "KASKO")
        elif policy_type == "SEYAHAT":
            data = process_seyahat(pdf_path, filename)
        elif policy_type == "İŞYERİ":
            data = process_isyeri(pdf_path, filename)
        elif policy_type == "NAKLİYAT":
            data = process_nakliyat(pdf_path, filename)
        elif policy_type == "EVİM":
            data = process_konut(pdf_path, filename)
        elif policy_type == "SAĞLIK":
            data = process_saglik(pdf_path, filename)
        elif policy_type == "DASK":
            # DASK poliçesi
            data = process_dask(pdf_path, filename)
        else:
            # Bilinmeyen tür - varsayılan olarak TRAFİK kabul et
            # AXA poliçeleri için process_vehicle kullan
            data = process_vehicle(pdf_path, filename, "TRAFİK")
            if data:
                # Log'a bilinmeyen tür olarak kaydet
                print(f"⚠️ Bilinmeyen tür (TRAFİK olarak işlendi): {filename}")

        # Eğer hiçbir parser sonuç döndürmediyse
        if not data:
            return None

        # Data döndükten sonra NET_PRIM yoksa PDF'den çek
        if data and (not data.get('NET_PRIM') or data.get('NET_PRIM') == '0'):
            try:
                import pdfplumber
                import re as regex_module
                with pdfplumber.open(pdf_path) as pdf:
                    text = ""
                    # Tüm sayfaları tara (Net Prim sonraki sayfalarda olabilir)
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            text += t + " "

                    # Net Prim regex'leri
                    net_match = regex_module.search(r'Net\s*Prim\s*[:\s]*([0-9.,]+)(?:\s*TL)?', text, regex_module.IGNORECASE)
                    if net_match:
                        data['NET_PRIM'] = normalize_amount_to_turkish(net_match.group(1))
                    else:
                        # Alternatif: "Net Prim" satırında tutar
                        net_match2 = regex_module.search(r'Net\s*Prim[^0-9]*([0-9]{1,3}(?:[.,][0-9]{3})*[.,][0-9]{2})', text, regex_module.IGNORECASE)
                        if net_match2:
                            data['NET_PRIM'] = normalize_amount_to_turkish(net_match2.group(1))
            except Exception as ne:
                print(f"Net prim çekme hatası: {ne}")

        return data
    except Exception as e:
        print(f"process_pdf hatası: {e}")
        return None


# ==============================================================================
# RENKLER VE SABİTLER
# ==============================================================================

COLORS = {
    'primary': '#0f172a',
    'primary_accent': '#0d9488',
    'success': '#059669',
    'warning': '#d97706',
    'danger': '#dc2626',
    'info': '#0891b2',
    'bg_light': '#f1f5f9',
    'text_dark': '#0f172a',
    'text_light': '#ffffff',
    'sidebar': '#1e293b',
    'card': '#ffffff',
    'border': '#e2e8f0'
}

AYLAR = ['OCAK', 'ŞUBAT', 'MART', 'NİSAN', 'MAYIS', 'HAZİRAN',
         'TEMMUZ', 'AĞUSTOS', 'EYLÜL', 'EKİM', 'KASIM', 'ARALIK']

KISILER = ['YAŞAR', 'KAMİL', 'TEZER', 'CMC']

TURLER = ['TRAFİK', 'KASKO', 'DASK', 'EVİM', 'SAĞLIK', 'SEYAHAT', 'NAKLİYAT', 'İŞYERİ']

ODEME_TURLERI = ['K.KART', 'AÇIK']


def format_turkish_currency(value):
    """Sayıyı Türk formatına çevirir: 1.234,56"""
    try:
        # Python formatı: 1,234.56 → Türk formatı: 1.234,56
        formatted = f"{float(value):,.2f}"
        # Virgül → geçici, Nokta → virgül, Geçici → nokta
        return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"


def is_iptal_police(pdf_path):
    """PDF'in iptal poliçesi olup olmadığını kontrol eder"""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages[:2]:
                t = page.extract_text()
                if t:
                    text += t.upper()

            # İptal belirtileri
            iptal_keywords = [
                'İPTAL EKBELGESİ',
                'IPTAL EKBELGESI',
                'İPTAL ZEYİLNAMESİ',
                'IPTAL ZEYILNAMESI',
                'SATIŞTAN DOLAYI İPTAL',
                'SATIŞ İPTALİ',
                'POLİÇE İPTALİ',
                'POLICE IPTALI'
            ]

            for keyword in iptal_keywords:
                if keyword in text:
                    return True

            # Eksi değerli prim kontrolü (güçlü gösterge)
            import re
            eksi_prim = re.search(r'[-]\s*[\d.,]+\s*TL', text)
            if eksi_prim and ('İPTAL' in text or 'IPTAL' in text):
                return True

    except Exception as e:
        print(f"İptal kontrol hatası: {e}")

    return False
