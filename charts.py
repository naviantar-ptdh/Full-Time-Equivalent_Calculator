"""
Chart builders (Plotly) — FTE Calculator PT Dharma Henwa (v6).

Aturan yang dipakai konsisten di seluruh file ini:

*   Satu chart menjawab satu pertanyaan. Tidak ada dua chart yang menampilkan
    angka yang sama dengan bentuk berbeda (masalah v4: line chart & bar chart
    isinya sama).

*   Pembagian warna tegas: chart yang membandingkan ROLE memakai
    `theme.ROLE_COLORS` (3 hue berbeda), chart yang membandingkan LEVEL
    memakai `theme.LEVEL_SHADES` (satu ramp orange, M1 paling pekat). Jadi
    pembaca tidak perlu menghafal dua sistem warna sekaligus.

*   Welder & Electrician nilainya company-wide, bukan per-section. Di v4
    keduanya digambar sebagai garis datar melintasi semua section, yang
    secara visual seolah-olah "ada nilainya di tiap section". Sekarang
    keduanya digambar sebagai batang terpisah di sebelah kanan, dipisahkan
    garis putus-putus + label "Company-wide", jadi bedanya jelas.

*   Angka ditulis dengan format Indonesia (ribuan pakai titik, desimal pakai
    koma). Plotly tidak bisa melakukan ini sendiri, jadi semua label & hover
    text disiapkan sebagai string dari Python.
"""
from __future__ import annotations

from typing import Dict, List

import plotly.graph_objects as go

from theme import (
    BRAND,
    LEVEL_SHADES,
    NEUTRAL,
    ROLE_COLORS,
    ROLE_LABEL,
)

FONT = dict(family="Public Sans, Segoe UI, sans-serif", size=11, color=NEUTRAL["text"])
HOVER = dict(
    bgcolor=BRAND["navy"],
    bordercolor=BRAND["navy"],
    font=dict(family="Public Sans, Segoe UI, sans-serif", color="#FFFFFF", size=11.5),
)
LEVELS = ["M1", "M2", "M3"]


def _layout(height: int, **kw) -> dict:
    base = dict(
        height=height,
        margin=dict(l=6, r=10, t=6, b=6),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=FONT,
        hoverlabel=HOVER,
        hovermode="closest",
        showlegend=False,
        dragmode=False,
    )
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Format angka gaya Indonesia
# ---------------------------------------------------------------------------
def num(x: float, dec: int = 0) -> str:
    s = f"{x:,.{dec}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def rp(x: float) -> str:
    return "Rp " + num(x)


def rp_short(x: float) -> str:
    """Rp 1,72 M / Rp 320 jt / Rp 4.500 — dipakai di gauge & KPI."""
    ax = abs(x)
    if ax >= 1_000_000_000:
        return "Rp " + num(x / 1_000_000_000, 2) + " M"
    if ax >= 1_000_000:
        return "Rp " + num(x / 1_000_000, 0) + " jt"
    return rp(x)


def _empty(height: int, msg: str = "Belum ada data untuk ditampilkan") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**_layout(height, xaxis=dict(visible=False), yaxis=dict(visible=False)))
    fig.add_annotation(
        text=msg, showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5,
        font=dict(family="Public Sans", size=12, color=NEUTRAL["text_soft"]),
    )
    return fig


