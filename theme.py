"""
Design system — FTE Calculator PT Dharma Henwa (v6, "Looker light").

Arah desain (dipilih user): TERANG, mengikuti nuansa dashboard Looker Studio
PTDH — header band gradasi orange dengan logo putih, kartu putih di atas
background abu terang, judul kartu berwarna sesuai aksen, dan strip navy
gelap untuk legenda/readout.

Tiga hal yang diperbaiki dari v5:

1.  KARTU SEKARANG BENAR-BENAR MEMBUNGKUS ISINYA.
    v5 membuka `<div class="ptdh-card">` lewat st.markdown lalu menutupnya
    di st.markdown berikutnya. Itu tidak pernah bekerja: Streamlit merender
    tiap markdown di container terpisah, jadi browser menutup div-nya
    sendiri dan chart jatuh DI LUAR kartu (kartu tampil sebagai strip putih
    kosong). Sekarang kartu dibangun dari `st.container(key=...)` +
    selector `div[class*="st-key-card_"]`, jadi apa pun yang dirender di
    dalam blok `with theme.card(...)` benar-benar berada di dalam kartu.

2.  WARNA ROLE DIPISAH BERDASARKAN HUE, BUKAN CUMA LIGHTNESS.
    v5 memakai orange #FF6805, salmon #FF9182, dan kuning-tua #E0A400 —
    ketiganya hue 15–45°, jadi Mechanic/Welder/Electrician tampak seperti
    satu warna yang buram. Sekarang: Mechanic = orange brand (populasi
    terbesar, layak dapat warna brand), Electrician = kuning listrik,
    Welder = biru-teal (warna busur las). Ketiganya masih dalam keluarga
    swatch PTDH (orange primary, yellow & steel-blue secondary).

3.  ANGKA MEMAKAI TABULAR NUMERALS.
    Kolom angka pada tabel/KPI tidak lagi "goyang" saat nilainya berubah.

Pembagian tugas warna dibuat tegas supaya tidak ada dua sistem warna yang
bersaing dalam satu layar:
    - Chart yang membandingkan ROLE   -> pakai ROLE_COLORS (3 hue berbeda).
    - Chart yang membandingkan LEVEL  -> pakai LEVEL_SHADES (1 ramp orange).
"""
from __future__ import annotations

import base64
import colorsys
from contextlib import contextmanager
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
IMAGES_DIR = ASSETS_DIR / "images"

# ---------------------------------------------------------------------------
# Token warna
# ---------------------------------------------------------------------------
BRAND = {
    "orange": "#FF6805",     # primary swatch PTDH
    "orange_deep": "#D94E00",
    "header_l": "#FF8A0D",   # ujung kiri gradasi header — dari sampel referensi
    "amber": "#FFC21A",      # ujung kanan gradasi header — dari sampel referensi
    "navy": "#101B2D",       # strip legenda & readout gelap
}

# Satu hue per role. Jarak hue-nya sengaja lebar (24° / 46° / 187°) supaya
# ketiganya tetap terbaca saat dicetak hitam-putih maupun dilihat penderita
# deuteranopia.
ROLE_COLORS = {
    "Mechanic": "#FF6805",   # orange brand
    "Electric": "#FFC300",   # kuning listrik (swatch Yellow, dinaikkan saturasinya)
    "Welder": "#0E7C86",     # biru-teal busur las (turunan swatch Steel Blue)
}

# Ramp untuk perbandingan LEVEL (M1 senior -> M3 junior). Sengaja satu hue
# supaya jelas ini "urutan", bukan "kategori".
LEVEL_SHADES = {
    "M1": "#D94E00",
    "M2": "#FF8A3D",
    "M3": "#FFC9A3",
}

STATUS = {
    "good": "#12A150",
    "warn": "#F5A524",
    "bad": "#E5484D",
}

NEUTRAL = {
    "bg": "#F1F3F7",
    "card": "#FFFFFF",
    "border": "#E3E7EF",
    "border_soft": "#EEF1F6",
    "text": "#111827",
    "text_muted": "#67707F",
    "text_soft": "#98A1AF",
    "wash": "#F7F9FC",
}

