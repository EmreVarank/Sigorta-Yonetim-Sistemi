#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sigorta Rapor ve Kayit Yonetimi - GUI
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path
import subprocess

# Modül yolunu ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import DatabaseManager, get_application_path

try:
    from parser import (
        init_database,
        insert_police_data,
        identify_policy_type,
        process_hdi_trafik,
        hdi_yeni_police,
        process_ray_trafik,
        process_ethica_trafik,
        process_sompo_trafik,
        process_quick_trafik,
        process_doga_trafik,
        process_hepiyi_trafik,
        process_allianz_trafik,
        process_allianz_kasko,
        process_seyahat,
        process_isyeri,
        process_nakliyat,
        process_konut,
        process_saglik,
        process_dask,
        process_vehicle
    )
    TAYYARE_AVAILABLE = True
except ImportError as e:
    print(f"Uyari: parser.py modulu bulunamadi: {e}")
    TAYYARE_AVAILABLE = False

# Renkler - Muhasebe GUI ile uyumlu
COLORS = {
    'primary': '#0f172a',
    'primary_light': '#1e293b',
    'accent': '#3b82f6',
    'accent_hover': '#2563eb',
    'success': '#10b981',
    'warning': '#f59e0b',
    'danger': '#ef4444',
    'info': '#06b6d4',
    'bg_light': '#f1f5f9',
    'bg_card': '#ffffff',
    'text_dark': '#0f172a',
    'text_muted': '#64748b',
    'text_light': '#ffffff',
    'border': '#e2e8f0',
    'header_gradient_start': '#0f172a',
    'header_gradient_end': '#1e3a5f'
}