# ---------------------------------------------------------------------------
# 1) Total FTE per section & per role — batang horizontal, warna per ROLE
# ---------------------------------------------------------------------------
def total_by_section_bar(
    mechanic_by_category: Dict[str, Dict[str, float]],
    welder_total: dict,
    electric_total: dict,
    height: int = 286,
) -> go.Figure:
    """Menjawab: 'kebutuhan FTE terbesar ada di mana?'

    Section mekanik diurutkan dari terkecil ke terbesar (Plotly menggambar
    kategori pertama di bawah, jadi hasilnya batang terpanjang di atas),
    lalu Welder & Electrician ditempel di bawah sebagai entitas company-wide.
    """
    items: List[tuple] = [
        (cat, sum(v.get(l, 0) for l in LEVELS), ROLE_COLORS["Mechanic"], "Mekanik")
        for cat, v in mechanic_by_category.items()
    ]
    items.sort(key=lambda t: t[1])

    tail = []
    if electric_total.get("Tot", 0):
        tail.append(("Electrician", electric_total["Tot"], ROLE_COLORS["Electric"], "Electrician"))
    if welder_total.get("Tot", 0):
        tail.append(("Welder", welder_total["Tot"], ROLE_COLORS["Welder"], "Welder"))
    items = tail + items

    if not items:
        return _empty(height)

    labels = [i[0] for i in items]
    values = [i[1] for i in items]
    colors = [i[2] for i in items]
    roles = [i[3] for i in items]
    grand = sum(values) or 1

    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
            text=[num(v) for v in values],
            textposition="outside",
            textfont=dict(family="Archivo", size=11, color=NEUTRAL["text"]),
            cliponaxis=False,
            hovertext=[
                f"<b>{lbl}</b><br>{r} · {num(v)} FTE<br>{num(v / grand * 100, 1)}% dari total site"
                for lbl, v, r in zip(labels, values, roles)
            ],
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )
    fig.update_layout(
        **_layout(
            height,
            margin=dict(l=6, r=42, t=6, b=6),
            xaxis=dict(visible=False, range=[0, max(values) * 1.16]),
            yaxis=dict(
                tickfont=dict(family="Public Sans", size=11, color=NEUTRAL["text"]),
                showgrid=False, ticksuffix="  ",
            ),
            bargap=0.32,
        )
    )
    return fig