FONT_DISPLAY = "'Archivo', 'Segoe UI', sans-serif"
FONT_BODY = "'Public Sans', 'Segoe UI', sans-serif"

ROLE_LABEL = {
    "Mechanic": "Mekanik",
    "Welder": "Welder",
    "Electric": "Electrician",
}

ROLE_ICON_FILE = {
    "Mechanic": "mechanic.png",
    "Welder": "welding.png",
    "Electric": "electrician.png",
}

LEVEL_NOTE = {
    "M1": "Senior",
    "M2": "Madya",
    "M3": "Junior",
}


# ---------------------------------------------------------------------------
# Shade generator — gradasi natural dari satu warna dasar
# ---------------------------------------------------------------------------
def _hex_to_hls(hex_color: str):
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def _hls_to_hex(h, l, s) -> str:
    l = min(max(l, 0.0), 1.0)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def shades_from_base(hex_color: str, levels=("M1", "M2", "M3")) -> dict:
    """Level pertama paling gelap (senior), terakhir paling terang (junior).

    Arahnya dibalik dibanding v5: di semua chart, nilai yang "lebih berat"
    (M1 = paling mahal, paling senior) sekarang selalu jadi warna paling
    pekat, jadi bobot visualnya sejalan dengan bobot maknanya.
    """
    h, l, s = _hex_to_hls(hex_color)
    n = len(levels)
    out = {}
    for i, lvl in enumerate(levels):
        if n == 1:
            out[lvl] = hex_color
            continue
        t = i / (n - 1)
        if t <= 0.5:
            dt = (0.5 - t) / 0.5
            out[lvl] = _hls_to_hex(h, max(l - dt * 0.16, 0.16), s * (1 - dt * 0.08))
        else:
            dt = (t - 0.5) / 0.5
            out[lvl] = _hls_to_hex(h, min(l + dt * 0.30, 0.90), s * (1 - dt * 0.18))
    return out


ROLE_SHADES = {role: shades_from_base(base) for role, base in ROLE_COLORS.items()}


