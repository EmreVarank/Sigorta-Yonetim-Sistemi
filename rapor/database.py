#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rapor Veritabanı Yönetimi
"""

import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime

# parser.py'den import et
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser import init_database, insert_police_data


def get_application_path():
    """EXE veya script'in bulunduğu gerçek klasörü döndürür"""
    if getattr(sys, 'frozen', False):
        # PyInstaller ile oluşturulmuş EXE
        return os.path.dirname(sys.executable)
    else:
        # Normal Python script
        return os.path.dirname(os.path.abspath(__file__))


class DatabaseManager:
    """Veritabanı yönetimi sınıfı"""

    def __init__(self, db_path=None):
        # Veritabanı EXE'nin yanında direkt oluşturulsun
        if db_path is None:
            script_dir = get_application_path()
            db_path = os.path.join(script_dir, 'rapor_veritabani.db')
        self.db_path = db_path
        init_database(self.db_path)

        # Session başlangıcındaki max ID'yi kaydet (yeni kayıtları tespit için)
        self.session_start_max_id = self.get_max_id()

    def get_max_id(self):
        """Veritabanındaki maksimum ID'yi getir"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(id) FROM policeler")
            result = cursor.fetchone()[0]
            conn.close()
            return result if result else 0
        except:
            return 0

    def get_all_records(self):
        """Tüm kayıtları getir - Yeniler en üstte"""
        try:
            conn = sqlite3.connect(self.db_path)
            # ID'ye göre AZALAN sıralama - en yeni ID'ler en üstte
            df = pd.read_sql_query("SELECT * FROM policeler ORDER BY id DESC", conn)
            conn.close()

            # Sütun isimlerini büyük harfe çevir
            df.columns = df.columns.str.upper()

            return df
        except Exception as e:
            print(f"Kayıt getirme hatası: {e}")
            return pd.DataFrame()

    def search_records(self, **filters):
        """Filtreye göre kayıt ara"""
        try:
            conn = sqlite3.connect(self.db_path)

            query = "SELECT * FROM policeler WHERE 1=1"
            params = []

            if filters.get('sigortali'):
                query += " AND sigortali LIKE ?"
                params.append(f"%{filters['sigortali']}%")

            if filters.get('police_no'):
                query += " AND police_no LIKE ?"
                params.append(f"%{filters['police_no']}%")

            if filters.get('tur'):
                query += " AND tur = ?"
                params.append(filters['tur'])

            if filters.get('sirket'):
                query += " AND sirket = ?"
                params.append(filters['sirket'])

            if filters.get('plaka'):
                query += " AND plaka LIKE ?"
                params.append(f"%{filters['plaka']}%")

            # Tarih filtreleri - Veritabanında DD/MM/YYYY formatında
            if filters.get('baslangic_tarih'):
                # GG.AA.YYYY veya GG/AA/YYYY -> DD/MM/YYYY
                user_date = filters['baslangic_tarih'].replace('.', '/')
                # SQL'de tarih karşılaştırması için YYYY-MM-DD formatına çevir
                # substr(tarih, 7, 4) || '-' || substr(tarih, 4, 2) || '-' || substr(tarih, 1, 2)
                query += " AND (substr(tarih, 7, 4) || '-' || substr(tarih, 4, 2) || '-' || substr(tarih, 1, 2)) >= ?"
                # Kullanıcının tarihini de YYYY-MM-DD'ye çevir
                try:
                    parts = user_date.split('/')
                    if len(parts) == 3:
                        user_date_converted = f"{parts[2]}-{parts[1]}-{parts[0]}"
                        params.append(user_date_converted)
                    else:
                        params.append(user_date)
                except:
                    params.append(user_date)

            if filters.get('bitis_tarih'):
                # GG.AA.YYYY veya GG/AA/YYYY -> DD/MM/YYYY
                user_date = filters['bitis_tarih'].replace('.', '/')
                query += " AND (substr(tarih, 7, 4) || '-' || substr(tarih, 4, 2) || '-' || substr(tarih, 1, 2)) <= ?"
                # Kullanıcının tarihini de YYYY-MM-DD'ye çevir
                try:
                    parts = user_date.split('/')
                    if len(parts) == 3:
                        user_date_converted = f"{parts[2]}-{parts[1]}-{parts[0]}"
                        params.append(user_date_converted)
                    else:
                        params.append(user_date)
                except:
                    params.append(user_date)

            # Yeniler en üstte - ID'ye göre azalan sıralama
            query += " ORDER BY id DESC"

            df = pd.read_sql_query(query, conn, params=params)
            conn.close()

            # Sütun isimlerini büyük harfe çevir
            df.columns = df.columns.str.upper()

            return df
        except Exception as e:
            print(f"Arama hatası: {e}")
            return pd.DataFrame()

    def delete_record(self, record_id):
        """Kayıt sil"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM policeler WHERE id = ?", (record_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Silme hatası: {e}")
            return False

    def update_record(self, record_id, **fields):
        """Kayıt güncelle"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            updates = []
            params = []
            for key, value in fields.items():
                updates.append(f"{key} = ?")
                params.append(value)

            params.append(record_id)
            query = f"UPDATE policeler SET {', '.join(updates)} WHERE id = ?"

            cursor.execute(query, params)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Güncelleme hatası: {e}")
            return False

    def get_statistics(self):
        """İstatistikleri getir"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Toplam kayıt
            cursor.execute("SELECT COUNT(*) FROM policeler")
            total_count = cursor.fetchone()[0]

            # Şirket bazlı dağılım
            cursor.execute("SELECT sirket, COUNT(*) FROM policeler GROUP BY sirket")
            company_stats = cursor.fetchall()

            # Tür bazlı dağılım
            cursor.execute("SELECT tur, COUNT(*) FROM policeler GROUP BY tur")
            type_stats = cursor.fetchall()

            # Bu ay kayıtlar
            cursor.execute("""
                SELECT COUNT(*) FROM policeler
                WHERE strftime('%Y-%m', kayit_tarihi) = strftime('%Y-%m', 'now')
            """)
            this_month = cursor.fetchone()[0]

            conn.close()

            return {
                'total': total_count,
                'company': company_stats,
                'type': type_stats,
                'this_month': this_month
            }
        except Exception as e:
            print(f"İstatistik hatası: {e}")
            return {'total': 0, 'company': [], 'type': [], 'this_month': 0}
