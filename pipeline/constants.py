"""
Numbers and paths shared by the whole pipeline (Short length limits, output size, fonts folder).
"""
from settings import ROOT


FONTS_DIR = ROOT / "fonts"


MIN_LEN = 15      # seconds


MAX_LEN = 59      # keep Shorts under a minute; they perform best short


OUT_W, OUT_H = 1080, 1920