class RaporGUI:
    """Ana GUI Sinifi"""

    def __init__(self, root):
        self.root = root
        self.root.title("Sigorta Rapor ve Kayit Yonetimi")
        self.root.geometry("1600x900")
        self.root.configure(bg=COLORS['bg_light'])

        # Veritabanı yöneticisi
        self.db_manager = DatabaseManager()

        # Arama filtreleri
        self.search_filters = {}

        # UI oluştur
        self.create_ui()

        # Başlangıç
        self.log("Uygulama baslatildi", "success")
        self.load_data()
        self.update_statistics()

    def create_ui(self):
        """Kullanici arayuzunu olustur"""
        # Menu
        self.create_menu()

        # Baslik
        self.create_header()

        # Ana icerik
        self.create_content()

        # Durum cubugu
        self.create_status_bar()

    def create_menu(self):
        """Menu cubugu"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # Dosya
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Dosya", menu=file_menu)
        file_menu.add_command(label="PDF Klasoru Isle", command=self.process_pdf_folder)
        file_menu.add_command(label="Excel'e Aktar", command=self.export_to_excel)
        file_menu.add_command(label="Excel Raporunu Ac", command=self.open_excel_report)
        file_menu.add_separator()
        file_menu.add_command(label="Veritabani Yedekle", command=self.backup_database)
        file_menu.add_separator()
        file_menu.add_command(label="Cikis", command=self.root.quit)

        # Duzenle
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Duzenle", menu=edit_menu)
        edit_menu.add_command(label="Yeni Kayit Ekle", command=self.add_manual_entry)
        edit_menu.add_command(label="Secili Kaydi Duzenle", command=self.edit_selected)
        edit_menu.add_command(label="Secili Kaydi Sil", command=self.delete_selected)

        # Gorunum
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Gorunum", menu=view_menu)
        view_menu.add_command(label="Yenile", command=self.load_data)
        view_menu.add_command(label="Filtreleri Temizle", command=self.clear_filters)
        view_menu.add_command(label="Loglari Temizle", command=self.clear_logs)

        # Raporlar
        reports_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Raporlar", menu=reports_menu)
        reports_menu.add_command(label="Sirket Bazli Rapor", command=self.show_company_report)
        reports_menu.add_command(label="Tur Bazli Rapor", command=self.show_type_report)
        reports_menu.add_command(label="Aylik Ozet", command=self.show_monthly_summary)

        # Yardim
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Yardim", menu=help_menu)
        help_menu.add_command(label="Kullanim Kilavuzu", command=self.show_help)
        help_menu.add_command(label="Hakkinda", command=self.show_about)

    def create_header(self):
        """Baslik bolumu - Modern koyu tema"""
        # Ana header container
        header_container = tk.Frame(self.root, bg=COLORS['primary'], height=60)
        header_container.pack(fill=tk.X)
        header_container.pack_propagate(False)

        # Ana baslik
        title = tk.Label(
            header_container,
            text="SIGORTA RAPOR VE KAYIT YONETIMI",
            font=('Segoe UI', 15, 'bold'),
            bg=COLORS['primary'],
            fg='#ffffff'
        )
        title.pack(pady=(12, 0))

        # Alt baslik
        subtitle = tk.Label(
            header_container,
            text="Otomatik PDF Okuma ve Veritabani Yonetim Sistemi",
            font=('Segoe UI', 9),
            bg=COLORS['primary'],
            fg='#94a3b8'
        )
        subtitle.pack()

        # Accent cizgi (mavi ince serit)
        accent_line = tk.Frame(self.root, bg=COLORS['accent'], height=3)
        accent_line.pack(fill=tk.X)

    def create_content(self):
        """Ana icerik alani"""
        main_frame = tk.Frame(self.root, bg=COLORS['bg_light'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Sol panel - Filtreler ve butonlar
        left_panel = tk.Frame(main_frame, bg='white', width=175)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)

        # Filtre paneli
        self.create_filter_panel(left_panel)

        # Butonlar
        self.create_buttons(left_panel)

        # Istatistikler
        self.create_statistics_panel(left_panel)

        # Sag panel - Tablo ve log
        right_panel = tk.Frame(main_frame, bg=COLORS['bg_light'])
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Tablo
        self.create_table(right_panel)

        # Log
        self.create_log_panel(right_panel)

    def create_filter_panel(self, parent):
        """Filtre paneli"""
        filter_frame = tk.LabelFrame(
            parent,
            text="FILTRELER",
            font=('Segoe UI', 9, 'bold'),
            bg='white',
            fg=COLORS['text_dark']
        )
        filter_frame.pack(fill=tk.X, padx=5, pady=5)

        # Sigortali
        tk.Label(filter_frame, text="Sigortali:", font=('Arial', 8), bg='white').pack(anchor='w', padx=5, pady=(5, 0))
        self.filter_sigortali = tk.Entry(filter_frame, font=('Arial', 8))
        self.filter_sigortali.pack(fill=tk.X, padx=5, pady=(1, 3))

        # Police No
        tk.Label(filter_frame, text="Police No:", font=('Arial', 8), bg='white').pack(anchor='w', padx=5, pady=(2, 0))
        self.filter_police = tk.Entry(filter_frame, font=('Arial', 8))
        self.filter_police.pack(fill=tk.X, padx=5, pady=(1, 3))

        # Tur
        tk.Label(filter_frame, text="Tur:", font=('Arial', 8), bg='white').pack(anchor='w', padx=5, pady=(2, 0))
        self.filter_tur = ttk.Combobox(
            filter_frame,
            font=('Arial', 8),
            values=['Tumu', 'TRAFIK', 'KASKO', 'DASK', 'EVIM', 'SAGLIK', 'SEYAHAT', 'NAKLIYAT', 'ISYERI',
                    'GENEL FERDI KAZA', 'MAKINE KIRILMASI', 'CEP TELEFONU SIGORTASI',
                    'ACENTE MESLEKI SORUMLULUK', 'ELEKTRONIK CIHAZ', 'DIGER'],
            state='readonly'
        )
        self.filter_tur.set('Tumu')
        self.filter_tur.pack(fill=tk.X, padx=5, pady=(1, 3))

        # Sirket
        tk.Label(filter_frame, text="Sirket:", font=('Arial', 8), bg='white').pack(anchor='w', padx=5, pady=(2, 0))
        self.filter_sirket = ttk.Combobox(
            filter_frame,
            font=('Arial', 8),
            values=['Tumu', 'ALLIANZ', 'AXA', 'HDI', 'RAY', 'ETHICA', 'SOMPO', 'QUICK', 'DOGA', 'HEPIYI'],
            state='readonly'
        )
        self.filter_sirket.set('Tumu')
        self.filter_sirket.pack(fill=tk.X, padx=5, pady=(1, 3))

        # Plaka
        tk.Label(filter_frame, text="Plaka:", font=('Arial', 8), bg='white').pack(anchor='w', padx=5, pady=(2, 0))
        self.filter_plaka = tk.Entry(filter_frame, font=('Arial', 8))
        self.filter_plaka.pack(fill=tk.X, padx=5, pady=(1, 3))

        # Baslangic Tarihi
        tk.Label(filter_frame, text="Baslangic Tarihi:", font=('Arial', 8), bg='white').pack(anchor='w', padx=5, pady=(2, 0))
        self.filter_baslangic_tarih = tk.Entry(filter_frame, font=('Arial', 8))
        self.filter_baslangic_tarih.pack(fill=tk.X, padx=5, pady=(1, 3))
        self.filter_baslangic_tarih.insert(0, "DD.MM.YYYY")
        self.filter_baslangic_tarih.bind('<FocusIn>', lambda e: self.clear_placeholder(e, "DD.MM.YYYY"))
        self.filter_baslangic_tarih.bind('<FocusOut>', lambda e: self.restore_placeholder(e, "DD.MM.YYYY"))
        self.filter_baslangic_tarih.config(fg='gray')

        # Bitis Tarihi
        tk.Label(filter_frame, text="Bitis Tarihi:", font=('Arial', 8), bg='white').pack(anchor='w', padx=5, pady=(2, 0))
        self.filter_bitis_tarih = tk.Entry(filter_frame, font=('Arial', 8))
        self.filter_bitis_tarih.pack(fill=tk.X, padx=5, pady=(1, 5))
        self.filter_bitis_tarih.insert(0, "DD.MM.YYYY")
        self.filter_bitis_tarih.bind('<FocusIn>', lambda e: self.clear_placeholder(e, "DD.MM.YYYY"))
        self.filter_bitis_tarih.bind('<FocusOut>', lambda e: self.restore_placeholder(e, "DD.MM.YYYY"))
        self.filter_bitis_tarih.config(fg='gray')

        # Arama butonu
        search_btn = tk.Button(
            filter_frame,
            text="ARA",
            command=self.apply_filters,
            font=('Segoe UI', 8, 'bold'),
            bg=COLORS['accent'],
            fg='white',
            relief=tk.FLAT,
            cursor='hand2',
            pady=5,
            activebackground=COLORS['accent_hover'],
            activeforeground='white'
        )
        search_btn.pack(fill=tk.X, padx=5, pady=(2, 5))

    def clear_placeholder(self, event, placeholder_text):
        """Placeholder metni temizle"""
        if event.widget.get() == placeholder_text:
            event.widget.delete(0, tk.END)
            event.widget.config(fg='black')

    def restore_placeholder(self, event, placeholder_text):
        """Placeholder metni geri yukle"""
        if not event.widget.get().strip():
            event.widget.insert(0, placeholder_text)
            event.widget.config(fg='gray')

    def create_buttons(self, parent):
        """Butonlar"""
        btn_frame = tk.LabelFrame(
            parent,
            text="ISLEMLER",
            font=('Segoe UI', 9, 'bold'),
            bg='white',
            fg=COLORS['text_dark']
        )
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        buttons = [
            ("PDF Klasoru Isle", self.process_pdf_folder, COLORS['accent']),
            ("Yeni Kayit Ekle", self.add_manual_entry, COLORS['success']),
            ("Excel'e Aktar", self.export_to_excel, '#e67e22'),
            ("Excel Raporunu Ac", self.open_excel_report, '#8b5cf6'),
            ("Yenile", self.load_data, COLORS['info']),
            ("Tum Kayitlari Sil", self.delete_all_records, COLORS['danger'])
        ]

        for text, command, color in buttons:
            btn = tk.Button(
                btn_frame,
                text=text,
                command=command,
                font=('Segoe UI', 8, 'bold'),
                bg=color,
                fg='white',
                relief=tk.FLAT,
                cursor='hand2',
                padx=5,
                pady=5,
                activebackground=COLORS['primary_light'],
                activeforeground='white'
            )
            btn.pack(fill=tk.X, padx=5, pady=2)

    def create_statistics_panel(self, parent):
        """Istatistikler paneli"""
        stats_frame = tk.LabelFrame(
            parent,
            text="ISTATISTIKLER",
            font=('Segoe UI', 9, 'bold'),
            bg='white',
            fg=COLORS['text_dark']
        )
        stats_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.stats_text = tk.Text(
            stats_frame,
            font=('Consolas', 7),
            bg='#f8fafc',
            fg='#1e293b',
            relief=tk.FLAT,
            wrap=tk.WORD
        )
        self.stats_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def create_table(self, parent):
        """Kayit tablosu"""
        table_frame = tk.Frame(parent, bg='white')
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Scrollbar
        scrollbar_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        scrollbar_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)

        # Treeview
        columns = ('ID', 'SIGORTALI', 'TARIH', 'MUSTERI_NO', 'POLICE_NO', 'TUR',
                   'SIRKET', 'PLAKA', 'MARKA', 'TUTAR', 'ACIKLAMA', 'REFERANS', 'ILETISIM')

        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show='headings',
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set,
            selectmode='extended'
        )

        # Sutun basliklari - BUYUK HARFLE - Siralama devre disi
        headers = {
            'ID': 'SIRA',
            'SIGORTALI': 'SIGORTALI',
            'TARIH': 'TARIH',
            'MUSTERI_NO': 'MUSTERI NO',
            'POLICE_NO': 'POLICE NO',
            'TUR': 'TUR',
            'SIRKET': 'SIRKET',
            'PLAKA': 'PLAKA',
            'MARKA': 'MARKA',
            'TUTAR': 'TUTAR',
            'ACIKLAMA': 'ACIKLAMA',
            'REFERANS': 'REFERANS',
            'ILETISIM': 'ILETISIM'
        }

        # Hicbir sutun siralanamaz - command parametresi yok
        for col in columns:
            self.tree.heading(col, text=headers[col])

        # Sutun genislikleri - Excel'deki gibi
        self.tree.column('ID', width=50, anchor='center')
        self.tree.column('SIGORTALI', width=250, anchor='w')
        self.tree.column('TARIH', width=90, anchor='center')
        self.tree.column('MUSTERI_NO', width=110, anchor='center')
        self.tree.column('POLICE_NO', width=110, anchor='center')
        self.tree.column('TUR', width=85, anchor='center')
        self.tree.column('SIRKET', width=70, anchor='center')
        self.tree.column('PLAKA', width=90, anchor='center')
        self.tree.column('MARKA', width=140, anchor='w')
        self.tree.column('TUTAR', width=110, anchor='e')
        self.tree.column('ACIKLAMA', width=90, anchor='center')
        self.tree.column('REFERANS', width=90, anchor='center')
        self.tree.column('ILETISIM', width=90, anchor='center')

        # Scrollbar'lari yerles tir
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(fill=tk.BOTH, expand=True)

        scrollbar_y.config(command=self.tree.yview)
        scrollbar_x.config(command=self.tree.xview)

        # Yeni kayitlar icin acik yesil tema tag'i
        self.tree.tag_configure('yeni_kayit', background='#b8e6b8')
        # Yeni satir icin mavi tag
        self.tree.tag_configure('new_row', background='#e8f4fd')

        # Inline editing icin degiskenler
        self.editing_new_row = False
        self.new_row_item = None
        self.current_edit_entry = None
        self.new_row_data = {}

        # Sag tik menu
        self.create_context_menu()
        self.tree.bind('<Button-3>', self.show_context_menu)
        # Cift tiklanma - sadece duzenlenebilir sutunlar icin
        self.tree.bind('<Double-Button-1>', self.on_tree_double_click)

    def create_log_panel(self, parent):
        """Log paneli"""
        log_frame = tk.LabelFrame(
            parent,
            text="KAYITLAR",
            font=('Arial', 10, 'bold'),
            bg='white'
        )
        log_frame.pack(fill=tk.X)

        self.log_text = tk.Text(
            log_frame,
            height=8,
            font=('Consolas', 9),
            bg='#fafafa',
            fg='#374151',
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tag'ler
        self.log_text.tag_config('success', foreground='#16a34a')
        self.log_text.tag_config('error', foreground='#dc2626')
        self.log_text.tag_config('warning', foreground='#ea580c')
        self.log_text.tag_config('info', foreground='#2563eb')

    def create_status_bar(self):
        """Durum cubugu"""
        self.status_bar = tk.Label(
            self.root,
            text="Hazir",
            font=('Segoe UI', 9),
            bg=COLORS['primary'],
            fg='#94a3b8',
            anchor='w',
            padx=15,
            pady=4
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def create_context_menu(self):
        """Sag tik menusu"""
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Sil", command=self.delete_selected)

    def show_context_menu(self, event):
        """Sag tik menusunu goster"""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def on_double_click(self, event):
        """Cift tiklanma - detaylari goster"""
        self.show_details()

    def on_tree_double_click(self, event):
        """Treeview'da cift tiklanma - tum duzenlenebilir sutunlari duzenle"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        column = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)

        if not item:
            return

        col_index = int(column.replace('#', '')) - 1
        columns = ('ID', 'SIGORTALI', 'TARIH', 'MUSTERI_NO', 'POLICE_NO', 'TUR',
                   'SIRKET', 'PLAKA', 'MARKA', 'TUTAR', 'ACIKLAMA', 'REFERANS', 'ILETISIM')

        if col_index >= len(columns) or col_index == 0:  # ID duzenlenemez
            return

        col_name = columns[col_index]
        values = self.tree.item(item, 'values')
        record_id = values[0]
        current_value = values[col_index] if col_index < len(values) else ""

        # Duzenlenebilir sutunlar ve veritabani alanlari
        editable_cols = {
            'SIGORTALI': ('sigortali', 'entry'),
            'TARIH': ('tarih', 'entry'),
            'MUSTERI_NO': ('musteri_no', 'entry'),
            'POLICE_NO': ('police_no', 'entry'),
            'TUR': ('tur', 'combo_tur'),
            'SIRKET': ('sirket', 'combo_sirket'),
            'PLAKA': ('plaka', 'entry'),
            'MARKA': ('marka', 'entry'),
            'TUTAR': ('tutar', 'entry'),
            'ACIKLAMA': ('aciklama', 'combo_aciklama'),
            'REFERANS': ('referans', 'entry'),
            'ILETISIM': ('iletisim', 'entry')
        }

        if col_name not in editable_cols:
            return

        db_field, widget_type = editable_cols[col_name]

        # Onceki entry'yi kapat
        if self.current_edit_entry:
            self.current_edit_entry.destroy()
            self.current_edit_entry = None

        # Hucre koordinatlarini al
        bbox = self.tree.bbox(item, column)
        if not bbox:
            return

        x, y, width, height = bbox

        # Widget olustur
        if widget_type == 'combo_tur':
            all_types = ['TRAFIK', 'KASKO', 'DASK', 'EVIM', 'SAGLIK', 'SEYAHAT', 'NAKLIYAT', 'ISYERI',
                         'GENEL FERDI KAZA', 'MAKINE KIRILMASI', 'CEP TELEFONU SIGORTASI',
                         'ACENTE MESLEKI SORUMLULUK', 'ELEKTRONIK CIHAZ', 'DIGER']
            self.current_edit_entry = ttk.Combobox(self.tree,
                values=all_types,
                font=('Arial', 9), state='readonly')
            self.current_edit_entry.set(current_value if current_value in all_types else 'TRAFIK')

            # DIGER secildiginde elle giris ac
            def on_tur_selected(e=None):
                if self.current_edit_entry.get() == 'DIGER':
                    # Combobox'i kaldir, yerine Entry koy
                    self.current_edit_entry.destroy()
                    self.current_edit_entry = tk.Entry(self.tree, font=('Arial', 9))
                    self.current_edit_entry.place(x=x, y=y, width=width, height=height)
                    self.current_edit_entry.focus_set()
                    self.current_edit_entry.bind('<Return>', save_edit)
                    self.current_edit_entry.bind('<Escape>', cancel_edit)
                    self.current_edit_entry.bind('<FocusOut>', save_edit)
                else:
                    save_edit()

        elif widget_type == 'combo_sirket':
            self.current_edit_entry = ttk.Combobox(self.tree,
                values=['AXA', 'ALLIANZ', 'HDI', 'RAY', 'ETHICA', 'SOMPO', 'QUICK', 'DOGA', 'HEPIYI'],
                font=('Arial', 9), state='readonly')
            self.current_edit_entry.set(current_value if current_value in ['AXA', 'ALLIANZ', 'HDI', 'RAY', 'ETHICA', 'SOMPO', 'QUICK', 'DOGA', 'HEPIYI'] else 'AXA')
        elif widget_type == 'combo_aciklama':
            self.current_edit_entry = ttk.Combobox(self.tree,
                values=['YASAR', 'KAMIL', 'TEZCAN', 'TEZER'],
                font=('Arial', 9))
            self.current_edit_entry.set(current_value)
        else:
            self.current_edit_entry = tk.Entry(self.tree, font=('Arial', 9))
            self.current_edit_entry.insert(0, current_value)
            self.current_edit_entry.select_range(0, tk.END)

        self.current_edit_entry.place(x=x, y=y, width=width, height=height)
        self.current_edit_entry.focus_set()

        def save_edit(e=None):
            new_value = self.current_edit_entry.get().strip()

            if self.db_manager.update_record(record_id, **{db_field: new_value}):
                # Tablodaki degeri guncelle
                new_values = list(values)
                new_values[col_index] = new_value
                self.tree.item(item, values=new_values)
                self.log(f"{col_name} guncellendi", "success")
            else:
                self.log(f"{col_name} guncellenemedi", "error")

            if self.current_edit_entry:
                self.current_edit_entry.destroy()
                self.current_edit_entry = None

        def cancel_edit(e=None):
            if self.current_edit_entry:
                self.current_edit_entry.destroy()
                self.current_edit_entry = None

        self.current_edit_entry.bind('<Return>', save_edit)
        self.current_edit_entry.bind('<Escape>', cancel_edit)
        self.current_edit_entry.bind('<FocusOut>', save_edit)

        if isinstance(self.current_edit_entry, ttk.Combobox):
            if widget_type == 'combo_tur':
                self.current_edit_entry.bind('<<ComboboxSelected>>', on_tur_selected)
            else:
                self.current_edit_entry.bind('<<ComboboxSelected>>', save_edit)

    # =========================================================================
    # VERI ISLEMLERI
    # =========================================================================

    def load_data(self, df=None, highlight_from_id=None):
        """Verileri yukle"""
        # Temizle
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Veri al
        if df is None:
            df = self.db_manager.get_all_records()

        if df.empty:
            self.log("Gosterilecek kayit yok", "info")
            return

        # Debug: DataFrame boyutunu kontrol et
        print(f"DEBUG: DataFrame shape: {df.shape}, rows: {len(df)}")

        # Eger highlight_from_id belirtilmediyse, session baslangicinndaki ID'yi kullan
        if highlight_from_id is None:
            highlight_from_id = self.db_manager.session_start_max_id

        # Ekle - tum satirlari ekle (KAYIT_TARIHI olmadan)
        added_count = 0
        try:
            for idx, row in df.iterrows():
                try:
                    values = (
                        row['ID'],
                        row['SIGORTALI'],
                        row['TARIH'],
                        row.get('MUSTERI_NO', '-'),
                        row['POLICE_NO'],
                        row['TUR'],
                        row['SIRKET'],
                        row['PLAKA'],
                        row['MARKA'],
                        row['TUTAR'],
                        row.get('ACIKLAMA', '-'),
                        row.get('REFERANS', '-'),
                        row.get('ILETISIM', '-')
                    )
                    # Yeni kayitlari tespit et (belirtilen ID'den sonra eklenenler)
                    if row['ID'] > highlight_from_id:
                        # Acik yesil tema ile ekle
                        self.tree.insert('', tk.END, values=values, tags=('yeni_kayit',))
                    else:
                        self.tree.insert('', tk.END, values=values)
                    added_count += 1
                except Exception as e:
                    print(f"DEBUG: Satir {idx} eklenirken hata: {e}")
                    continue
        except Exception as e:
            print(f"DEBUG: iterrows hatasi: {e}")

        print(f"DEBUG: Tabloya eklenen satir sayisi: {added_count}")
        self.log(f"{len(df)} kayit yuklendi (Scroll ile tumunu goruntuleyebilirsiniz)", "success")
        self.update_statistics()

    def apply_filters(self):
        """Filtreleri uygula"""
        filters = {}

        if self.filter_sigortali.get().strip():
            filters['sigortali'] = self.filter_sigortali.get().strip()

        if self.filter_police.get().strip():
            filters['police_no'] = self.filter_police.get().strip()

        if self.filter_tur.get() != 'Tumu':
            filters['tur'] = self.filter_tur.get()

        if self.filter_sirket.get() != 'Tumu':
            filters['sirket'] = self.filter_sirket.get()

        if self.filter_plaka.get().strip():
            filters['plaka'] = self.filter_plaka.get().strip()

        # Tarih filtreleri
        baslangic = self.filter_baslangic_tarih.get().strip()
        if baslangic and baslangic != "DD.MM.YYYY":
            filters['baslangic_tarih'] = baslangic

        bitis = self.filter_bitis_tarih.get().strip()
        if bitis and bitis != "DD.MM.YYYY":
            filters['bitis_tarih'] = bitis

        if filters:
            df = self.db_manager.search_records(**filters)
            self.load_data(df)
            self.log(f"Filtre uygulandi: {len(filters)} kriter", "info")
        else:
            self.load_data()

    def clear_filters(self):
        """Filtreleri temizle"""
        self.filter_sigortali.delete(0, tk.END)
        self.filter_police.delete(0, tk.END)
        self.filter_tur.set('Tumu')
        self.filter_sirket.set('Tumu')
        self.filter_plaka.delete(0, tk.END)
        self.filter_baslangic_tarih.delete(0, tk.END)
        self.filter_baslangic_tarih.insert(0, "DD.MM.YYYY")
        self.filter_baslangic_tarih.config(fg='gray')
        self.filter_bitis_tarih.delete(0, tk.END)
        self.filter_bitis_tarih.insert(0, "DD.MM.YYYY")
        self.filter_bitis_tarih.config(fg='gray')
        self.load_data()
        self.log("Filtreler temizlendi", "info")

    def update_statistics(self):
        """Istatistikleri guncelle"""
        stats = self.db_manager.get_statistics()

        text = "GENEL ISTATISTIKLER\n"
        text += "=" * 35 + "\n\n"
        text += f"Toplam Kayit: {stats['total']}\n"
        text += f"Bu Ay: {stats['this_month']}\n\n"

        text += "SIRKET BAZLI\n"
        text += "-" * 35 + "\n"
        for company, count in stats['company']:
            if company:
                text += f"   {company}: {count}\n"

        text += "\nTUR BAZLI\n"
        text += "-" * 35 + "\n"
        for type_name, count in stats['type']:
            if type_name:
                text += f"   {type_name}: {count}\n"

        self.stats_text.delete('1.0', tk.END)
        self.stats_text.insert('1.0', text)

    # =========================================================================
    # PDF ISLEMLERI
    # =========================================================================

    def process_pdf_folder(self):
        """PDF klasoru sec ve isle"""
        if not TAYYARE_AVAILABLE:
            messagebox.showerror("Hata", "parser.py modulu bulunamadi!")
            return

        folder = filedialog.askdirectory(title="PDF Klasorunu Secin")
        if not folder:
            return

        pdf_files = [f for f in os.listdir(folder) if f.lower().endswith('.pdf')]

        if not pdf_files:
            messagebox.showwarning("Uyari", "Klasorde PDF dosyasi bulunamadi!")
            return

        # PDF isleme baslamadan once mevcut max ID'yi kaydet
        max_id_before = self.db_manager.get_max_id()

        self.log(f"{len(pdf_files)} PDF dosyasi bulundu", "info")

        # Islem paneli - Ana pencerede goster
        progress_win = tk.Frame(self.root, bg='white', relief=tk.RIDGE, borderwidth=2)
        progress_win.place(relx=0.5, rely=0.5, anchor='center', width=450, height=150)

        # Baslik
        title_label = tk.Label(progress_win, text="PDF Isleniyor...", font=('Arial', 12, 'bold'), bg='white', fg=COLORS['primary'])
        title_label.pack(pady=10)

        progress_label = tk.Label(progress_win, text="Isleniyor...", font=('Arial', 10), bg='white')
        progress_label.pack(pady=10)

        progress_bar = ttk.Progressbar(progress_win, length=400, mode='determinate')
        progress_bar.pack(pady=10)

        basarili = 0
        basarisiz = 0
        processed_data = []
        duplicate_pdfs = []  # Duplicate PDF listesi

        for idx, pdf_file in enumerate(pdf_files):
            pdf_path = os.path.join(folder, pdf_file)
            progress_label.config(text=f"{pdf_file}...")
            progress_bar['value'] = ((idx + 1) / len(pdf_files)) * 100
            progress_win.update()

            try:
                # Police turunu belirle
                policy_type = identify_policy_type(pdf_path)

                if policy_type == "BILINMIYOR":
                    self.log(f"Bilinmeyen tur: {pdf_file}", "warning")
                    basarisiz += 1
                    continue

                # Isle - Tum desteklenen turler
                parser_map = {
                    'TRAFIK_HDI': process_hdi_trafik,
                    'TRAFIK_HDI_YENI': hdi_yeni_police,
                    'TRAFIK_RAY': process_ray_trafik,
                    'TRAFIK_ETHICA': process_ethica_trafik,
                    'TRAFIK_SOMPO': process_sompo_trafik,
                    'TRAFIK_QUICK': process_quick_trafik,
                    'TRAFIK_DOGA': process_doga_trafik,
                    'TRAFIK_HEPIYI': process_hepiyi_trafik,
                    'TRAFIK_ALLIANZ': process_allianz_trafik,
                    'KASKO_ALLIANZ': process_allianz_kasko,
                    'SEYAHAT': process_seyahat,
                    'ISYERI': process_isyeri,
                    'NAKLIYAT': process_nakliyat,
                    'EVIM': process_konut,
                    'KONUT': process_konut,
                    'SAGLIK': process_saglik,
                    'DASK': process_dask,
                    'TRAFIK': lambda p, f: process_vehicle(p, f, "TRAFIK"),
                    'KASKO': lambda p, f: process_vehicle(p, f, "KASKO")
                }

                parser = parser_map.get(policy_type)
                if parser:
                    data = parser(pdf_path, pdf_file)
                    if data:
                        # Eksik bilgi kontrolu - ekle ama isaretele
                        sigortali = str(data.get('SIGORTALI', '')).strip()
                        police_no = str(data.get('POLICE NO', '')).strip()

                        eksik_bilgi = []
                        if not sigortali or sigortali == '-':
                            eksik_bilgi.append('Sigortali')
                        if not police_no or police_no == '-':
                            eksik_bilgi.append('Police No')

                        if eksik_bilgi:
                            # ACIKLAMA alanina eksik bilgi notunu ekle
                            mevcut_aciklama = data.get('ACIKLAMA', '')
                            eksik_text = f"[EKSIK: {', '.join(eksik_bilgi)}]"
                            if mevcut_aciklama and mevcut_aciklama != '-':
                                data['ACIKLAMA'] = f"{eksik_text} {mevcut_aciklama}"
                            else:
                                data['ACIKLAMA'] = eksik_text
                            self.log(f"Eksik bilgi ({', '.join(eksik_bilgi)}): {pdf_file}", "warning")

                        # PDF dosya ismini duplicate kontrolu icin gecici alana kaydet
                        data['_PDF_FILE'] = pdf_file

                        processed_data.append(data)
                        basarili += 1
                        if not eksik_bilgi:
                            self.log(f"{pdf_file} - {policy_type}", "success")
                    else:
                        self.log(f"Veri cikarillamadi: {pdf_file}", "warning")
                        basarisiz += 1
                else:
                    self.log(f"Parser yok ({policy_type}): {pdf_file}", "warning")
                    basarisiz += 1

            except Exception as e:
                self.log(f"Hata ({pdf_file}): {str(e)}", "error")
                basarisiz += 1

        # Veritabanina ekle ve duplicate kontrolu
        added = 0
        duplicate_count = 0
        if processed_data:
            # Once mevcut police numaralarini ve referanslarini al
            conn = sqlite3.connect(self.db_manager.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT police_no, referans FROM policeler")
            existing_policies = {row[0]: row[1] for row in cursor.fetchall()}
            conn.close()

            # Batch icindeki police numaralarini da kontrol et (batch ici duplicate'lar icin)
            batch_police_nos = {}

            # Duplicate olanlari tespit et
            for data in processed_data:
                police_no = str(data.get('POLICE NO', '')).strip()
                # PDF dosya ismini gecici alandan al
                new_pdf = data.get('_PDF_FILE', 'PDF dosyasi')

                if police_no and police_no != '-':
                    # Veritabaninda var mi?
                    if police_no in existing_policies:
                        # Veritabaninda mevcut - PDF ismi yerine 'DB' goster
                        duplicate_pdfs.append((new_pdf, 'Veritabaninda mevcut', police_no))
                    # Batch icinde daha once islendi mi?
                    elif police_no in batch_police_nos:
                        first_pdf = batch_police_nos[police_no]
                        duplicate_pdfs.append((new_pdf, first_pdf, police_no))
                    else:
                        # Ilk kez goruyoruz, kaydet
                        batch_police_nos[police_no] = new_pdf

            added = insert_police_data(self.db_manager.db_path, processed_data)
            duplicate_count = len(processed_data) - added
            if added > 0:
                self.log(f"{added} yeni kayit eklendi", "success")
            if duplicate_count > 0:
                self.log(f"{duplicate_count} kayit zaten mevcut (duplicate)", "warning")
                # Her duplicate icin detay log
                for new_pdf, existing_ref, police_no in duplicate_pdfs:
                    if existing_ref == 'Veritabaninda mevcut':
                        self.log(f"   {new_pdf} - (Police: {police_no}) eklenmedi.", "warning")
                    else:
                        self.log(f"   {new_pdf} - {existing_ref} ile ayni eklenmedi.", "warning")

        progress_win.destroy()

        self.log(f"{basarili} basarili, {basarisiz} hatali", "success")

        # Mesaj kutusu
        msg = f"TARAMA SONUCU\n{'='*40}\n\n"
        msg += f"Taranan PDF: {len(pdf_files)} adet\n"
        msg += f"Basariyla islenen: {basarili} adet\n"

        if basarisiz > 0:
            msg += f"Hatali/Islenemedi: {basarisiz} adet\n"

        msg += f"\nVERITABANI ISLEMLERI\n{'='*40}\n\n"
        msg += f"Yeni eklenen: {added} kayit\n"

        if duplicate_count > 0:
            msg += f"Zaten mevcut (duplicate): {duplicate_count} kayit\n"

        messagebox.showinfo("Tamamlandi", msg)

        # Sadece bu islemde eklenen kayitlari yesil goster
        self.load_data(highlight_from_id=max_id_before)

    # =========================================================================
    # EXCEL ISLEMLERI
    # =========================================================================

    def open_excel_report(self):
        """Excel rapor dosyasi sec ve GUI'de goster"""
        filename = filedialog.askopenfilename(
            title="Excel Rapor Dosyasi Sec",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
        )

        if not filename:
            return

        try:
            # Excel dosyasini oku
            df = pd.read_excel(filename)

            # Excel'deki Turkce sutun isimlerini normalize et
            column_mapping = {
                'SIRA': 'ID',
                'SIGORTALI': 'SIGORTALI',
                'TARIH': 'TARIH',
                'MUSTERI NO': 'MUSTERI_NO',
                'POLICE NO': 'POLICE_NO',
                'TUR': 'TUR',
                'SIRKET': 'SIRKET',
                'PLAKA': 'PLAKA',
                'MARKA': 'MARKA',
                'TUTAR': 'TUTAR',
                'ACIKLAMA': 'ACIKLAMA',
                'REFERANS': 'REFERANS',
                'ILETISIM': 'ILETISIM'
            }

            # Sutun isimlerini donustur
            df = df.rename(columns=column_mapping)

            # NaN degerlerini '-' ile degistir
            df = df.fillna('-')

            # Excel'deki sirayi tersine cevir - en eski kayitlar once veritabanina eklensin
            df = df.iloc[::-1].reset_index(drop=True)

            # Veritabani formatina donustur ve ekle
            data_list = []
            for _, row in df.iterrows():
                data = {
                    'SIGORTALI': str(row.get('SIGORTALI', '-')),
                    'TARIH': str(row.get('TARIH', '-')),
                    'MUSTERI NO': str(row.get('MUSTERI_NO', '-')),
                    'POLICE NO': str(row.get('POLICE_NO', '-')),
                    'TUR': str(row.get('TUR', '-')),
                    'SIRKET': str(row.get('SIRKET', '-')),
                    'PLAKA': str(row.get('PLAKA', '-')),
                    'MARKA': str(row.get('MARKA', '-')),
                    'TUTAR': str(row.get('TUTAR', '-')),
                    'ACIKLAMA': str(row.get('ACIKLAMA', '-')),
                    'REFERANS': str(row.get('REFERANS', '-')),
                    'ILETISIM': str(row.get('ILETISIM', '-'))
                }
                data_list.append(data)

            # Veritabanina ekle
            if TAYYARE_AVAILABLE:
                added = insert_police_data(self.db_manager.db_path, data_list)
                duplicate_count = len(data_list) - added

                msg = f"{added} kayit veritabanina eklendi"
                if duplicate_count > 0:
                    msg += f"\n{duplicate_count} kayit zaten mevcut (atlanidi)"

                messagebox.showinfo("Tamamlandi", msg)
                self.log(f"Excel'den {added} kayit import edildi", "success")

                # Veritabanindan yeniden yukle
                self.load_data()
            else:
                messagebox.showerror("Hata", "Veritabani modulu bulunamadi!")

        except Exception as e:
            messagebox.showerror("Hata", f"Excel dosyasi okunamadi:\n{str(e)}")
            self.log(f"Excel okuma hatasi: {str(e)}", "error")

    def export_to_excel(self):
        """Excel'e aktar"""
        df = self.db_manager.get_all_records()

        if df.empty:
            messagebox.showwarning("Uyari", "Disa aktarilacak veri yok!")
            return

        # KAYIT_TARIHI sutununu kaldir
        if 'KAYIT_TARIHI' in df.columns:
            df = df.drop('KAYIT_TARIHI', axis=1)

        # Sutun isimlerini buyuk harfe cevir ve sira numarasi ekle
        column_mapping = {
            'ID': 'SIRA',
            'SIGORTALI': 'SIGORTALI',
            'TARIH': 'TARIH',
            'MUSTERI_NO': 'MUSTERI NO',
            'POLICE_NO': 'POLICE NO',
            'TUR': 'TUR',
            'SIRKET': 'SIRKET',
            'PLAKA': 'PLAKA',
            'MARKA': 'MARKA',
            'TUTAR': 'TUTAR',
            'ACIKLAMA': 'ACIKLAMA',
            'REFERANS': 'REFERANS',
            'ILETISIM': 'ILETISIM'
        }
        df = df.rename(columns=column_mapping)

        # Dosya adi - Mevcut ay
        aylar = {
            1: 'Ocak', 2: 'Subat', 3: 'Mart', 4: 'Nisan', 5: 'Mayis', 6: 'Haziran',
            7: 'Temmuz', 8: 'Agustos', 9: 'Eylul', 10: 'Ekim', 11: 'Kasim', 12: 'Aralik'
        }
        now = datetime.now()
        ay_adi = aylar[now.month]
        yil = now.year
        default_filename = f"Sigorta_Kayitlari_{ay_adi}_{yil}.xlsx"

        filename = filedialog.asksaveasfilename(
            title="Excel Dosyasi Kaydet",
            defaultextension=".xlsx",
            initialfile=default_filename,
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )

        if not filename:
            return

        try:
            # Excel'e yaz ve bicimlendir
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name="Kayitlar", index=False)

                # Worksheet'i al
                worksheet = writer.sheets['Kayitlar']

                # Sutun genisliklerini ayarla (resme gore)
                column_widths = {
                    'A': 6,   # SIRA
                    'B': 30,  # SIGORTALI
                    'C': 12,  # TARIH
                    'D': 14,  # MUSTERI NO
                    'E': 14,  # POLICE NO
                    'F': 10,  # TUR
                    'G': 10,  # SIRKET
                    'H': 12,  # PLAKA
                    'I': 18,  # MARKA
                    'J': 14,  # TUTAR
                    'K': 12,  # ACIKLAMA
                    'L': 12,  # REFERANS
                    'M': 12   # ILETISIM
                }

                for col, width in column_widths.items():
                    worksheet.column_dimensions[col].width = width

                # Baslik satirini kalinlastir ve hizala
                from openpyxl.styles import Font, Alignment
                for cell in worksheet[1]:
                    cell.font = Font(bold=True, size=11)
                    cell.alignment = Alignment(horizontal='center', vertical='center')

            self.log(f"Excel dosyasi olusturuldu: {os.path.basename(filename)}", "success")
            messagebox.showinfo("Basarili", f"Excel dosyasi kaydedildi:\n{filename}")

        except Exception as e:
            self.log(f"Excel hatasi: {str(e)}", "error")
            messagebox.showerror("Hata", str(e))

    # =========================================================================
    # DIGER ISLEMLER
    # =========================================================================

    def add_inline_record(self):
        """Tabloya inline yeni satir ekle"""
        if self.editing_new_row:
            self.log("Zaten yeni satir duzenleniyor!", "warning")
            return

        # Yeni satir ekle - tablonun en ustune
        placeholder_values = (
            'YEN',           # ID
            '(Sigortali)*',  # SIGORTALI
            '(Tarih)*',      # TARIH
            '-',             # MUSTERI_NO
            '(Police No)*',  # POLICE_NO
            '(Tur)*',        # TUR
            '(Sirket)*',     # SIRKET
            '-',             # PLAKA
            '-',             # MARKA
            '(Tutar)*',      # TUTAR
            '-',             # ACIKLAMA
            '-',             # REFERANS
            '-'              # ILETISIM
        )

        self.new_row_item = self.tree.insert('', 0, values=placeholder_values, tags=('new_row',))
        self.tree.selection_set(self.new_row_item)
        self.tree.see(self.new_row_item)

        self.editing_new_row = True
        self.new_row_data = {}

        self.log("Yeni satir eklendi. Hucrelere cift tiklayarak doldurun, zorunlu alanlar (*) isaretli.", "info")

        # Cift tiklama eventini yeni satir icin ayarla
        self.tree.bind('<Double-Button-1>', self.on_double_click_new_row)

    def on_double_click_new_row(self, event):
        """Yeni satirda cift tiklama - hucreyi duzenle"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        column = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)

        if not item:
            return

        # Sadece yeni satirda duzenleme yap
        if item != self.new_row_item:
            return

        col_index = int(column.replace('#', '')) - 1
        columns = ('ID', 'SIGORTALI', 'TARIH', 'MUSTERI_NO', 'POLICE_NO', 'TUR',
                   'SIRKET', 'PLAKA', 'MARKA', 'TUTAR', 'ACIKLAMA', 'REFERANS', 'ILETISIM')

        if col_index >= len(columns) or col_index == 0:  # ID duzenlenemez
            return

        col_name = columns[col_index]

        # Onceki entry'yi kapat
        if self.current_edit_entry:
            self.current_edit_entry.destroy()
            self.current_edit_entry = None

        # Hucre koordinatlari
        bbox = self.tree.bbox(item, column)
        if not bbox:
            return

        x, y, width, height = bbox

        # Widget olustur
        if col_name == 'TUR':
            all_types = ['TRAFIK', 'KASKO', 'DASK', 'EVIM', 'SAGLIK', 'SEYAHAT', 'NAKLIYAT', 'ISYERI',
                         'GENEL FERDI KAZA', 'MAKINE KIRILMASI', 'CEP TELEFONU SIGORTASI',
                         'ACENTE MESLEKI SORUMLULUK', 'ELEKTRONIK CIHAZ', 'DIGER']
            self.current_edit_entry = ttk.Combobox(self.tree,
                values=all_types,
                font=('Arial', 9), state='readonly')
            self.current_edit_entry.set('TRAFIK')
        elif col_name == 'SIRKET':
            self.current_edit_entry = ttk.Combobox(self.tree,
                values=['AXA', 'ALLIANZ', 'HDI', 'RAY', 'ETHICA', 'SOMPO', 'QUICK', 'DOGA', 'HEPIYI'],
                font=('Arial', 9), state='readonly')
            self.current_edit_entry.set('AXA')
        elif col_name == 'ACIKLAMA':
            self.current_edit_entry = ttk.Combobox(self.tree,
                values=['YASAR', 'KAMIL', 'TEZCAN', 'TEZER'],
                font=('Arial', 9))
        else:
            self.current_edit_entry = tk.Entry(self.tree, font=('Arial', 9))

        self.current_edit_entry.place(x=x, y=y, width=width, height=height)
        self.current_edit_entry.focus_set()

        def save_cell(e=None):
            value = self.current_edit_entry.get().strip()

            # Degeri kaydet
            db_field_map = {
                'SIGORTALI': 'sigortali', 'TARIH': 'tarih', 'MUSTERI_NO': 'musteri_no',
                'POLICE_NO': 'police_no', 'TUR': 'tur', 'SIRKET': 'sirket',
                'PLAKA': 'plaka', 'MARKA': 'marka', 'TUTAR': 'tutar',
                'ACIKLAMA': 'aciklama', 'REFERANS': 'referans', 'ILETISIM': 'iletisim'
            }
            self.new_row_data[db_field_map[col_name]] = value

            # Treeview'i guncelle
            current_values = list(self.tree.item(item, 'values'))
            current_values[col_index] = value if value else '-'
            self.tree.item(item, values=current_values)

            if self.current_edit_entry:
                self.current_edit_entry.destroy()
                self.current_edit_entry = None

            # Zorunlu alanlar dolu mu kontrol et
            self.check_and_save_inline_record()

        def cancel_cell(e=None):
            if self.current_edit_entry:
                self.current_edit_entry.destroy()
                self.current_edit_entry = None

        self.current_edit_entry.bind('<Return>', save_cell)
        self.current_edit_entry.bind('<Tab>', save_cell)
        self.current_edit_entry.bind('<Escape>', cancel_cell)
        self.current_edit_entry.bind('<FocusOut>', save_cell)

        if isinstance(self.current_edit_entry, ttk.Combobox):
            if col_name == 'TUR':
                def on_new_row_tur_selected(e=None):
                    if self.current_edit_entry.get() == 'DIGER':
                        self.current_edit_entry.destroy()
                        self.current_edit_entry = tk.Entry(self.tree, font=('Arial', 9))
                        self.current_edit_entry.place(x=x, y=y, width=width, height=height)
                        self.current_edit_entry.focus_set()
                        self.current_edit_entry.bind('<Return>', save_cell)
                        self.current_edit_entry.bind('<Tab>', save_cell)
                        self.current_edit_entry.bind('<Escape>', cancel_cell)
                        self.current_edit_entry.bind('<FocusOut>', save_cell)
                    else:
                        save_cell()
                self.current_edit_entry.bind('<<ComboboxSelected>>', on_new_row_tur_selected)
            else:
                self.current_edit_entry.bind('<<ComboboxSelected>>', save_cell)

    def check_and_save_inline_record(self):
        """Zorunlu alanlar doluysa kaydi veritabanina ekle"""
        required = ['sigortali', 'tarih', 'police_no', 'tur', 'sirket', 'tutar']

        for field in required:
            if field not in self.new_row_data or not self.new_row_data[field]:
                return  # Henuz doldurulmamis

        # Tum zorunlu alanlar dolu - kaydet
        try:
            data = [{
                'SIGORTALI': self.new_row_data.get('sigortali', '-'),
                'TARIH': self.new_row_data.get('tarih', '-'),
                'MUSTERI NO': self.new_row_data.get('musteri_no', '-'),
                'POLICE NO': self.new_row_data.get('police_no', '-'),
                'TUR': self.new_row_data.get('tur', '-'),
                'SIRKET': self.new_row_data.get('sirket', '-'),
                'PLAKA': self.new_row_data.get('plaka', '-'),
                'MARKA': self.new_row_data.get('marka', '-'),
                'TUTAR': self.new_row_data.get('tutar', '0'),
                'ACIKLAMA': self.new_row_data.get('aciklama', '-'),
                'REFERANS': self.new_row_data.get('referans', '-'),
                'ILETISIM': self.new_row_data.get('iletisim', '-')
            }]

            if TAYYARE_AVAILABLE and insert_police_data(self.db_manager.db_path, data):
                self.log(f"Yeni kayit eklendi: {self.new_row_data.get('sigortali')}", "success")

                # Durumu sifirla
                self.editing_new_row = False
                self.new_row_item = None
                self.new_row_data = {}

                # Cift tiklama eventini eski haline donudur
                self.tree.bind('<Double-Button-1>', self.on_tree_double_click)

                # Verileri yeniden yukle
                self.load_data()
                self.update_statistics()
            else:
                self.log("Kayit eklenemedi!", "error")
        except Exception as e:
            self.log(f"Hata: {e}", "error")

    def add_manual_entry(self):
        """Manuel kayit ekle"""
        # Manuel giris penceresi
        entry_win = tk.Toplevel(self.root)
        entry_win.title("Yeni Kayit Ekle")
        entry_win.geometry("500x600")
        entry_win.transient(self.root)
        entry_win.grab_set()

        # Alanlar
        fields = {
            'Sigortali': tk.Entry(entry_win, font=('Arial', 10)),
            'Tarih': tk.Entry(entry_win, font=('Arial', 10)),
            'Musteri No': tk.Entry(entry_win, font=('Arial', 10)),
            'Police No': tk.Entry(entry_win, font=('Arial', 10)),
            'Tur': ttk.Combobox(entry_win, values=['TRAFIK', 'KASKO', 'DASK', 'EVIM', 'SAGLIK', 'SEYAHAT', 'NAKLIYAT', 'ISYERI',
                                                  'GENEL FERDI KAZA', 'MAKINE KIRILMASI', 'CEP TELEFONU SIGORTASI',
                                                  'ACENTE MESLEKI SORUMLULUK', 'ELEKTRONIK CIHAZ', 'DIGER'], font=('Arial', 10)),
            'Sirket': ttk.Combobox(entry_win, values=['AXA', 'HDI', 'RAY', 'ETHICA', 'SOMPO', 'QUICK', 'DOGA', 'HEPIYI'], font=('Arial', 10), state='readonly'),
            'Plaka': tk.Entry(entry_win, font=('Arial', 10)),
            'Marka': tk.Entry(entry_win, font=('Arial', 10)),
            'Tutar': tk.Entry(entry_win, font=('Arial', 10)),
            'Aciklama': ttk.Combobox(entry_win, values=['YASAR', 'KAMIL', 'TEZCAN', 'TEZER'], font=('Arial', 10)),
            'Referans': tk.Text(entry_win, height=2, font=('Arial', 10)),
            'Iletisim': tk.Text(entry_win, height=2, font=('Arial', 10))
        }

        row = 0
        for label, widget in fields.items():
            tk.Label(entry_win, text=f"{label}:", font=('Arial', 9, 'bold')).grid(row=row, column=0, sticky='w', padx=10, pady=5)
            widget.grid(row=row, column=1, sticky='ew', padx=10, pady=5)
            row += 1

        entry_win.grid_columnconfigure(1, weight=1)

        def save_entry():
            data = [{
                'SIGORTALI': fields['Sigortali'].get(),
                'TARIH': fields['Tarih'].get(),
                'MUSTERI NO': fields['Musteri No'].get(),
                'POLICE NO': fields['Police No'].get(),
                'TUR': fields['Tur'].get(),
                'SIRKET': fields['Sirket'].get(),
                'PLAKA': fields['Plaka'].get(),
                'MARKA': fields['Marka'].get(),
                'TUTAR': fields['Tutar'].get(),
                'ACIKLAMA': fields['Aciklama'].get(),
                'REFERANS': fields['Referans'].get('1.0', tk.END).strip(),
                'ILETISIM': fields['Iletisim'].get('1.0', tk.END).strip()
            }]

            if insert_police_data(self.db_manager.db_path, data):
                self.log("Yeni kayit eklendi", "success")
                self.load_data()
                entry_win.destroy()
            else:
                messagebox.showerror("Hata", "Kayit eklenemedi!")

        btn_frame = tk.Frame(entry_win)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=20)

        tk.Button(btn_frame, text="Kaydet", command=save_entry, font=('Arial', 10, 'bold'), bg=COLORS['success'], fg='white', padx=20, pady=8).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Iptal", command=entry_win.destroy, font=('Arial', 10, 'bold'), bg=COLORS['danger'], fg='white', padx=20, pady=8).pack(side=tk.LEFT, padx=5)

    def edit_selected(self):
        """Secili kaydi duzenle"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Uyari", "Lutfen bir kayit secin!")
            return

        if len(selection) > 1:
            messagebox.showwarning("Uyari", "Lutfen tek bir kayit secin!")
            return

        # Kayit bilgilerini al
        values = self.tree.item(selection[0], 'values')
        record_id = values[0]

        # Duzenleme ozelligi devre disi birakildi
        return

    def delete_selected(self):
        """Secili kayitlari sil"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Uyari", "Lutfen kayit secin!")
            return

        if messagebox.askyesno("Onay", f"{len(selection)} kayit silinecek. Emin misiniz?"):
            for item in selection:
                values = self.tree.item(item, 'values')
                record_id = values[0]
                self.db_manager.delete_record(record_id)

            self.log(f"{len(selection)} kayit silindi", "warning")
            self.load_data()

    def delete_all_records(self):
        """Tum kayitlari sil"""
        # Once toplam kayit sayisini al
        df = self.db_manager.get_all_records()
        total_count = len(df)

        if total_count == 0:
            messagebox.showinfo("Bilgi", "Silinecek kayit yok!")
            return

        # Ilk onay
        response = messagebox.askyesno(
            "TEHLIKELI ISLEM",
            f"TUM {total_count} KAYIT SILINECEK!\n\nBu islem geri alinamaz.\n\nDevam etmek istediginizden emin misiniz?",
            icon='warning'
        )

        if not response:
            return

        # Ikinci onay (cift kontrol)
        response2 = messagebox.askyesno(
            "SON ONAY",
            f"Tekrar soruyoruz:\n\n{total_count} kayit kalici olarak silinecek!\n\nGercekten devam etmek istiyor musunuz?",
            icon='warning'
        )

        if not response2:
            self.log("Islem iptal edildi", "info")
            return

        try:
            # Tum kayitlari sil
            conn = sqlite3.connect(self.db_manager.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM policeler")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='policeler'")  # ID sifirla
            conn.commit()
            conn.close()

            self.log(f"TUM KAYITLAR SILINDI: {total_count} kayit", "warning")
            self.load_data()
            messagebox.showinfo("Tamamlandi", f"{total_count} kayit basariyla silindi!")

        except Exception as e:
            self.log(f"Silme hatasi: {str(e)}", "error")
            messagebox.showerror("Hata", f"Kayitlar silinirken hata olustu:\n{str(e)}")

    def show_details(self):
        """Kayit detaylarini goster"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Uyari", "Lutfen bir kayit secin!")
            return

        if len(selection) > 1:
            messagebox.showwarning("Uyari", "Lutfen tek bir kayit secin!")
            return

        # Detay gosterme devre disi birakildi
        return

    def sort_column(self, col):
        """Sutuna gore siralama - DEVRE DISI"""
        # Siralama ozelligi kaldirildi
        return

    def backup_database(self):
        """Veritabanini yedekle"""
        import shutil

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"policeler_backup_{timestamp}.db"

        filename = filedialog.asksaveasfilename(
            title="Veritabani Yedekle",
            defaultextension=".db",
            initialfile=backup_name,
            filetypes=[("Database files", "*.db"), ("All files", "*.*")]
        )

        if filename:
            try:
                shutil.copy2(self.db_manager.db_path, filename)
                self.log(f"Veritabani yedeklendi: {os.path.basename(filename)}", "success")
                messagebox.showinfo("Basarili", f"Veritabani yedeklendi:\n{filename}")
            except Exception as e:
                self.log(f"Yedekleme hatasi: {str(e)}", "error")
                messagebox.showerror("Hata", str(e))

    def show_company_report(self):
        """Sirket bazli rapor goster"""
        stats = self.db_manager.get_statistics()

        report = "SIRKET BAZLI RAPOR\n\n"
        for company, count in stats['company']:
            if company:
                report += f"{company}: {count} kayit\n"

        messagebox.showinfo("Sirket Bazli Rapor", report)

    def show_type_report(self):
        """Tur bazli rapor goster"""
        stats = self.db_manager.get_statistics()

        report = "TUR BAZLI RAPOR\n\n"
        for type_name, count in stats['type']:
            if type_name:
                report += f"{type_name}: {count} kayit\n"

        messagebox.showinfo("Tur Bazli Rapor", report)

    def show_monthly_summary(self):
        """Aylik ozet goster"""
        stats = self.db_manager.get_statistics()

        summary = f"""
AYLIK OZET

Bu Ay: {stats['this_month']} kayit
Toplam: {stats['total']} kayit
        """

        messagebox.showinfo("Aylik Ozet", summary)

    def log(self, message, level="info"):
        """Log ekle"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"

        self.log_text.insert(tk.END, log_entry, level)
        self.log_text.see(tk.END)

        # Durum cubugu
        self.status_bar.config(text=message)

    def clear_logs(self):
        """Loglari temizle"""
        self.log_text.delete('1.0', tk.END)
        self.log("Loglar temizlendi", "info")

    def show_help(self):
        """Yardim goster"""
        help_text = """
