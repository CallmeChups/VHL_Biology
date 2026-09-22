"""
Module: app.py
Purpose: VHL Biology — step-by-step analysis wizard. One step per screen,
         time elapsed per step, back/forward navigation.
Version: 2.2.0
"""
import time

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

import backend_client as client
from backend_client import BackendError

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="VHL Biology Analysis", layout="wide", page_icon="🔬")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""<style>
    .main { background-color: #f0f2f5; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #f8fafc, #f1f5f9);
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 12px 16px;
    }
    .step-title { font-size: 26px; font-weight: 700; color: #1e293b; margin-bottom: 4px; }
    .step-desc  { font-size: 15px; color: #64748b; margin-bottom: 20px; line-height: 1.6; }
    .elapsed-badge {
        display: inline-block;
        background: #dcfce7;
        color: #15803d;
        border: 1px solid #86efac;
        border-radius: 20px;
        padding: 3px 12px;
        font-size: 13px;
        font-weight: 600;
        margin-bottom: 16px;
    }
</style>""", unsafe_allow_html=True)

# ── Session state defaults ────────────────────────────────────────────────────
_DEFAULTS: dict = dict(
    step=0,
    session_id=None, export_bytes=None,
    file_bytes=None, sample_name=None,
    do_array=None, signal_points=None, do_min=None, do_max=None,
    peaks_df=None,
    cls_pred=None, cls_prob=None, cls_error=None,
    phase_error=None,
    toxicity_df=None,
    tox_val=None, stage1_tag=None, stage2_tag=None, s1_ddo=None, s2_ddo=None,
    bod_enabled=False,
    bod_phase1=None,
    bod_phase2=None,
    bod_a=None,
    bod_b=None,
    step_times={},
)
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Navigation helpers ────────────────────────────────────────────────────────
def _go(n: int):
    st.session_state.step = n

def _reset():
    for k, v in _DEFAULTS.items():
        st.session_state[k] = {} if k == "step_times" else v

def _nav(back=None, nxt=None, nxt_label="Tiếp theo →", nxt_disabled=False):
    # Explicit unique keys prevent Streamlit from confusing buttons across steps
    cols = st.columns([1, 5, 1])
    with cols[0]:
        if back is not None:
            if st.button("← Quay lại", key=f"btn_back_{back}_{nxt}",
                         use_container_width=True):
                st.session_state.step = back
                st.rerun()
    with cols[2]:
        if nxt is not None:
            if st.button(nxt_label, key=f"btn_nxt_{back}_{nxt}",
                         disabled=nxt_disabled, use_container_width=True, type="primary"):
                st.session_state.step = nxt
                st.rerun()

# ── Step indicator ────────────────────────────────────────────────────────────
_LABEL_DISPLAY = {
    "gga":       "Organic Pollution",
    "gga-metal": "Metal Pollution",
}

def _get_step_labels() -> list:
    return ["Upload", "Peak Extraction", "Phase Detection",
            "BOD Concentration", "Classification", "Tổng kết"]

def _render_indicator():
    labels = _get_step_labels()
    cur = st.session_state.step
    parts = []
    for i, label in enumerate(labels):
        t = st.session_state.step_times.get(i)
        tstr = f" <small>✓{t}s</small>" if t else (" <small>✓</small>" if i < cur else "")
        if i < cur:
            parts.append(
                f'<span style="color:#16a34a;font-weight:600;">●&nbsp;{i+1}.&nbsp;{label}{tstr}</span>'
            )
        elif i == cur:
            parts.append(
                f'<span style="color:#1d4ed8;font-weight:700;border-bottom:2px solid #1d4ed8;">'
                f'●&nbsp;{i+1}.&nbsp;{label}</span>'
            )
        else:
            parts.append(f'<span style="color:#94a3b8;">○&nbsp;{i+1}.&nbsp;{label}</span>')
    st.markdown("&nbsp;&nbsp;→&nbsp;&nbsp;".join(parts), unsafe_allow_html=True)
    st.markdown("<hr style='margin:10px 0 20px'>", unsafe_allow_html=True)

# ── Flow diagram helper ───────────────────────────────────────────────────────
_BOX_CSS = (
    "background:{bg};border:1.5px solid {border};border-radius:8px;"
    "padding:7px 9px;text-align:center;font-size:11px;font-weight:500;"
    "color:{tc};line-height:1.5;"
)

def _flow(nodes: list) -> None:
    """Render a vertical flowchart with colored boxes.
    nodes: dicts {label, bg, border, tc} or strings "↓" / "↓ edge-label",
           or lists [node, node] for side-by-side branches.
    """
    parts = ['<div style="display:flex;flex-direction:column;gap:4px;padding:4px 0;">']
    for n in nodes:
        if isinstance(n, str):
            edge = n.replace("↓", "").strip()
            parts.append('<div style="text-align:center;color:#94a3b8;font-size:16px;line-height:1.2;">↓</div>')
            if edge:
                parts.append(f'<div style="text-align:center;color:#64748b;font-size:9px;margin-top:-4px;">{edge}</div>')
        elif isinstance(n, list):
            row = '<div style="display:flex;gap:4px;">'
            for b in n:
                row += (f'<div style="flex:1;{_BOX_CSS.format(**b)}">'
                        + b["label"].replace("\n", "<br>") + "</div>")
            row += "</div>"
            parts.append(row)
        else:
            parts.append(f'<div style="{_BOX_CSS.format(**n)}">'
                         + n["label"].replace("\n", "<br>") + "</div>")
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)

# ── Signal chart (cached figure build) ───────────────────────────────────────
@st.cache_data(show_spinner=False)
def _build_chart_fig(do_array: np.ndarray, peak_xs: tuple = (), peak_ys: tuple = (), height: int = 380):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=do_array, mode="lines",
        line=dict(color="#3b82f6", width=1.3), name="DO Signal",
    ))
    if peak_xs:
        fig.add_trace(go.Scatter(
            x=list(peak_xs), y=list(peak_ys), mode="markers",
            marker=dict(color="#ef4444", size=9, symbol="x", line=dict(width=2)),
            name="Peaks",
        ))
    fig.update_layout(
        yaxis_title="DO (mV)", xaxis_title="Data Point",
        template="plotly_white", height=height,
        margin=dict(l=50, r=10, t=25, b=40),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
    )
    return fig

def _signal_chart(do_array, peaks_df=None, height=380):
    xs, ys = [], []
    if peaks_df is not None and len(peaks_df) > 0 and "No.peak" in peaks_df.columns:
        for x in peaks_df["No.peak"].dropna().astype(int).tolist():
            if 0 <= x < len(do_array):
                xs.append(x)
                ys.append(float(do_array[x]))
    fig = _build_chart_fig(do_array, tuple(xs), tuple(ys), height)
    st.plotly_chart(fig, use_container_width=True)

# ── Tag coloring ──────────────────────────────────────────────────────────────
def _color_tag(row):
    tag = str(row.get("Tag", "")).strip().lower()
    if tag == "phase1" or "bod10" in tag:
        return ["background-color:#FEF9C3"] * len(row)
    if tag == "transition":
        return ["background-color:#FECACA"] * len(row)
    if tag == "phase2" or "bod5" in tag:
        return ["background-color:#DBEAFE"] * len(row)
    return [""] * len(row)

# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 0 — UPLOAD
# ═══════════════════════════════════════════════════════════════════════════════
def render_step_0():
    st.markdown('<p class="step-title">📁 Bước 1 — Tải lên dữ liệu</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="step-desc">'
        'Tải lên file đo DO từ thiết bị (định dạng UTF-16, cột Time / DO). '
        'Hệ thống sẽ vẽ tín hiệu thô để bạn kiểm tra trước khi phân tích.'
        '</p>',
        unsafe_allow_html=True,
    )

    col_main, col_diag = st.columns([3, 1])
    with col_diag:
        _flow([
            {"label": "🔬 Thiết bị DO\n(Sensor)", "bg": "#dbeafe", "border": "#60a5fa", "tc": "#1e40af"},
            "↓",
            {"label": "📄 File .txt\nUTF-16 encoding", "bg": "#f0fdf4", "border": "#4ade80", "tc": "#166534"},
            "↓",
            {"label": "⚙️ Parse\n→ DO array", "bg": "#fef9c3", "border": "#fbbf24", "tc": "#92400e"},
        ])

    with col_main:
        uploaded = st.file_uploader(
            "Chọn file .txt (UTF-16, Time/DO columns)",
            type=["txt"],
            label_visibility="collapsed",
        )

        if uploaded:
            name = uploaded.name.replace(".txt", "").strip()
            if st.session_state.sample_name != name:
                with st.spinner("Đang đọc tín hiệu..."):
                    uploaded.seek(0)
                    file_bytes = uploaded.read()
                    try:
                        session_id = client.create_session()
                        resp = client.upload(session_id, uploaded.name, file_bytes)
                    except BackendError as e:
                        st.error(str(e))
                        st.stop()
                st.session_state.update(dict(
                    session_id=session_id,
                    file_bytes=file_bytes, sample_name=resp["sample_name"],
                    do_array=np.array(resp["do_array"]), signal_points=resp["signal_points"],
                    do_min=resp["do_min"], do_max=resp["do_max"],
                    peaks_df=None, cls_pred=None, cls_prob=None,
                    cls_error=None, phase_error=None, toxicity_df=None,
                    tox_val=None, stage1_tag=None, stage2_tag=None,
                    s1_ddo=None, s2_ddo=None, step_times={}, export_bytes=None,
                ))

            if st.session_state.do_array is not None:
                c1, c2, c3 = st.columns(3)
                c1.metric("Tín hiệu", f"{st.session_state.signal_points:,} pts")
                c2.metric("DO min", f"{st.session_state.do_min:.2f} mV")
                c3.metric("DO max", f"{st.session_state.do_max:.2f} mV")
                _signal_chart(st.session_state.do_array, height=320)

            st.markdown("---")
            _nav(nxt=1, nxt_label="▶ Bắt đầu phân tích")

        elif st.session_state.file_bytes is not None:
            # Navigating back — existing file already in session, no re-upload needed
            st.success(f"✅ File đã tải: **{st.session_state.sample_name}**  ·  Tải file mới phía trên để thay thế.")
            c1, c2, c3 = st.columns(3)
            c1.metric("Tín hiệu", f"{st.session_state.signal_points:,} pts")
            c2.metric("DO min", f"{st.session_state.do_min:.2f} mV")
            c3.metric("DO max", f"{st.session_state.do_max:.2f} mV")
            _signal_chart(st.session_state.do_array, height=320)
            st.markdown("---")
            _nav(nxt=1, nxt_label="▶ Tiếp tục phân tích")

        else:
            st.info("📁 Upload file .txt để bắt đầu.")


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — PEAK EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════
def render_step_1():
    st.markdown('<p class="step-title">⛏️ Bước 2 — Trích xuất Peak</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="step-desc">'
        'Thuật toán 2-pass phát hiện các điểm <b>DOin</b> (nồng độ ban đầu) và '
        '<b>DOmin</b> (nồng độ đáy) trong mỗi chu kỳ đo. '
        '<b>DDO = DOin − DOmin</b> là độ suy giảm oxy dùng để phân tích sau. '
        'HH signal được tự động nhận diện và tái trích xuất với thông số riêng.'
        '</p>',
        unsafe_allow_html=True,
    )

    col_main, col_diag = st.columns([3, 1])
    with col_diag:
        _flow([
            {"label": "📈 DO array", "bg": "#dbeafe", "border": "#60a5fa", "tc": "#1e40af"},
            "↓ Pass 1",
            {"label": "🔍 Smooth\nMinima detect\nFind plateau", "bg": "#f0fdf4", "border": "#4ade80", "tc": "#166534"},
            "↓",
            {"label": "◇ DDO P90 > 12mV?\nYes ▶ Pass 2 (HH)\nNo  ▶ done", "bg": "#fefce8", "border": "#fbbf24", "tc": "#92400e"},
            "↓",
            {"label": "📋 peaks_df\nDOin · DOmin\nDDO · No.peak", "bg": "#ede9fe", "border": "#a78bfa", "tc": "#5b21b6"},
        ])

    with col_main:
        if st.session_state.peaks_df is None:
            with st.spinner("Đang trích xuất peak..."):
                t0 = time.time()
                try:
                    records = client.extract_peaks(st.session_state.session_id)
                    st.session_state.peaks_df = client.records_to_df(records)
                    st.session_state.step_times[1] = round(time.time() - t0, 2)
                except BackendError as e:
                    st.error(str(e))
                    st.stop()

        peaks_df = st.session_state.peaks_df
        elapsed = st.session_state.step_times.get(1)
        if elapsed:
            st.markdown(f'<span class="elapsed-badge">⏱ {elapsed}s</span>', unsafe_allow_html=True)

        ddo_min = peaks_df["DDO (mV)"].min()
        ddo_max = peaks_df["DDO (mV)"].max()
        c1, c2, c3 = st.columns(3)
        c1.metric("Peaks phát hiện", len(peaks_df))
        c2.metric("DDO min", f"{ddo_min:.2f} mV")
        c3.metric("DDO max", f"{ddo_max:.2f} mV")

        _signal_chart(st.session_state.do_array, peaks_df=peaks_df, height=300)

        display_df = peaks_df[["No.peak", "Tag", "Doin (mV)", "DOmin (mV)", "DDO (mV)"]].copy()
        st.dataframe(
            display_df.style.format({"Doin (mV)": "{:.2f}", "DOmin (mV)": "{:.2f}", "DDO (mV)": "{:.2f}"}),
            use_container_width=True, height=280,
        )

    st.markdown("---")
    _nav(back=0, nxt=2)


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 4 — CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════
def render_step_2():
    st.markdown('<p class="step-title">🧬 Bước 5 — Phân loại mẫu</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="step-desc">'
        'Mô hình <b>CatBoost</b> (81 đặc trưng, accuracy 84.4% trên 518 file) phân loại '
        'mẫu thành <b>Organic Pollution</b> (nước thải sinh hoạt) hoặc '
        '<b>Metal Pollution</b> (có kim loại nặng). '
        'Kết quả này được dùng để phân biệt Organic Pollution và Metal Pollution trong báo cáo.'
        '</p>',
        unsafe_allow_html=True,
    )

    col_main, col_diag = st.columns([3, 1])
    with col_diag:
        _flow([
            {"label": "📋 peaks_df\n81 features", "bg": "#dbeafe", "border": "#60a5fa", "tc": "#1e40af"},
            "↓",
            {"label": "🤖 CatBoost\niter=300, depth=8\n84.4% accuracy", "bg": "#f0fdf4", "border": "#4ade80", "tc": "#166534"},
            "↓",
            [
                {"label": "🟢 GGA", "bg": "#dcfce7", "border": "#4ade80", "tc": "#166534"},
                {"label": "🔶 Metal", "bg": "#fef3c7", "border": "#fbbf24", "tc": "#92400e"},
            ],
            "↓",
            {"label": "🎯 Probability\n(confidence %)", "bg": "#ede9fe", "border": "#a78bfa", "tc": "#5b21b6"},
        ])

    with col_main:
        if st.session_state.cls_pred is None:
            with st.spinner("Đang phân loại mẫu..."):
                t0 = time.time()
                try:
                    resp = client.classify(st.session_state.session_id)
                    st.session_state.cls_pred = resp["cls_pred"]
                    st.session_state.cls_prob = resp["cls_prob"]
                except Exception as e:
                    st.session_state.cls_pred = "Lỗi"
                    st.session_state.cls_prob = 0.0
                    st.session_state.cls_error = str(e)
                st.session_state.step_times[4] = round(time.time() - t0, 2)

        elapsed = st.session_state.step_times.get(4)
        if elapsed:
            st.markdown(f'<span class="elapsed-badge">⏱ {elapsed}s</span>', unsafe_allow_html=True)

        cls = st.session_state.cls_pred or "—"
        cls_display = _LABEL_DISPLAY.get(cls, cls)
        prob = st.session_state.cls_prob or 0.0
        is_err = cls == "Lỗi"
        bg = "linear-gradient(135deg,#fff7ed,#ffedd5)" if is_err else "linear-gradient(135deg,#f0fdf4,#dcfce7)"
        border = "#fb923c" if is_err else "#86efac"
        text_color = "#c2410c" if is_err else "#15803d"

        st.markdown(f"""
        <div style="text-align:center;padding:48px 24px;background:{bg};
             border-radius:16px;border:2px solid {border};margin:8px 0 24px;">
            <div style="font-size:13px;color:#64748b;margin-bottom:8px;letter-spacing:.06em;">
                KẾT QUẢ PHÂN LOẠI
            </div>
            <div style="font-size:64px;font-weight:800;color:{text_color};line-height:1.1;">
                {cls_display}
            </div>
            <div style="font-size:22px;color:#94a3b8;margin-top:10px;">
                {prob * 100:.1f}% xác suất
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.cls_error:
            with st.expander("Chi tiết lỗi"):
                st.code(st.session_state.cls_error)

        if (st.session_state.cls_pred or "") != "gga" and st.session_state.tox_val is None:
            try:
                tox = client.toxicity(st.session_state.session_id)
                st.session_state.update(
                    tox_val=tox["tox_val"],
                    stage1_tag=tox["stage1"],
                    stage2_tag=tox["stage2"],
                    s1_ddo=tox["s1_ddo"],
                    s2_ddo=tox["s2_ddo"],
                )
            except BackendError as e:
                st.session_state.phase_error = str(e)

    st.markdown("---")
    _nav(back=3, nxt=5)


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — PHASE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════
def render_step_3():
    st.markdown('<p class="step-title">🔍 Bước 3 — Phát hiện ranh giới pha</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="step-desc">'
        'Mỗi peak được gán nhãn <b>phase1</b> (ổn định ban đầu), '
        '<b>transition</b> (vùng chuyển tiếp không ổn định), '
        'hoặc <b>phase2</b> (ổn định cuối). '
        'Bước này chạy trước classification bằng thuật toán change-point chung để '
        'tạo phase1, transition và phase2 cho cả hai loại mẫu. Toxicity sẽ tính '
        'trên phase1 vs phase2, bỏ qua transition.'
        '</p>',
        unsafe_allow_html=True,
    )

    col_main, col_diag = st.columns([3, 1])
    with col_diag:
        _flow([
            {"label": "📋 peaks_df", "bg": "#dbeafe", "border": "#60a5fa", "tc": "#1e40af"},
            "↓",
            {"label": "◇ Generic change-point\nn&lt;8 → fallback\nphase1 → transition → phase2", "bg": "#fefce8", "border": "#fbbf24", "tc": "#92400e"},
            "↓",
            [
                {"label": "🟡 phase1", "bg": "#fef9c3", "border": "#fbbf24", "tc": "#92400e"},
                {"label": "🔴 trans.", "bg": "#fee2e2", "border": "#f87171", "tc": "#b91c1c"},
                {"label": "🔵 phase2", "bg": "#dbeafe", "border": "#60a5fa", "tc": "#1e40af"},
            ],
        ])

    with col_main:
        if "phase_confidence" not in st.session_state.peaks_df.columns:
            with st.spinner("Đang phát hiện ranh giới pha..."):
                t0 = time.time()
                try:
                    records = client.detect_phase(st.session_state.session_id)
                    st.session_state.peaks_df = client.records_to_df(records)
                except Exception as e:
                    st.session_state.phase_error = str(e)
                st.session_state.step_times[2] = round(time.time() - t0, 2)

        peaks_df = st.session_state.peaks_df
        elapsed = st.session_state.step_times.get(2)
        if elapsed:
            st.markdown(f'<span class="elapsed-badge">⏱ {elapsed}s</span>', unsafe_allow_html=True)

        # Phase distribution
        tag_counts = peaks_df["Tag"].value_counts()
        cols_tags = st.columns(max(len(tag_counts), 1))
        color_map = {"phase1": ("#ca8a04", "#fef9c3", "#fbbf24"),
                     "transition": ("#dc2626", "#fee2e2", "#fca5a5"),
                     "phase2": ("#1d4ed8", "#dbeafe", "#93c5fd")}
        for i, (tag, cnt) in enumerate(tag_counts.items()):
            tc, bg, border = color_map.get(tag.lower(), ("#475569", "#f8fafc", "#cbd5e1"))
            with cols_tags[i]:
                st.markdown(f"""<div style="text-align:center;padding:20px 12px;background:{bg};
                     border-radius:10px;border:1.5px solid {border};margin-bottom:12px;">
                    <div style="font-size:34px;font-weight:800;color:{tc};">{cnt}</div>
                    <div style="font-size:13px;color:#475569;font-weight:600;">{tag}</div>
                </div>""", unsafe_allow_html=True)

        # Low confidence warning
        if "phase_confidence" in peaks_df.columns:
            non_t = peaks_df[peaks_df["Tag"].isin(["phase1", "phase2"])]
            if not non_t.empty and float(non_t["phase_confidence"].mean()) < 0.6:
                st.warning(f"⚠ Phase confidence thấp ({non_t['phase_confidence'].mean():.2f}). "
                           "Kết quả toxicity có thể không chính xác.")

        if st.session_state.phase_error:
            st.error(f"Lỗi phase detection: {st.session_state.phase_error}")

        display_df = peaks_df[["No.peak", "Tag", "Doin (mV)", "DOmin (mV)", "DDO (mV)"]].copy()
        styled = (display_df.style
                  .apply(_color_tag, axis=1)
                  .format({"Doin (mV)": "{:.2f}", "DOmin (mV)": "{:.2f}", "DDO (mV)": "{:.2f}"}))
        st.dataframe(styled, use_container_width=True, height=380)

    st.markdown("---")
    _nav(back=1, nxt=3)


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 4 — TOXICITY
# ═══════════════════════════════════════════════════════════════════════════════
def render_step_4():
    st.markdown('<p class="step-title">☣️ Bước 5 — Tính độc tính</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="step-desc">'
        'Độ độc tính phản ánh mức độ ức chế vi sinh vật trong mẫu nước. '
        'Công thức: <b>Toxicity = (DDO₁ − DDO₂) / DDO₁ × 100%</b> — '
        'so sánh DDO trung bình của phase1 và phase2. '
        'Các peak <i>transition</i> bị loại bỏ để tránh nhiễu tính toán.'
        '</p>',
        unsafe_allow_html=True,
    )

    col_main, col_diag = st.columns([3, 1])
    with col_diag:
        _flow([
            {"label": "📋 peaks_df\n(with Tags)", "bg": "#dbeafe", "border": "#60a5fa", "tc": "#1e40af"},
            "↓",
            {"label": "🚫 Filter\nskip transition", "bg": "#fee2e2", "border": "#f87171", "tc": "#b91c1c"},
            "↓",
            [
                {"label": "🟢 phase1\nDDO₁ mean", "bg": "#dcfce7", "border": "#4ade80", "tc": "#166534"},
                {"label": "🔵 phase2\nDDO₂ mean", "bg": "#dbeafe", "border": "#60a5fa", "tc": "#1e40af"},
            ],
            "↓",
            {"label": "☣️ Toxicity %\n(DDO₁−DDO₂)\n÷ DDO₁ × 100", "bg": "#fef9c3", "border": "#fbbf24", "tc": "#92400e"},
        ])

    with col_main:
        if st.session_state.toxicity_df is None:
            with st.spinner("Đang tính độc tính..."):
                t0 = time.time()
                try:
                    resp = client.toxicity(st.session_state.session_id)
                except BackendError as e:
                    st.error(str(e))
                    st.stop()
                st.session_state.toxicity_df = True  # marks this step as computed
                st.session_state.update(dict(
                    tox_val=resp["tox_val"], stage1_tag=resp["stage1"],
                    stage2_tag=resp["stage2"], s1_ddo=resp["s1_ddo"], s2_ddo=resp["s2_ddo"],
                ))
                st.session_state.step_times[4] = round(time.time() - t0, 2)

        elapsed = st.session_state.step_times.get(4)
        if elapsed:
            st.markdown(f'<span class="elapsed-badge">⏱ {elapsed}s</span>', unsafe_allow_html=True)

        tox_val = st.session_state.tox_val
        stage1 = st.session_state.stage1_tag
        stage2 = st.session_state.stage2_tag
        s1_ddo = st.session_state.s1_ddo
        s2_ddo = st.session_state.s2_ddo

        peaks_df = st.session_state.peaks_df
        s1_peaks = peaks_df[peaks_df["Tag"].str.strip() == str(stage1).strip()] if stage1 else pd.DataFrame()
        s2_peaks = peaks_df[peaks_df["Tag"].str.strip() == str(stage2).strip()] if stage2 else pd.DataFrame()

        c1, c2, c3 = st.columns(3)
        with c1:
            s1_str = f"{s1_ddo:.3f} mV" if s1_ddo is not None else "N/A"
            st.markdown(f"""<div style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);
                 border:2px solid #86efac;border-radius:14px;padding:28px;text-align:center;">
                <div style="color:#166534;font-size:11px;font-weight:700;letter-spacing:.06em;">
                    STAGE 1 · {stage1 or "—"}</div>
                <div style="font-size:32px;font-weight:800;color:#15803d;margin:8px 0;">{s1_str}</div>
                <div style="color:#64748b;font-size:12px;">{len(s1_peaks)} peaks · DDO₁ trung bình</div>
            </div>""", unsafe_allow_html=True)

        with c2:
            tox_str   = f"{tox_val}%" if tox_val is not None else "N/A"
            tox_color = "#b45309" if tox_val is not None else "#64748b"
            st.markdown(f"""<div style="background:linear-gradient(135deg,#fefce8,#fef9c3);
                 border:2px solid #fbbf24;border-radius:14px;padding:28px;text-align:center;">
                <div style="color:#92400e;font-size:11px;font-weight:700;letter-spacing:.06em;">
                    ĐỘ ĐỘC / TOXICITY</div>
                <div style="font-size:52px;font-weight:800;color:{tox_color};margin:8px 0;">
                    {tox_str}</div>
                <div style="color:#78350f;font-size:11px;">(DDO₁ − DDO₂) / DDO₁ × 100</div>
            </div>""", unsafe_allow_html=True)

        with c3:
            s2_str = f"{s2_ddo:.3f} mV" if s2_ddo is not None else "N/A"
            st.markdown(f"""<div style="background:linear-gradient(135deg,#eff6ff,#dbeafe);
                 border:2px solid #93c5fd;border-radius:14px;padding:28px;text-align:center;">
                <div style="color:#1e40af;font-size:11px;font-weight:700;letter-spacing:.06em;">
                    STAGE 2 · {stage2 or "—"}</div>
                <div style="font-size:32px;font-weight:800;color:#1d4ed8;margin:8px 0;">{s2_str}</div>
                <div style="color:#64748b;font-size:12px;">{len(s2_peaks)} peaks · DDO₂ trung bình</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("---")
    _nav(back=3, nxt=5, nxt_label="Xem tổng kết →")


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — BOD CONCENTRATION
# ═══════════════════════════════════════════════════════════════════════════════
def render_step_4_bod():
    st.markdown('<p class="step-title">📊 Bước 4 — Tính nồng độ BOD</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="step-desc">'
        'Nhập 2 điểm hiệu chuẩn (BOD, DDO) để xác định đường tuyến tính '
        '<b>DDO = a · BOD + b</b>. Hệ thống sẽ suy ngược DDO của từng pha '
        'để tính nồng độ BOD tương ứng.'
        '</p>',
        unsafe_allow_html=True,
    )

    # Use the same GGA calibration for both Organic and Metal samples.
    peaks_df = st.session_state.peaks_df
    p1 = peaks_df[peaks_df["Tag"].str.strip() == "phase1"]
    p2 = peaks_df[peaks_df["Tag"].str.strip() == "phase2"]
    ddo_p1 = float(p1["DDO (mV)"].mean()) if not p1.empty else None
    ddo_p2 = float(p2["DDO (mV)"].mean()) if not p2.empty else None

    if ddo_p1 is None or ddo_p2 is None:
        st.error("Không tìm thấy đủ peaks phase1 / phase2 để tính DDO. Quay lại bước trước.")
        _nav(back=2, nxt=None)
        return

    col_form, col_result = st.columns([1, 1])

    with col_form:
        st.markdown("**Nhập điểm hiệu chuẩn**")
        st.info(
            f"DDO phase1 từ pipeline: **{ddo_p1:.3f} mV**  \n"
            f"DDO phase2 từ pipeline: **{ddo_p2:.3f} mV**"
        )
        r1c1, r1c2 = st.columns(2)
        bod1 = r1c1.number_input("BOD₁ (mg/L)", min_value=0.0, value=20.0, step=0.1, key="bod1_cal")
        ddo1 = r1c2.number_input("DDO₁ (mV)",   min_value=0.0, value=11.3, step=0.1, key="ddo1_cal")
        r2c1, r2c2 = st.columns(2)
        bod2 = r2c1.number_input("BOD₂ (mg/L)", min_value=0.0, value=15.0, step=0.1, key="bod2_cal")
        ddo2 = r2c2.number_input("DDO₂ (mV)",   min_value=0.0, value=9.13, step=0.01, key="ddo2_cal")
        st.caption("Hai điểm này xác định đường tuyến tính DDO = a · BOD + b")

    with col_result:
        st.markdown("**Kết quả**")
        valid = bod1 > 0 and ddo1 > 0 and bod2 > 0 and ddo2 > 0
        if not valid:
            st.warning("Nhập đầy đủ 4 giá trị > 0 để tính.")
        else:
            try:
                t0 = time.time()
                res = client.bod_calibration(
                    st.session_state.session_id,
                    bod1=bod1, ddo1=ddo1, bod2=bod2, ddo2=ddo2,
                )
                st.session_state.step_times[3] = round(time.time() - t0, 2)
                st.session_state.update(dict(
                    bod_phase1=res["bod_phase1"],
                    bod_phase2=res["bod_phase2"],
                    bod_a=res["a"],
                    bod_b=res["b"],
                ))
                st.markdown(f"""
                <div style="background:#f0fdf4;border:1.5px solid #86efac;border-radius:10px;
                     padding:18px 20px;margin-bottom:12px;">
                    <div style="font-size:13px;color:#64748b;margin-bottom:6px;">Phương trình hiệu chuẩn</div>
                    <div style="font-size:18px;font-weight:700;color:#15803d;">
                        DDO = {res['a']:.4f} · BOD + {res['b']:.4f}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                c1.metric("BOD Phase 1", f"{res['bod_phase1']:.3f} mg/L",
                          help=f"DDO phase1 = {ddo_p1:.3f} mV")
                c2.metric("BOD Phase 2", f"{res['bod_phase2']:.3f} mg/L",
                          help=f"DDO phase2 = {ddo_p2:.3f} mV")
            except BackendError as e:
                st.error(str(e))

    st.markdown("---")
    _nav(back=2, nxt=4)


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 5 — SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
def render_step_5():
    st.markdown('<p class="step-title">📊 Tổng kết kết quả</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="step-desc">'
        'Toàn bộ kết quả phân tích được tổng hợp ở đây. '
        'Bạn có thể xuất báo cáo Excel hoặc quay lại bất kỳ bước nào để xem lại chi tiết.'
        '</p>',
        unsafe_allow_html=True,
    )

    peaks_df  = st.session_state.peaks_df
    tox_val   = st.session_state.tox_val
    stage1    = st.session_state.stage1_tag
    stage2    = st.session_state.stage2_tag
    s1_ddo    = st.session_state.s1_ddo
    s2_ddo    = st.session_state.s2_ddo

    # ── metric cards ─────────────────────────────────────────────────────────
    tag_counts = peaks_df["Tag"].value_counts()
    bod_str = " · ".join(f"{cnt} {tag}" for tag, cnt in tag_counts.items())

    cls_display = _LABEL_DISPLAY.get(st.session_state.cls_pred or "", st.session_state.cls_pred or "—")

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        st.metric("Số Peak", len(peaks_df))
        st.caption(bod_str)
    with c2:
        st.metric("Phân loại", cls_display,
                  help=f"{(st.session_state.cls_prob or 0) * 100:.1f}% xác suất")
        st.caption(f"{(st.session_state.cls_prob or 0) * 100:.1f}% xác suất")
    with c3:
        st.metric("BOD Phase 1", f"{st.session_state.bod_phase1:.3f} mg/L"
                  if st.session_state.bod_phase1 is not None else "N/A")
    with c4:
        st.metric("BOD Phase 2", f"{st.session_state.bod_phase2:.3f} mg/L"
                  if st.session_state.bod_phase2 is not None else "N/A")
    with c5:
        st.metric("Độ độc", f"{tox_val}%" if tox_val is not None else "N/A")
        if stage1 and stage2:
            st.caption(f"{stage1} → {stage2}")
    with c6:
        st.metric("Tín hiệu", f"{st.session_state.signal_points:,} pts")
        st.caption(f"{st.session_state.do_min:.2f} – {st.session_state.do_max:.2f} mV")

    st.markdown("---")

    # ── Timeline ──────────────────────────────────────────────────────────────
    st.markdown("### ⏱ Thời gian xử lý")
    step_name_map = {
        1: "Peak Extraction",
        2: "Phase Detection",
        3: "BOD Concentration",
        4: "Classification",
    }
    rows, total = [], 0.0
    for i, name in step_name_map.items():
        t = st.session_state.step_times.get(i, 0.0)
        total += t
        rows.append({"Bước": name, "Thời gian": f"{t}s"})
    rows.append({"Bước": "**Tổng cộng**", "Thời gian": f"**{total:.2f}s**"})
    st.table(pd.DataFrame(rows))

    st.markdown("---")

    # ── Export + Reset ────────────────────────────────────────────────────────
    if st.session_state.export_bytes is None:
        try:
            st.session_state.export_bytes = client.export_report(st.session_state.session_id)
        except BackendError as e:
            st.error(str(e))

    dl_col, reset_col = st.columns(2)
    with dl_col:
        st.download_button(
            label="📥 Xuất Excel Report",
            data=st.session_state.export_bytes or b"",
            file_name=f"VHL_Report_{st.session_state.sample_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, type="primary",
            disabled=st.session_state.export_bytes is None,
        )
    with reset_col:
        if st.button("🔄 Phân tích mẫu mới", key="btn_reset", use_container_width=True):
            _reset()
            st.rerun()

    _nav(back=4)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════
_RENDERERS = [render_step_0, render_step_1, render_step_3,
              render_step_4_bod, render_step_2, render_step_5]

# Header
st.markdown("""
<div style="background:linear-gradient(135deg,#1a365d,#2d5d8a);padding:16px 24px;
     border-radius:12px;margin-bottom:16px;display:flex;
     justify-content:space-between;align-items:center;">
    <div>
        <span style="color:white;font-size:22px;font-weight:700;">🔬 VHL Biology Analysis</span>
        <span style="color:rgba(255,255,255,0.6);font-size:13px;margin-left:14px;">
            Phân tích DO &amp; Phân loại mẫu sinh học
        </span>
    </div>
    <span style="background:rgba(255,255,255,0.15);padding:4px 12px;border-radius:6px;
          color:white;font-size:12px;">v2.2.0</span>
</div>
""", unsafe_allow_html=True)

_render_indicator()

def _dispatch():
    step = st.session_state.step
    _RENDERERS[step]()

_dispatch()

st.markdown("---")
st.caption("VHL Biology Analysis · Powered by Streamlit · v2.2.0")
