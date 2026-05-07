#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Muhasebe - Veritabanı Yönetimi (MuhasebeDB)
"""

import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from commission import get_application_path


class MuhasebeDB:
    """Muhasebe veritabanı yönetimi sınıfı"""

    def __init__(self, db_path=None):
        if db_path is None:
            script_dir = get_application_path()
            db_path = os.path.join(script_dir, 'komisyon_veritabani.db')
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Veritabanını oluştur - AXA ve Diğer Şirketler için ayrı tablolar"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # AXA Poliçeleri Tablosu
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS komisyonlar_axa (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kisi TEXT NOT NULL,
                    ay TEXT NOT NULL,
                    yil INTEGER NOT NULL,
                    sigortali TEXT,
                    police_no TEXT UNIQUE,
                    tarih TEXT,
                    plaka TEXT,
                    tur TEXT,
                    odeme_turu TEXT DEFAULT 'K.KART',
                    kart_sahibi TEXT,
                    brut_prim REAL DEFAULT 0,
                    tramer REAL DEFAULT 0,
                    net_prim REAL DEFAULT 0,
                    komisyon_orani REAL DEFAULT 0,
                    toplam_komisyon REAL DEFAULT 0,
                    odeme_orani REAL DEFAULT 0,
                    odenen_komisyon REAL DEFAULT 0,
                    ikinci_police INTEGER DEFAULT 0,
                    iptal INTEGER DEFAULT 0,
                    notlar TEXT,
                    kayit_tarihi DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                ''')

                # Mevcut tabloya iptal sütunu ekle (migration)
                try:
                    cursor.execute("ALTER TABLE komisyonlar_axa ADD COLUMN iptal INTEGER DEFAULT 0")
                except:
                    pass  # Sütun zaten var
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_kisi_axa ON komisyonlar_axa(kisi)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ay_yil_axa ON komisyonlar_axa(ay, yil)')

                # Diğer Şirketler Tablosu
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS komisyonlar_other (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kisi TEXT NOT NULL,
                    ay TEXT NOT NULL,
                    yil INTEGER NOT NULL,
                    sigortali TEXT,
                    police_no TEXT UNIQUE,
                    tarih TEXT,
                    plaka TEXT,
                    tur TEXT,
                    odeme_turu TEXT DEFAULT 'K.KART',
                    kart_sahibi TEXT,
                    brut_prim REAL DEFAULT 0,
                    tramer REAL DEFAULT 0,
                    net_prim REAL DEFAULT 0,
                    komisyon_orani REAL DEFAULT 0,
                    toplam_komisyon REAL DEFAULT 0,
                    odeme_orani REAL DEFAULT 0,
                    odenen_komisyon REAL DEFAULT 0,
                    ikinci_police INTEGER DEFAULT 0,
                    iptal INTEGER DEFAULT 0,
                    sirket TEXT NOT NULL,
                    notlar TEXT,
                    kayit_tarihi DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                ''')

                # Mevcut tabloya iptal sütunu ekle (migration)
                try:
                    cursor.execute("ALTER TABLE komisyonlar_other ADD COLUMN iptal INTEGER DEFAULT 0")
                except:
                    pass  # Sütun zaten var
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_kisi_other ON komisyonlar_other(kisi)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_ay_yil_other ON komisyonlar_other(ay, yil)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_sirket ON komisyonlar_other(sirket)')

                # Eski 'komisyonlar' tablosundan veri migration
                try:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='komisyonlar'")
                    if cursor.fetchone():
                        # AXA kayıtlarını axa tablosuna taşı (sirket sütunu olmadan)
                        cursor.execute("""
                            INSERT OR IGNORE INTO komisyonlar_axa
                            (id, kisi, ay, yil, sigortali, police_no, tarih, plaka, tur, odeme_turu,
                             kart_sahibi, brut_prim, tramer, net_prim, komisyon_orani, toplam_komisyon,
                             odeme_orani, odenen_komisyon, ikinci_police, notlar, kayit_tarihi)
                            SELECT id, kisi, ay, yil, sigortali, police_no, tarih, plaka, tur, odeme_turu,
                                   kart_sahibi, brut_prim, COALESCE(tramer, 0), net_prim, komisyon_orani, toplam_komisyon,
                                   odeme_orani, odenen_komisyon, COALESCE(ikinci_police, 0), notlar, kayit_tarihi
                            FROM komisyonlar WHERE sirket='AXA' OR sirket IS NULL
                        """)
                        # Diğer kayıtları other tablosuna taşı
                        cursor.execute("""
                            INSERT OR IGNORE INTO komisyonlar_other
                            (id, kisi, ay, yil, sigortali, police_no, tarih, plaka, tur, odeme_turu,
                             kart_sahibi, brut_prim, tramer, net_prim, komisyon_orani, toplam_komisyon,
                             odeme_orani, odenen_komisyon, ikinci_police, sirket, notlar, kayit_tarihi)
                            SELECT id, kisi, ay, yil, sigortali, police_no, tarih, plaka, tur, odeme_turu,
                                   kart_sahibi, brut_prim, COALESCE(tramer, 0), net_prim, komisyon_orani, toplam_komisyon,
                                   odeme_orani, odenen_komisyon, COALESCE(ikinci_police, 0), sirket, notlar, kayit_tarihi
                            FROM komisyonlar WHERE sirket IS NOT NULL AND sirket != 'AXA'
                        """)
                        # Eski tabloyu yedekle
                        cursor.execute("ALTER TABLE komisyonlar RENAME TO komisyonlar_backup")
                except Exception as e:
                    print(f"Migration hatası (normal olabilir): {e}")

                conn.commit()
            return True
        except Exception as e:
            print(f"Veritabanı hatası: {e}")
            return False

    def insert_record(self, data):
        """Yeni kayıt ekle - şirkete göre doğru tabloya"""
        try:
            sirket = data.get('sirket', 'AXA').upper()
            table_name = 'komisyonlar_axa' if sirket == 'AXA' else 'komisyonlar_other'

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if table_name == 'komisyonlar_axa':
                    cursor.execute('''
                    INSERT INTO komisyonlar_axa
                    (kisi, ay, yil, sigortali, police_no, tarih, plaka, tur, odeme_turu,
                     kart_sahibi, brut_prim, tramer, net_prim, komisyon_orani, toplam_komisyon,
                     odeme_orani, odenen_komisyon, ikinci_police, iptal, notlar)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        data.get('kisi', ''),
                        data.get('ay', ''),
                        data.get('yil', datetime.now().year),
                        data.get('sigortali', ''),
                        data.get('police_no', ''),
                        data.get('tarih', ''),
                        data.get('plaka', '-'),
                        data.get('tur', ''),
                        data.get('odeme_turu', 'K.KART'),
                        data.get('kart_sahibi', ''),
                        data.get('brut_prim', 0),
                        data.get('tramer', 0),
                        data.get('net_prim', 0),
                        data.get('komisyon_orani', 0),
                        data.get('toplam_komisyon', 0),
                        data.get('odeme_orani', 0),
                        data.get('odenen_komisyon', 0),
                        data.get('ikinci_police', 0),
                        data.get('iptal', 0),
                        data.get('notlar', '')
                    ))
                else:
                    cursor.execute('''
                    INSERT INTO komisyonlar_other
                    (kisi, ay, yil, sigortali, police_no, tarih, plaka, tur, odeme_turu,
                     kart_sahibi, brut_prim, tramer, net_prim, komisyon_orani, toplam_komisyon,
                     odeme_orani, odenen_komisyon, ikinci_police, iptal, sirket, notlar)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        data.get('kisi', ''),
                        data.get('ay', ''),
                        data.get('yil', datetime.now().year),
                        data.get('sigortali', ''),
                        data.get('police_no', ''),
                        data.get('tarih', ''),
                        data.get('plaka', '-'),
                        data.get('tur', ''),
                        data.get('odeme_turu', 'K.KART'),
                        data.get('kart_sahibi', ''),
                        data.get('brut_prim', 0),
                        data.get('tramer', 0),
                        data.get('net_prim', 0),
                        data.get('komisyon_orani', 0),
                        data.get('toplam_komisyon', 0),
                        data.get('odeme_orani', 0),
                        data.get('odenen_komisyon', 0),
                        data.get('ikinci_police', 0),
                        data.get('iptal', 0),
                        sirket,
                        data.get('notlar', '')
                    ))

                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False  # Duplicate
        except Exception as e:
            print(f"Kayıt ekleme hatası: {e}")
            return False

    def get_records(self, kisi=None, yil=None, ay=None):
        """Kayıtları getir - her iki tablodan, tarih sütunundaki aya göre filtrele"""
        try:
            conn = sqlite3.connect(self.db_path)

            # Ay ismini ay numarasına çevir (OCAK=1, ŞUBAT=2, vs.)
            ay_numarasi = None
            if ay:
                ay_list = ['OCAK', 'ŞUBAT', 'MART', 'NİSAN', 'MAYIS', 'HAZİRAN',
                           'TEMMUZ', 'AĞUSTOS', 'EYLÜL', 'EKİM', 'KASIM', 'ARALIK']
                if ay.upper() in ay_list:
                    ay_numarasi = ay_list.index(ay.upper()) + 1  # 1-12 arası

            # AXA kayıtları
            query_axa = "SELECT *, 'AXA' as sirket FROM komisyonlar_axa WHERE 1=1"
            params = []

            if kisi:
                query_axa += " AND kisi = ?"
                params.append(kisi)

            df_axa = pd.read_sql_query(query_axa, conn, params=params)

            # Diğer şirket kayıtları
            query_other = "SELECT * FROM komisyonlar_other WHERE 1=1"
            params_other = []

            if kisi:
                query_other += " AND kisi = ?"
                params_other.append(kisi)

            df_other = pd.read_sql_query(query_other, conn, params=params_other)

            # Birleştir ve sırala
            df = pd.concat([df_axa, df_other], ignore_index=True)

            # Tarih sütunundan ay numarasını çıkararak filtrele
            if ay_numarasi and not df.empty and 'tarih' in df.columns:
                def extract_month(tarih):
                    """Tarih string'inden ay numarasını çıkar"""
                    if pd.isna(tarih) or not tarih:
                        return None
                    tarih_str = str(tarih).strip()
                    # DD.MM.YYYY veya DD/MM/YYYY formatı
                    if '.' in tarih_str:
                        parts = tarih_str.split('.')
                        if len(parts) >= 2:
                            try:
                                return int(parts[1])
                            except:
                                return None
                    elif '/' in tarih_str:
                        parts = tarih_str.split('/')
                        if len(parts) >= 2:
                            try:
                                return int(parts[1])
                            except:
                                return None
                    elif '-' in tarih_str:
                        # YYYY-MM-DD formatı
                        parts = tarih_str.split('-')
                        if len(parts) >= 2:
                            try:
                                return int(parts[1])
                            except:
                                return None
                    return None

                df['_ay_numarasi'] = df['tarih'].apply(extract_month)
                df = df[df['_ay_numarasi'] == ay_numarasi]
                df = df.drop(columns=['_ay_numarasi'])

            df = df.sort_values('id', ascending=False)

            conn.close()
            return df
        except Exception as e:
            print(f"Kayıt getirme hatası: {e}")
            return pd.DataFrame()

    def delete_record(self, record_id, table_type='axa'):
        """Kayıt sil - hangi tablodan olduğunu belirt"""
        try:
            table_name = 'komisyonlar_axa' if table_type == 'axa' else 'komisyonlar_other'
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
                conn.commit()
                return True
        except Exception as e:
            print(f"Silme hatası: {e}")
            return False

    def update_record(self, record_id, table_type='axa', **fields):
        """Kayıt güncelle - hangi tabloda olduğunu belirt"""
        try:
            table_name = 'komisyonlar_axa' if table_type == 'axa' else 'komisyonlar_other'
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                updates = []
                params = []
                for key, value in fields.items():
                    updates.append(f"{key} = ?")
                    params.append(value)
                params.append(record_id)
                query = f"UPDATE {table_name} SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, params)
                conn.commit()
                return True
        except Exception as e:
            print(f"Güncelleme hatası: {e}")
            return False

    def get_summary(self, kisi=None, yil=None, ay=None):
        """Özet istatistikleri getir - tarih sütunundaki aya göre filtrele"""
        try:
            # Ay ismini ay numarasına çevir
            ay_numarasi = None
            if ay:
                ay_list = ['OCAK', 'ŞUBAT', 'MART', 'NİSAN', 'MAYIS', 'HAZİRAN',
                           'TEMMUZ', 'AĞUSTOS', 'EYLÜL', 'EKİM', 'KASIM', 'ARALIK']
                if ay.upper() in ay_list:
                    ay_numarasi = ay_list.index(ay.upper()) + 1

            conn = sqlite3.connect(self.db_path)

            # AXA kayıtları
            query_axa = "SELECT tarih, brut_prim, net_prim, toplam_komisyon, odenen_komisyon FROM komisyonlar_axa WHERE 1=1"
            params = []
            if kisi:
                query_axa += " AND kisi = ?"
                params.append(kisi)

            df_axa = pd.read_sql_query(query_axa, conn, params=params)

            # Diğer şirket kayıtları
            query_other = "SELECT tarih, brut_prim, net_prim, toplam_komisyon, odenen_komisyon FROM komisyonlar_other WHERE 1=1"
            params_other = []
            if kisi:
                query_other += " AND kisi = ?"
                params_other.append(kisi)

            df_other = pd.read_sql_query(query_other, conn, params=params_other)
            conn.close()

            # Birleştir
            df = pd.concat([df_axa, df_other], ignore_index=True)

            # Tarihten ay çıkararak filtrele
            if ay_numarasi and not df.empty and 'tarih' in df.columns:
                def extract_month(tarih):
                    if pd.isna(tarih) or not tarih:
                        return None
                    tarih_str = str(tarih).strip()
                    if '.' in tarih_str:
                        parts = tarih_str.split('.')
                        if len(parts) >= 2:
                            try:
                                return int(parts[1])
                            except:
                                return None
                    elif '/' in tarih_str:
                        parts = tarih_str.split('/')
                        if len(parts) >= 2:
                            try:
                                return int(parts[1])
                            except:
                                return None
                    elif '-' in tarih_str:
                        parts = tarih_str.split('-')
                        if len(parts) >= 2:
                            try:
                                return int(parts[1])
                            except:
                                return None
                    return None

                df['_ay_numarasi'] = df['tarih'].apply(extract_month)
                df = df[df['_ay_numarasi'] == ay_numarasi]

            if df.empty:
                return {'kayit_sayisi': 0, 'toplam_brut': 0, 'toplam_net': 0, 'toplam_komisyon': 0, 'toplam_odenen': 0}

            return {
                'kayit_sayisi': len(df),
                'toplam_brut': df['brut_prim'].sum(),
                'toplam_net': df['net_prim'].sum(),
                'toplam_komisyon': df['toplam_komisyon'].sum(),
                'toplam_odenen': df['odenen_komisyon'].sum()
            }
        except Exception as e:
            print(f"Özet hatası: {e}")
            return {'kayit_sayisi': 0, 'toplam_brut': 0, 'toplam_net': 0, 'toplam_komisyon': 0, 'toplam_odenen': 0}

    def get_iptal_summary(self, kisi=None, yil=None, ay=None):
        """İptal edilen poliçelerin özet istatistiklerini getir - tarih sütunundaki aya göre filtrele"""
        try:
            # Ay ismini ay numarasına çevir
            ay_numarasi = None
            if ay:
                ay_list = ['OCAK', 'ŞUBAT', 'MART', 'NİSAN', 'MAYIS', 'HAZİRAN',
                           'TEMMUZ', 'AĞUSTOS', 'EYLÜL', 'EKİM', 'KASIM', 'ARALIK']
                if ay.upper() in ay_list:
                    ay_numarasi = ay_list.index(ay.upper()) + 1

            conn = sqlite3.connect(self.db_path)

            # AXA kayıtları - sadece iptal=1
            query_axa = "SELECT tarih, brut_prim, net_prim, toplam_komisyon, odenen_komisyon FROM komisyonlar_axa WHERE iptal = 1"
            params = []
            if kisi:
                query_axa += " AND kisi = ?"
                params.append(kisi)

            df_axa = pd.read_sql_query(query_axa, conn, params=params)

            # Diğer şirket kayıtları - sadece iptal=1
            query_other = "SELECT tarih, brut_prim, net_prim, toplam_komisyon, odenen_komisyon FROM komisyonlar_other WHERE iptal = 1"
            params_other = []
            if kisi:
                query_other += " AND kisi = ?"
                params_other.append(kisi)

            df_other = pd.read_sql_query(query_other, conn, params=params_other)
            conn.close()

            # Birleştir
            df = pd.concat([df_axa, df_other], ignore_index=True)

            # Tarihten ay çıkararak filtrele
            if ay_numarasi and not df.empty and 'tarih' in df.columns:
                def extract_month(tarih):
                    if pd.isna(tarih) or not tarih:
                        return None
                    tarih_str = str(tarih).strip()
                    if '.' in tarih_str:
                        parts = tarih_str.split('.')
                        if len(parts) >= 2:
                            try:
                                return int(parts[1])
                            except:
                                return None
                    elif '/' in tarih_str:
                        parts = tarih_str.split('/')
                        if len(parts) >= 2:
                            try:
                                return int(parts[1])
                            except:
                                return None
                    elif '-' in tarih_str:
                        parts = tarih_str.split('-')
                        if len(parts) >= 2:
                            try:
                                return int(parts[1])
                            except:
                                return None
                    return None

                df['_ay_numarasi'] = df['tarih'].apply(extract_month)
                df = df[df['_ay_numarasi'] == ay_numarasi]

            if df.empty:
                return {'kayit_sayisi': 0, 'toplam_brut': 0, 'toplam_net': 0, 'toplam_komisyon': 0, 'toplam_odenen': 0}

            return {
                'kayit_sayisi': len(df),
                'toplam_brut': df['brut_prim'].sum(),
                'toplam_net': df['net_prim'].sum(),
                'toplam_komisyon': df['toplam_komisyon'].sum(),
                'toplam_odenen': df['odenen_komisyon'].sum()
            }
        except Exception as e:
            print(f"İptal özet hatası: {e}")
            return {'kayit_sayisi': 0, 'toplam_brut': 0, 'toplam_net': 0, 'toplam_komisyon': 0, 'toplam_odenen': 0}

    def get_detailed_summary(self, kisi=None, ay=None):
        """AXA ve Diğer Şirketler için ödeme türüne göre detaylı özet"""
        def empty_summary():
            return {
                'kk': {'toplam': {'brut': 0, 'net': 0, 'komisyon': 0, 'odenen': 0},
                       'iptal': {'brut': 0, 'net': 0, 'komisyon': 0, 'odenen': 0}},
                'acik': {'toplam': {'brut': 0, 'net': 0, 'komisyon': 0, 'odenen': 0},
                         'iptal': {'brut': 0, 'net': 0, 'komisyon': 0, 'odenen': 0}},
                'genel': {'toplam': {'brut': 0, 'net': 0, 'komisyon': 0, 'odenen': 0},
                          'iptal': {'brut': 0, 'net': 0, 'komisyon': 0, 'odenen': 0}}
            }

        result = {'axa': empty_summary(), 'other': empty_summary()}

        try:
            # Ay ismini ay numarasına çevir
            ay_numarasi = None
            if ay:
                ay_list = ['OCAK', 'ŞUBAT', 'MART', 'NİSAN', 'MAYIS', 'HAZİRAN',
                           'TEMMUZ', 'AĞUSTOS', 'EYLÜL', 'EKİM', 'KASIM', 'ARALIK']
                if ay.upper() in ay_list:
                    ay_numarasi = ay_list.index(ay.upper()) + 1

            conn = sqlite3.connect(self.db_path)

            # Tarihten ay çıkarma fonksiyonu
            def extract_month(tarih):
                if pd.isna(tarih) or not tarih:
                    return None
                tarih_str = str(tarih).strip()
                if '.' in tarih_str:
                    parts = tarih_str.split('.')
                    if len(parts) >= 2:
                        try:
                            return int(parts[1])
                        except:
                            return None
                elif '/' in tarih_str:
                    parts = tarih_str.split('/')
                    if len(parts) >= 2:
                        try:
                            return int(parts[1])
                        except:
                            return None
                elif '-' in tarih_str:
                    parts = tarih_str.split('-')
                    if len(parts) >= 2:
                        try:
                            return int(parts[1])
                        except:
                            return None
                return None

            # AXA kayıtları
            query_axa = "SELECT tarih, odeme_turu, iptal, brut_prim, net_prim, toplam_komisyon, odenen_komisyon FROM komisyonlar_axa WHERE 1=1"
            params = []
            if kisi:
                query_axa += " AND kisi = ?"
                params.append(kisi)

            df_axa = pd.read_sql_query(query_axa, conn, params=params)

            # Diğer şirket kayıtları
            query_other = "SELECT tarih, odeme_turu, iptal, brut_prim, net_prim, toplam_komisyon, odenen_komisyon FROM komisyonlar_other WHERE 1=1"
            params_other = []
            if kisi:
                query_other += " AND kisi = ?"
                params_other.append(kisi)

            df_other = pd.read_sql_query(query_other, conn, params=params_other)
            conn.close()

            # Ay filtreleme
            if ay_numarasi:
                if not df_axa.empty and 'tarih' in df_axa.columns:
                    df_axa['_ay'] = df_axa['tarih'].apply(extract_month)
                    df_axa = df_axa[df_axa['_ay'] == ay_numarasi]
                if not df_other.empty and 'tarih' in df_other.columns:
                    df_other['_ay'] = df_other['tarih'].apply(extract_month)
                    df_other = df_other[df_other['_ay'] == ay_numarasi]

            def calc_summary(df, source):
                if df.empty:
                    return

                for _, row in df.iterrows():
                    odeme = str(row.get('odeme_turu', '')).upper().strip()
                    is_kk = 'K.KART' in odeme or 'KART' in odeme
                    is_iptal = row.get('iptal', 0) == 1

                    brut = float(row.get('brut_prim', 0) or 0)
                    net = float(row.get('net_prim', 0) or 0)
                    kom = float(row.get('toplam_komisyon', 0) or 0)
                    ode = float(row.get('odenen_komisyon', 0) or 0)

                    # Ödeme türüne göre
                    odeme_key = 'kk' if is_kk else 'acik'
                    iptal_key = 'iptal' if is_iptal else 'toplam'

                    result[source][odeme_key][iptal_key]['brut'] += brut
                    result[source][odeme_key][iptal_key]['net'] += net
                    result[source][odeme_key][iptal_key]['komisyon'] += kom
                    result[source][odeme_key][iptal_key]['odenen'] += ode

                    # Genel toplama da ekle
                    result[source]['genel'][iptal_key]['brut'] += brut
                    result[source]['genel'][iptal_key]['net'] += net
                    result[source]['genel'][iptal_key]['komisyon'] += kom
                    result[source]['genel'][iptal_key]['odenen'] += ode

            calc_summary(df_axa, 'axa')
            calc_summary(df_other, 'other')

        except Exception as e:
            print(f"Detaylı özet hatası: {e}")

        return result