SIGORTA RAPOR VE KAYIT YONETIMI - KULLANIM KILAVUZU

1. PDF ISLEME
   - "PDF Klasoru Isle" butonuna tiklayin
   - PDF'lerin bulundugu klasoru secin
   - Otomatik isleme ve veritabanina kayit baslayacaktir

2. FILTRELEME VE ARAMA
   - Sol panelden filtre kriterlerini girin
   - "ARA" butonuna tiklayin
   - Sonuclar tabloda gorunitur

3. EXCEL RAPORU
   - "Excel'e Aktar" butonuna tiklayin
   - Kayit yerini secin
   - Tum veriler Excel formatinda kaydedilir

4. KAYIT YONETIMI
   - Yeni kayit eklemek icin "Yeni Kayit Ekle"
   - Kayit duzenlemek icin cift tiklayin
   - Kayit silmek icin secip "Sil" secenegini kullanin

5. VERITABANI
   - Tum veriler SQLite veritabaninda saklanir
   - "Veritabani Yedekle" menuunden yedek alabilirsiniz

Iyi calismalar!
        """

        help_win = tk.Toplevel(self.root)
        help_win.title("Yardim")
        help_win.geometry("700x600")

        text = tk.Text(help_win, wrap=tk.WORD, font=('Consolas', 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert('1.0', help_text)
        text.config(state='disabled')

    def show_about(self):
        """Hakkinda"""
        about_text = """
Sigorta Rapor ve Kayit Yonetimi
Versiyon: 1.0

Ozellikler:
- Otomatik PDF okuma ve veri cikarma
- SQLite veritabani entegrasyonu
- Gelismis filtreleme ve arama
- Excel raporlama
- Istatistik ve analiz
- Modern kullanici arayuzu

Desteklenen Sirketler:
HDI, RAY, ETHICA, SOMPO, QUICK, DOGA, HEPIYI

Gelistirme: 2026
        """
        messagebox.showinfo("Hakkinda", about_text)
