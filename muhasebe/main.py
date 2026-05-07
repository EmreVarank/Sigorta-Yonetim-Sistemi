#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'parsers'))

import tkinter as tk
from gui import MuhasebeGUI

def main():
    root = tk.Tk()
    app = MuhasebeGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
