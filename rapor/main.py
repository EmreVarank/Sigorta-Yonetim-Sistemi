#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from gui import RaporGUI

def main():
    root = tk.Tk()
    app = RaporGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
