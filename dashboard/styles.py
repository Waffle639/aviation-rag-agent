"""Visual styling for Aviation RAG Evaluations."""

from __future__ import annotations


CSS = """
<style>
:root {
  --navy: #081621;
  --panel: #102536;
  --panel-2: #163348;
  --surface: #f4f7f9;
  --card: #ffffff;
  --ink: #16222d;
  --muted: #66798b;
  --cyan: #22c7d6;
  --amber: #f5a524;
  --green: #23bfa5;
  --red: #ef6474;
  --line: #d9e3ea;
}

.stApp {
  background:
    linear-gradient(180deg, rgba(8, 22, 33, 0.04), rgba(8, 22, 33, 0) 220px),
    var(--surface);
  color: var(--ink);
}

.block-container {
  padding-top: 0.65rem;
}

section.main > div {
  padding-top: 0.3rem;
}

.dashboard-header {
  position: relative;
  overflow: hidden;
  padding: 0.95rem 1.15rem;
  border-radius: 16px;
  background:
    radial-gradient(circle at 88% 18%, rgba(34, 199, 214, 0.22), transparent 26%),
    linear-gradient(135deg, rgba(34, 199, 214, 0.14), rgba(245, 165, 36, 0.06)),
    var(--navy);
  color: white;
  box-shadow: 0 18px 48px rgba(8, 22, 33, 0.18);
  border: 1px solid rgba(34, 199, 214, 0.22);
}

.dashboard-header::after {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px);
  background-size: 28px 28px;
  pointer-events: none;
}

.dashboard-header h1 {
  margin: 0;
  font-size: clamp(1.55rem, 2.8vw, 2.35rem);
  letter-spacing: -0.04em;
  line-height: 0.98;
  text-transform: none;
}

.dashboard-header p {
  margin: 0.36rem 0 0;
  color: #cce4ef;
  font-size: 0.78rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.header-content {
  position: relative;
  z-index: 1;
}

.title-kicker {
  margin-bottom: 0.35rem;
  color: var(--cyan);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

.brand-title {
  color: #ffffff;
  font-weight: 820;
}

.brand-accent {
  color: var(--cyan);
  font-weight: 820;
}

.header-copy {
  max-width: 620px;
}

.status-pill, .metric-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.28rem 0.62rem;
  border-radius: 999px;
  background: rgba(34, 199, 214, 0.12);
  color: #d7f9ff;
  border: 1px solid rgba(34, 199, 214, 0.32);
  font-size: 0.76rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
}

.status-pill.completed { color: #dffcf8; border-color: rgba(35, 191, 165, 0.5); }
.status-pill.warning { color: #fff0c7; border-color: rgba(245, 165, 36, 0.55); }
.status-pill.failed { color: #ffe2e7; border-color: rgba(239, 100, 116, 0.55); }

.kpi-card {
  min-height: 150px;
  padding: 1.05rem;
  border-radius: 16px;
  background: var(--card);
  border: 1px solid var(--line);
  box-shadow: 0 12px 30px rgba(8, 22, 33, 0.06);
}

.kpi-label {
  color: var(--muted);
  font-size: 0.75rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.kpi-value {
  margin-top: 0.35rem;
  font-size: clamp(2rem, 4vw, 3rem);
  font-weight: 760;
  letter-spacing: -0.04em;
  color: var(--ink);
}

.kpi-delta {
  margin-top: 0.4rem;
  font-size: 0.92rem;
  font-weight: 650;
}

.delta-good { color: var(--green); }
.delta-bad { color: var(--red); }
.delta-neutral { color: var(--muted); }

.panel {
  padding: 1rem;
  border-radius: 16px;
  background: var(--card);
  border: 1px solid var(--line);
  box-shadow: 0 12px 30px rgba(8, 22, 33, 0.05);
}

.panel-title {
  margin-bottom: 0.75rem;
  color: var(--panel);
  font-size: 0.8rem;
  font-weight: 750;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.evaluation-card {
  padding: 1rem 1.1rem;
  border-radius: 16px;
  background: #ffffff;
  border: 1px solid var(--line);
  box-shadow: 0 12px 30px rgba(8, 22, 33, 0.06);
}

.evaluation-card strong {
  display: block;
  color: var(--panel);
  font-size: 1.1rem;
  letter-spacing: -0.01em;
}

.evaluation-meta {
  margin-top: 0.35rem;
  color: var(--muted);
  font-size: 0.9rem;
}

.baseline-card {
  padding: 0.85rem 1rem;
  border-radius: 14px;
  background: #eef7fa;
  border: 1px solid #cde9ef;
}

.alert-card {
  padding: 0.9rem 1rem;
  border-radius: 14px;
  border: 1px solid rgba(245, 165, 36, 0.45);
  background: #fff7e8;
  color: #6f4a00;
}

.case-question {
  padding: 1rem;
  border-radius: 14px;
  background: #eef7fa;
  border: 1px solid #cde9ef;
}

.case-answer {
  padding: 1rem;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid var(--line);
}

.small-muted {
  color: var(--muted);
  font-size: 0.86rem;
}

div[data-testid="stMetric"] {
  background: var(--card);
  padding: 0.85rem 1rem;
  border-radius: 14px;
  border: 1px solid var(--line);
}

@media (max-width: 760px) {
  .dashboard-header {
    padding: 1rem;
    border-radius: 14px;
  }
  .kpi-card {
    min-height: 118px;
  }
}
</style>
"""


def apply_styles() -> None:
    import streamlit as st

    st.markdown(CSS, unsafe_allow_html=True)