# ---------------------------------------------------------------------------
# 2) Komposisi level M1–M3 — donut, warna per LEVEL
# ---------------------------------------------------------------------------
def level_donut(level_totals: Dict[str, float], height: int = 286) -> go.Figure:
    """Menjawab: 'seberapa berat komposisi tenaga senior vs junior?'

    Center hole dipakai untuk total FTE supaya tidak perlu KPI tambahan.
    """
    vals = [level_totals.get(l, 0) for l in LEVELS]
    total = sum(vals)
    if total <= 0:
        return _empty(height)

    from theme import LEVEL_NOTE

    fig = go.Figure(
        go.Pie(
            labels=[f"{l} · {LEVEL_NOTE[l]}" for l in LEVELS],
            values=vals,
            hole=0.62,
            sort=False,
            direction="clockwise",
            marker=dict(colors=[LEVEL_SHADES[l] for l in LEVELS], line=dict(color="#fff", width=2)),
            text=[f"{num(v / total * 100, 1)}%" for v in vals],
            textinfo="text",
            textposition="inside",
            insidetextorientation="horizontal",
            textfont=dict(family="Archivo", size=12, color="#fff"),
            hovertext=[
                f"<b>{l} ({LEVEL_NOTE[l]})</b><br>{num(v)} FTE · {num(v / total * 100, 1)}%"
                for l, v in zip(LEVELS, vals)
            ],
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )
    fig.add_annotation(
        text=(
            f"<span style='font-family:Archivo;font-size:26px;font-weight:800;color:{NEUTRAL['text']}'>{num(total)}</span>"
            f"<br><span style='font-size:10px;color:{NEUTRAL['text_muted']};letter-spacing:.08em'>TOTAL FTE</span>"
        ),
        showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5, align="center",
    )
    fig.update_layout(
        **_layout(
            height,
            margin=dict(l=6, r=6, t=6, b=26),
            showlegend=True,
            legend=dict(
                orientation="h", yanchor="top", y=0.02, xanchor="center", x=0.5,
                font=dict(family="Public Sans", size=10.5, color=NEUTRAL["text_muted"]),
            ),
        )
    )
    return fig


# ---------------------------------------------------------------------------
# 3) Persebaran M1–M3 per section — stacked bar, warna per LEVEL
# ---------------------------------------------------------------------------
def level_stack_by_section(
    mechanic_by_category: Dict[str, Dict[str, float]],
    welder_total: dict,
    electric_total: dict,
    height: int = 286,
) -> go.Figure:
    """Menjawab: 'di section mana komposisi seniornya paling berat?'

    Section mekanik di kiri; Welder & Electrician di kanan setelah garis
    pemisah, karena angkanya company-wide (bukan per-section).
    """
    sections = list(mechanic_by_category.keys())
    extras = []
    if welder_total.get("Tot", 0):
        extras.append(("Welder", welder_total))
    if electric_total.get("Tot", 0):
        extras.append(("Electrician", electric_total))

    x = sections + [e[0] for e in extras]
    if not x:
        return _empty(height)

    fig = go.Figure()
    for lvl in LEVELS:
        y, hover = [], []
        for cat in sections:
            v = mechanic_by_category[cat].get(lvl, 0)
            y.append(v)
            hover.append(f"<b>{cat}</b><br>Mekanik {lvl}: {num(v)} FTE")
        for name, tot in extras:
            v = tot.get(lvl, 0)
            y.append(v)
            hover.append(f"<b>{name}</b> (company-wide)<br>{lvl}: {num(v)} FTE")
        fig.add_trace(
            go.Bar(
                x=x, y=y, name=lvl,
                marker=dict(color=LEVEL_SHADES[lvl], line=dict(width=0)),
                hovertext=hover,
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )

    totals = [
        sum(mechanic_by_category[c].get(l, 0) for l in LEVELS) for c in sections
    ] + [sum(t.get(l, 0) for l in LEVELS) for _n, t in extras]
    fig.add_trace(
        go.Scatter(
            x=x, y=totals, mode="text",
            text=[num(t) for t in totals],
            textposition="top center",
            textfont=dict(family="Archivo", size=10.5, color=NEUTRAL["text"]),
            hoverinfo="skip", showlegend=False, cliponaxis=False,
        )
    )

    # garis pemisah antara section dan entitas company-wide
    if sections and extras:
        cut = len(sections) - 0.5
        fig.add_vline(x=cut, line=dict(color=NEUTRAL["border"], width=1.5, dash="dot"))
        fig.add_annotation(
            x=cut + (len(extras) / 2), xref="x", yref="paper", y=1.0,
            text="Company-wide", showarrow=False,
            font=dict(family="Public Sans", size=9.5, color=NEUTRAL["text_soft"]),
        )

    fig.update_layout(
        **_layout(
            height,
            barmode="stack",
            margin=dict(l=6, r=10, t=18, b=6),
            xaxis=dict(
                tickangle=-18, showgrid=False,
                tickfont=dict(family="Public Sans", size=10, color=NEUTRAL["text"]),
            ),
            yaxis=dict(
                gridcolor=NEUTRAL["border_soft"], zerolinecolor=NEUTRAL["border"],
                tickfont=dict(family="Public Sans", size=10, color=NEUTRAL["text_muted"]),
                range=[0, max(totals) * 1.16] if totals else None,
            ),
            bargap=0.34,
        )
    )
    return fig


# ---------------------------------------------------------------------------
# 4) Cost — busur komposisi (skala relatif antar-site)
# ---------------------------------------------------------------------------
def cost_gauge(
    cost_breakdown: dict,
    scale_max: float,
    avg: float | None = None,
    top_site: str | None = None,
    height: int = 208,
) -> go.Figure:
    """Busur setengah-donut: posisi DAN komposisi cost dalam satu bentuk.

    v6 memakai `go.Indicator` (speedometer klasik) untuk chart ini. Dua
    masalah muncul dari situ: (1) `go.Indicator` memang tidak mendukung
    hover sama sekali — itu batas Plotly, bukan pilihan desain — jadi tidak
    ada cara memberi tooltip di atasnya; (2) warna "steps"-nya cuma gradasi
    oranye generik, tidak menjelaskan apa-apa selain posisi jarum.

    Sekarang busurnya dibangun dari `go.Pie` (bukan Indicator), diputar dan
    disembunyikan separuh, supaya betul-betul bisa di-hover. Panjang busur
    berwarna = total cost site ini, dipecah per role (Mekanik/Electrician/
    Welder — warna sama seperti dipakai di seluruh dashboard); sisa busur
    abu-abu muda = jarak menuju site termahal. Jadi posisi batas
    warna-ke-abu ITU SENDIRI adalah "jarum"-nya — tidak perlu elemen
    terpisah, dan setiap segmen berwarna bisa di-hover untuk lihat rincian
    role-nya.
    """
    mech = cost_breakdown.get("Mechanic", {}).get("Tot", 0.0)
    elec = cost_breakdown.get("Electric", {}).get("Tot", 0.0)
    weld = cost_breakdown.get("Welder", {}).get("Tot", 0.0)
    total = mech + elec + weld
    scale_max = max(scale_max, total, 1.0)
    remainder = max(scale_max - total, 0.0)

    def seg_hover(role_label, v):
        return f"<b>{role_label}</b><br>{rp(v)} · {num(v / total * 100, 1)}% dari cost site ini" if total > 0 else ""

    # Separuh atas = data asli (mech, elec, weld, sisa). Separuh bawah =
    # satu slice bayangan sebesar total separuh atas (transparan), supaya
    # lingkaran penuh Plotly TAMPAK seperti busur setengah lingkaran saja.
    half_total = scale_max
    labels = ["Mekanik", "Electrician", "Welder", "Sisa kapasitas", ""]
    values = [mech, elec, weld, remainder, half_total]
    colors = [
        ROLE_COLORS["Mechanic"], ROLE_COLORS["Electric"], ROLE_COLORS["Welder"],
        NEUTRAL["border_soft"], "rgba(0,0,0,0)",
    ]
    hovertext = [
        seg_hover("Mekanik", mech), seg_hover("Electrician", elec), seg_hover("Welder", weld),
        f"<b>Sisa kapasitas</b><br>{rp(remainder)} menuju site termahal" if remainder > 0 else "",
        "",
    ]

    fig = go.Figure(
        go.Pie(
            labels=labels, values=values, hole=0.68,
            rotation=270, direction="clockwise", sort=False,
            marker=dict(colors=colors, line=dict(color="#fff", width=2)),
            textinfo="none",
            hovertext=hovertext,
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )

    pct = total / scale_max * 100 if scale_max else 0
    fig.add_annotation(
        text=(
            f"<span style='font-family:Archivo;font-size:26px;font-weight:800;color:{NEUTRAL['text']}'>{rp_short(total)}</span>"
            f"<br><span style='font-size:10px;color:{NEUTRAL['text_muted']}'>per bulan · {num(pct, 0)}% dari site termahal</span>"
        ),
        showarrow=False, xref="paper", yref="paper", x=0.5, y=0.48, align="center",
    )
    fig.update_layout(
        **_layout(
            height,
            margin=dict(l=10, r=10, t=6, b=0),
            showlegend=False,
        )
    )
    return fig


def cost_gauge_caption(scale_max: float, avg: float, top_site: str | None) -> str:
    """Keterangan busur — wajib ada, karena skalanya relatif."""
    site = f" (<b>{top_site}</b>)" if top_site else ""
    return (
        f'<div class="dh-note">Warna = komposisi cost per role di site ini. Abu-abu = jarak menuju '
        f'{rp_short(scale_max)}, yaitu cost site tertinggi{site}. Rata-rata antar-site: {rp_short(avg)}.</div>'
    )


# ---------------------------------------------------------------------------
# 5) Mode Kalkulator — donut per role untuk 1 jenis unit
# ---------------------------------------------------------------------------
def role_donut(fte_table: dict, height: int = 210) -> go.Figure:
    roles = ["Mechanic", "Electric", "Welder"]
    vals = [fte_table.get(r, {}).get("Tot", 0) for r in roles]
    total = sum(vals)
    if total <= 0:
        return _empty(height)

    fig = go.Figure(
        go.Pie(
            labels=[ROLE_LABEL[r] for r in roles],
            values=vals,
            hole=0.58, sort=False,
            marker=dict(colors=[ROLE_COLORS[r] for r in roles], line=dict(color="#fff", width=2)),
            textinfo="none",
            hovertext=[
                f"<b>{ROLE_LABEL[r]}</b><br>{num(v)} FTE · {num(v / total * 100, 1)}%"
                for r, v in zip(roles, vals)
            ],
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )
    fig.add_annotation(
        text=(
            f"<span style='font-family:Archivo;font-size:22px;font-weight:800;color:{NEUTRAL['text']}'>{num(total)}</span>"
            f"<br><span style='font-size:9.5px;color:{NEUTRAL['text_muted']};letter-spacing:.08em'>TOTAL FTE</span>"
        ),
        showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5,
    )
    fig.update_layout(
        **_layout(
            height,
            margin=dict(l=4, r=4, t=4, b=24),
            showlegend=True,
            legend=dict(
                orientation="h", yanchor="top", y=0.04, xanchor="center", x=0.5,
                font=dict(family="Public Sans", size=10, color=NEUTRAL["text_muted"]),
            ),
        )
    )
    return fig