def tint(hex_color: str, amount: float = 0.88) -> str:
    """Campur warna dengan putih. amount=0.88 -> 88% putih (latar ikon/chip)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    r = round(r + (255 - r) * amount)
    g = round(g + (255 - g) * amount)
    b = round(b + (255 - b) * amount)
    return "#{:02X}{:02X}{:02X}".format(r, g, b)


# ---------------------------------------------------------------------------
# Asset helpers
# ---------------------------------------------------------------------------
def _data_uri(path: Path) -> str | None:
    if not path.is_file():
        return None
    ext = path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


def image_uri(name: str) -> str | None:
    return _data_uri(IMAGES_DIR / name)


def role_icon_uri(role: str) -> str | None:
    return image_uri(ROLE_ICON_FILE.get(role, ""))


_ICON_CACHE: dict[str, str] = {}


def icon_svg(name: str, size: int = 16, color: str | None = None) -> str:
    """Inline <svg> dari assets/icons/<n>.svg, warnanya ikut currentColor."""
    import re

    raw = _ICON_CACHE.get(name)
    if raw is None:
        p = ICONS_DIR / f"{name}.svg"
        if not p.is_file():
            return ""
        raw = p.read_text(encoding="utf-8")
        _ICON_CACHE[name] = raw
    svg = re.sub(r'stroke="#[0-9a-fA-F]{3,6}"', 'stroke="currentColor"', raw)
    svg = re.sub(r'fill="#[0-9a-fA-F]{3,6}"', 'fill="currentColor"', svg)
    svg = re.sub(r'width="\d+(px)?"', f'width="{size}"', svg)
    svg = re.sub(r'height="\d+(px)?"', f'height="{size}"', svg)
    style = "display:inline-flex;align-items:center;"
    if color:
        style += f"color:{color};"
    return f'<span style="{style}">{svg}</span>'


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
def inject_css():
    import streamlit as st

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800&family=Public+Sans:wght@400;500;600;700;800&display=swap');

        :root {{
            --dh-orange: {BRAND['orange']};
            --dh-orange-deep: {BRAND['orange_deep']};
            --dh-amber: {BRAND['amber']};
            --dh-navy: {BRAND['navy']};
            --dh-border: {NEUTRAL['border']};
            --dh-text: {NEUTRAL['text']};
            --dh-muted: {NEUTRAL['text_muted']};
        }}

        html, body, .stApp, [class*="css"] {{ font-family: {FONT_BODY}; }}
        .stApp {{ background: {NEUTRAL['bg']}; }}
        h1, h2, h3, h4, h5 {{ font-family: {FONT_DISPLAY}; color: {NEUTRAL['text']}; }}

        /* full-bleed: dashboard Looker memakai seluruh lebar layar */
        .block-container {{
            padding: 0.45rem 1.4rem 2rem 1.4rem !important;
            max-width: 100% !important;
        }}
        header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
        #MainMenu, footer {{ visibility: hidden; }}
        div[data-testid="stDecoration"] {{ display: none; }}

        /* angka tidak goyang saat berubah */
        .dh-num, .dh-table td, .kpi .value, .kpi .sub {{ font-variant-numeric: tabular-nums; }}

        /* =====================================================
           HEADER BAND (orange gradient, logo putih) — signature
           ===================================================== */
        .dh-band {{
            background: linear-gradient(100deg, {BRAND['header_l']} 0%, {BRAND['orange']} 38%, {BRAND['amber']} 100%);
            border-radius: 14px;
            padding: 14px 20px;
            display: flex; align-items: center; gap: 18px;
            margin-bottom: 14px;
            box-shadow: 0 6px 18px -8px rgba(217,78,0,.55);
        }}
        .dh-band .logo {{ height: 40px; width: auto; flex: 0 0 auto; }}
        .dh-band .rule {{ width: 1px; height: 34px; background: rgba(255,255,255,.45); }}
        .dh-band .heading {{ flex: 1 1 auto; min-width: 0; }}
        .dh-band .heading .title {{
            font-family: {FONT_DISPLAY}; font-weight: 800; font-size: 21px;
            color: #fff; line-height: 1.15; letter-spacing: -.01em;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .dh-band .heading .sub {{
            font-size: 11.5px; color: rgba(255,255,255,.85); font-weight: 500; margin-top: 1px;
        }}
        .dh-band .chips {{ display: flex; gap: 8px; flex: 0 0 auto; flex-wrap: wrap; justify-content: flex-end; }}
        .dh-band .chip {{
            background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.35);
            border-radius: 999px; padding: 5px 12px; color: #fff;
            font-size: 11.5px; font-weight: 600; backdrop-filter: blur(2px);
        }}
        .dh-band .chip b {{ font-weight: 800; }}

        /* strip navy: legenda / catatan skala */
        .dh-strip {{
            background: {BRAND['navy']}; border-radius: 10px;
            padding: 8px 16px; margin-bottom: 14px;
            display: flex; align-items: center; justify-content: space-between;
            gap: 14px; flex-wrap: wrap;
        }}
        .dh-strip .left {{ color: #C3CBD9; font-size: 11.5px; font-weight: 600; }}
        .dh-strip .items {{ display: flex; gap: 16px; flex-wrap: wrap; }}
        .dh-strip .item {{
            display: inline-flex; align-items: center; gap: 6px;
            color: #E8ECF3; font-size: 11.5px; font-weight: 600;
        }}
        .dh-strip .item .sw {{ width: 9px; height: 9px; border-radius: 50%; }}

        /* =====================================================
           KPI CARD
           ===================================================== */
        .kpi {{
            background: {NEUTRAL['card']};
            border: 1px solid {NEUTRAL['border']};
            border-top: 3px solid var(--accent, {BRAND['orange']});
            border-radius: 12px;
            padding: 11px 13px;
            display: flex; align-items: center; gap: 11px;
            box-shadow: 0 1px 2px rgba(17,24,39,.05);
            min-height: 88px;
        }}
        .kpi .ico {{
            width: 42px; height: 42px; border-radius: 50%;
            background: var(--tint, #FFF0E6);
            display: flex; align-items: center; justify-content: center;
            flex: 0 0 auto;
        }}
        .kpi .ico img {{ width: 24px; height: 24px; object-fit: contain; }}
        .kpi .ico span {{ font-size: 19px; line-height: 1; }}
        .kpi .body {{ min-width: 0; }}
        .kpi .label {{
            font-size: 10px; font-weight: 700; letter-spacing: .07em;
            text-transform: uppercase; color: {NEUTRAL['text_muted']};
        }}
        .kpi .value {{
            font-family: {FONT_DISPLAY}; font-size: var(--vsize, 25px); font-weight: 800;
            color: {NEUTRAL['text']}; line-height: 1.1; letter-spacing: -.02em;
            white-space: nowrap;
        }}
        .kpi .value small {{ font-size: 13px; font-weight: 700; color: {NEUTRAL['text_muted']}; }}
        .kpi .sub {{
            font-size: 10.5px; color: {NEUTRAL['text_muted']}; margin-top: 2px;
            white-space: normal; line-height: 1.35; overflow-wrap: break-word;
        }}
        .kpi .sub b {{ color: {NEUTRAL['text']}; font-weight: 700; }}

        /* =====================================================
           CARD — dibangun dari st.container(key="card_*") supaya
           isinya benar-benar terbungkus (lihat docstring file)
           ===================================================== */
        /* Streamlit meregangkan kartu di dalam st.columns supaya setinggi
           kolom TERTINGGI dalam baris (default flex align-items:stretch di
           stHorizontalBlock). Itu penyebab ruang kosong besar di bawah kartu
           yang isinya lebih pendek dari kartu sebelahnya — dikeluhkan di
           mode Kalkulator (kartu Parameter) dan mode Basecase (kartu
           Persebaran M1-M3). Kartu dipaksa mengikuti tinggi isinya sendiri. */
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            align-items: flex-start !important;
        }}
        div[class*="st-key-card_"] {{
            background: {NEUTRAL['card']};
            border: 1px solid {NEUTRAL['border']};
            border-radius: 12px;
            padding: 12px 14px 8px 14px;
            box-shadow: 0 1px 2px rgba(17,24,39,.05);
            height: auto !important;
            flex-grow: 0 !important;
            align-self: flex-start !important;
            width: 100%;
        }}
        div[class*="st-key-card_"] {{ gap: 0.35rem !important; }}
        div[class*="st-key-card_"] div[data-testid="stVerticalBlock"] {{ gap: 0.35rem !important; }}
        div[class*="st-key-card_"] div[data-testid="stCaptionContainer"] p {{ margin-bottom: 0; }}

        .dh-card-head {{
            display: flex; align-items: center; gap: 8px;
            padding-bottom: 8px; margin-bottom: 4px;
            border-bottom: 1px solid {NEUTRAL['border_soft']};
        }}
        .dh-card-head .bar {{
            width: 3px; height: 15px; border-radius: 2px;
            background: var(--accent, {BRAND['orange']}); flex: 0 0 auto;
        }}
        .dh-card-head .t {{
            font-family: {FONT_DISPLAY}; font-weight: 700; font-size: 13px;
            color: var(--accent, {BRAND['orange']}); letter-spacing: -.005em;
        }}
        .dh-card-head .s {{
            font-size: 11px; color: {NEUTRAL['text_soft']}; font-weight: 500;
            margin-left: auto; text-align: right;
        }}

        /* =====================================================
           SIDEBAR — terang, aksen orange
           ===================================================== */
        section[data-testid="stSidebar"] {{
            background: {NEUTRAL['card']} !important;
            border-right: 1px solid {NEUTRAL['border']};
            min-width: 268px !important;
        }}
        section[data-testid="stSidebar"] .dh-side-brand {{
            display: flex; align-items: center; gap: 10px;
            padding: 2px 0 14px 0; margin-bottom: 8px;
            border-bottom: 1px solid {NEUTRAL['border_soft']};
        }}
        section[data-testid="stSidebar"] .dh-side-brand .mark {{
            width: 34px; height: 34px; border-radius: 9px; flex: 0 0 auto;
            background: linear-gradient(135deg, {BRAND['orange_deep']}, {BRAND['amber']});
            display: flex; align-items: center; justify-content: center;
        }}
        section[data-testid="stSidebar"] .dh-side-brand .mark img {{ width: 22px; height: 22px; }}
        section[data-testid="stSidebar"] .dh-side-brand .title {{
            font-family: {FONT_DISPLAY}; font-weight: 800; font-size: 14px; color: {NEUTRAL['text']};
        }}
        section[data-testid="stSidebar"] .dh-side-brand .subtitle {{
            font-size: 10.5px; color: {NEUTRAL['text_muted']};
        }}
        .dh-side-label {{
            font-size: 9.5px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase;
            color: {NEUTRAL['text_soft']}; margin: 14px 0 6px 0;
        }}
        section[data-testid="stSidebar"] label p {{
            font-size: 10.5px !important; font-weight: 700 !important;
            text-transform: uppercase; letter-spacing: .04em;
            color: {NEUTRAL['text_muted']} !important;
        }}

        /* nav pill */
        div[class*="st-key-nav_"] button {{
            background: transparent !important;
            color: {NEUTRAL['text_muted']} !important;
            border: 1px solid {NEUTRAL['border']} !important;
            border-radius: 9px !important;
            font-weight: 600 !important; font-size: 13px !important;
            justify-content: flex-start !important; text-align: left !important;
            height: 40px; padding-left: 12px !important;
        }}
        div[class*="st-key-nav_"] button:hover {{
            border-color: {BRAND['orange']} !important; color: {BRAND['orange']} !important;
            background: {tint(BRAND['orange'], .94)} !important;
        }}
        div[class*="st-key-nav_"] button[kind="primary"] {{
            background: linear-gradient(135deg, {BRAND['orange_deep']}, {BRAND['orange']}) !important;
            border-color: transparent !important; color: #fff !important;
            box-shadow: 0 4px 10px -4px rgba(217,78,0,.6);
        }}

        /* tombol utama */
        div[class*="st-key-sb_compute"] button, div[class*="st-key-calc_go"] button {{
            background: linear-gradient(135deg, {BRAND['orange_deep']}, {BRAND['orange']}) !important;
            color: #fff !important; border: none !important;
            font-weight: 800 !important; border-radius: 9px !important; height: 42px;
            box-shadow: 0 4px 12px -4px rgba(217,78,0,.6);
        }}
        div[class*="st-key-sb_compute"] button:disabled, div[class*="st-key-calc_go"] button:disabled {{
            background: {NEUTRAL['border']} !important; color: {NEUTRAL['text_soft']} !important;
            box-shadow: none;
        }}
        div[class*="st-key-sb_refresh"] button {{
            background: {NEUTRAL['wash']} !important; color: {NEUTRAL['text_muted']} !important;
            border: 1px solid {NEUTRAL['border']} !important; border-radius: 9px !important; height: 42px;
            font-weight: 600 !important;
        }}

        /* slider & select aksen orange */
        div[data-baseweb="slider"] div[role="slider"] {{ background: {BRAND['orange']} !important; }}
        .stSlider [data-testid="stTickBar"] {{ display: none; }}

        /* =====================================================
           TABS
           ===================================================== */
        div[data-testid="stTabs"] button[role="tab"] {{
            font-weight: 700 !important; font-size: 12.5px !important;
            color: {NEUTRAL['text_muted']} !important;
        }}
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
            color: {BRAND['orange']} !important;
        }}
        div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] {{
            background: {BRAND['orange']} !important;
        }}

        /* =====================================================
           TABEL
           ===================================================== */
        .dh-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
        .dh-table th {{
            text-align: right; font-weight: 700; font-size: 9.5px; letter-spacing: .07em;
            text-transform: uppercase; color: #fff; background: {BRAND['navy']};
            padding: 7px 10px;
        }}
        .dh-table th:first-child {{ text-align: left; border-radius: 6px 0 0 0; }}
        .dh-table th:last-child {{ border-radius: 0 6px 0 0; }}
        .dh-table td {{
            text-align: right; padding: 6px 10px; color: {NEUTRAL['text']};
            border-bottom: 1px solid {NEUTRAL['border_soft']};
        }}
        .dh-table td:first-child {{ text-align: left; font-weight: 600; }}
        .dh-table tbody tr:nth-child(even) td {{ background: {NEUTRAL['wash']}; }}
        /* Kolom TOTAL: latarnya tint oranye TERANG, jadi teksnya HARUS gelap.
           Sebelumnya th.tc mewarisi color:#fff dari aturan `th` di atas —
           putih di atas tint terang jadi nyaris tak kelihatan. */
        .dh-table td.tc, .dh-table th.tc {{
            font-weight: 800; background: {tint(BRAND['orange'], .93)};
            color: {BRAND['orange_deep']} !important;
        }}
        .dh-table tbody tr:nth-child(even) td.tc {{ background: {tint(BRAND['orange'], .89)}; }}
        .dh-table tr.tr-total td {{
            font-weight: 800; background: {BRAND['navy']} !important; color: #fff; border-bottom: none;
        }}
        .dh-table tr.tr-total td:first-child {{ border-radius: 0 0 0 6px; }}
        /* Sel TOTAL di baris TOTAL: latar oranye solid, putih di atasnya
           kontrasnya rendah — dipakai teks navy gelap supaya tetap terbaca. */
        .dh-table tr.tr-total td.tc {{
            background: {BRAND['amber']} !important; color: {BRAND['navy']} !important;
        }}
        .dh-table tr.tr-total td:last-child {{ border-radius: 0 0 6px 0; }}

        div[data-testid="stDataFrame"] {{
            border-radius: 10px; overflow: hidden; border: 1px solid {NEUTRAL['border']};
        }}
        div[data-testid="stDataFrame"] table {{ font-size: 12px !important; }}

        /* =====================================================
           MISC
           ===================================================== */
        .dh-empty {{
            border: 1.5px dashed {NEUTRAL['border']}; border-radius: 14px;
            background: {NEUTRAL['card']}; padding: 34px 26px; text-align: center;
        }}
        .dh-empty .ico {{
            width: 54px; height: 54px; border-radius: 50%; margin: 0 auto 12px auto;
            background: {tint(BRAND['orange'], .9)};
            display: flex; align-items: center; justify-content: center; font-size: 24px;
        }}
        .dh-empty h4 {{ margin: 0 0 4px 0; font-size: 15px; font-weight: 700; }}
        .dh-empty p {{ margin: 0; font-size: 12.5px; color: {NEUTRAL['text_muted']}; }}

        .dh-readout {{
            background: {BRAND['navy']}; border-radius: 12px; padding: 16px 18px; color: #fff;
        }}
        .dh-readout .label {{
            font-size: 9.5px; letter-spacing: .12em; text-transform: uppercase; color: #8896AC; font-weight: 700;
        }}
        .dh-readout .big {{
            font-family: {FONT_DISPLAY}; font-size: 42px; font-weight: 800; line-height: 1.05;
            color: #fff; letter-spacing: -.02em; font-variant-numeric: tabular-nums;
        }}
        .dh-readout .lv {{ display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }}
        .dh-readout .lv span {{
            background: rgba(255,255,255,.09); border: 1px solid rgba(255,255,255,.14);
            border-radius: 7px; padding: 4px 9px; font-size: 11px; color: #C3CBD9; font-weight: 600;
        }}
        .dh-readout .lv span b {{ color: #fff; font-weight: 800; }}
        .dh-readout .cost {{
            margin-top: 12px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,.12);
            font-size: 12px; color: #8896AC; font-weight: 600;
        }}
        .dh-readout .cost b {{ color: {BRAND['amber']}; font-weight: 800; }}

        .dh-note {{
            font-size: 11px; color: {NEUTRAL['text_soft']}; margin-top: 2px;
        }}
        .dh-legend {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 4px; }}
        .dh-legend .it {{
            display: inline-flex; align-items: center; gap: 5px;
            font-size: 11px; font-weight: 600; color: {NEUTRAL['text_muted']};
        }}
        .dh-legend .it .sw {{ width: 10px; height: 10px; border-radius: 3px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Komponen
# ---------------------------------------------------------------------------
def header_band(title: str, subtitle: str = "", chips: list[str] | None = None) -> str:
    logo = image_uri("logo_putih.png")
    logo_html = f'<img class="logo" src="{logo}" alt="PT Dharma Henwa"/><div class="rule"></div>' if logo else ""
    chips_html = "".join(f'<div class="chip">{c}</div>' for c in (chips or []))
    return (
        f'<div class="dh-band">{logo_html}'
        f'<div class="heading"><div class="title">{title}</div>'
        f'<div class="sub">{subtitle}</div></div>'
        f'<div class="chips">{chips_html}</div></div>'
    )


def legend_strip(left: str, items: list[tuple[str, str]]) -> str:
    """items = [(label, hex), ...]"""
    its = "".join(
        f'<div class="item"><span class="sw" style="background:{c}"></span>{lbl}</div>'
        for lbl, c in items
    )
    return f'<div class="dh-strip"><div class="left">{left}</div><div class="items">{its}</div></div>'


def kpi_card(label: str, value: str, sub: str = "", accent: str | None = None,
             role: str | None = None, emoji: str = "", value_size: int = 25) -> str:
    accent = accent or (ROLE_COLORS.get(role or "", BRAND["orange"]))
    uri = role_icon_uri(role) if role else None
    if uri:
        ico = f'<img src="{uri}" alt=""/>'
    else:
        ico = f"<span>{emoji}</span>"
    return (
        f'<div class="kpi" style="--accent:{accent};--tint:{tint(accent, .88)};--vsize:{value_size}px">'
        f'<div class="ico">{ico}</div>'
        f'<div class="body"><div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="sub">{sub}</div></div></div>'
    )


@contextmanager
def card(key: str, title: str = "", sub: str = "", accent: str | None = None):
    """Kartu yang benar-benar membungkus isinya.

    Pemakaian:
        with theme.card("cost", "Estimasi Cost", "per bulan"):
            st.plotly_chart(fig)
    """
    import streamlit as st

    accent = accent or BRAND["orange"]
    container = st.container(key=f"card_{key}")
    with container:
        if title:
            s = f'<div class="s">{sub}</div>' if sub else ""
            st.markdown(
                f'<div class="dh-card-head" style="--accent:{accent}">'
                f'<span class="bar"></span><span class="t">{title}</span>{s}</div>',
                unsafe_allow_html=True,
            )
        yield container


def table_html(headers: list[str], rows: list[list], total_row: list | None = None,
               total_col: int | None = None) -> str:
    """Tabel ringkas dengan kolom total DAN baris total sekaligus."""
    def cls(i):
        return ' class="tc"' if total_col is not None and i == total_col else ""

    thead = "<tr>" + "".join(f"<th{cls(i)}>{h}</th>" for i, h in enumerate(headers)) + "</tr>"
    tbody = "".join(
        "<tr>" + "".join(f"<td{cls(i)}>{v}</td>" for i, v in enumerate(r)) + "</tr>"
        for r in rows
    )
    if total_row is not None:
        tbody += '<tr class="tr-total">' + "".join(
            f"<td{cls(i)}>{v}</td>" for i, v in enumerate(total_row)
        ) + "</tr>"
    return f'<table class="dh-table"><thead>{thead}</thead><tbody>{tbody}</tbody></table>'


def empty_state(title: str, body: str, emoji: str = "📊") -> str:
    return (
        f'<div class="dh-empty"><div class="ico">{emoji}</div>'
        f"<h4>{title}</h4><p>{body}</p></div>"
    )


def legend_html(items: list[tuple[str, str]]) -> str:
    its = "".join(
        f'<div class="it"><span class="sw" style="background:{c}"></span>{lbl}</div>'
        for lbl, c in items
    )
    return f'<div class="dh-legend">{its}</div>'
