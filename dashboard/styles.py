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

div[data-testid="stSegmentedControl"] {
  margin: 0.85rem 0 1rem;
  padding: 0.35rem;
  border-radius: 16px;
  background: #e9f0f4;
  border: 1px solid var(--line);
}

div[data-testid="stSegmentedControl"] label {
  border-radius: 12px !important;
  font-weight: 750 !important;
  letter-spacing: 0.02em;
}

div[data-testid="stSegmentedControl"] label[aria-checked="true"] {
  background: #ffffff !important;
  color: var(--panel) !important;
  box-shadow: 0 8px 20px rgba(8, 22, 33, 0.10);
}

div[data-testid="stPopover"] {
  width: 100%;
}

div[data-testid="stPopover"] button {
  width: 100% !important;
  min-height: 4.6rem !important;
  padding: 0.85rem 1rem !important;
  border: 1px solid var(--line) !important;
  border-radius: 16px !important;
  background: var(--card) !important;
  color: var(--ink) !important;
  text-align: center !important;
  box-shadow: 0 12px 30px rgba(8, 22, 33, 0.06) !important;
  white-space: normal !important;
}

div[data-testid="stPopover"] button:hover {
  border-color: var(--cyan) !important;
  background: #fbfeff !important;
}

div[data-testid="stPopover"] button svg {
  display: none !important;
}

.comparison-value-card,
.comparison-delta-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  min-height: 118px;
  padding: 0.85rem 1rem;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--card);
  box-shadow: 0 8px 22px rgba(8, 22, 33, 0.05);
}

.comparison-a-card {
  border-color: #b9e9ee;
  background: #fbfeff;
}

.comparison-b-card {
  border-color: #f1d7a5;
  background: #fffdfa;
}

.comparison-delta-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  background: #f8fafb;
}

.comparison-role {
  color: var(--muted);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.comparison-column-header {
  min-height: 4.2rem;
  padding: 0.65rem 1rem;
  border-bottom: 2px solid var(--line);
  color: var(--muted);
  text-align: center;
}

.comparison-column-header span,
.comparison-column-header strong,
.comparison-column-header small {
  display: block;
}

.comparison-column-header span {
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.comparison-column-header strong {
  margin-top: 0.18rem;
  color: var(--panel);
  font-size: 0.95rem;
}

.comparison-column-header small {
  margin-top: 0.16rem;
  color: var(--muted);
  font-size: 0.72rem;
}

.comparison-column-difference {
  display: flex !important;
  align-items: center;
  justify-content: center;
  color: var(--panel);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.comparison-label {
  margin-top: 0.4rem;
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 700;
}

.comparison-value {
  margin-top: 0.28rem;
  color: var(--ink);
  font-size: 1.8rem;
  font-weight: 780;
  letter-spacing: -0.04em;
}

.comparison-delta {
  margin-top: 0.28rem;
  font-size: 1.15rem;
  font-weight: 780;
}

.comparison-winner {
  margin-top: 0.3rem;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.comparison-a-wins {
  border-color: rgba(35, 191, 165, 0.5);
  background: #effbf8;
  color: #087c6d;
}

.comparison-b-wins {
  border-color: rgba(239, 100, 116, 0.45);
  background: #fff4f5;
  color: #b13c4c;
}

.comparison-tie {
  color: var(--muted);
}

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
  overflow: visible;
}

.kpi-label-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.55rem;
}

.info-icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 0.95rem;
  height: 0.95rem;
  margin-left: 0.22rem;
  border-radius: 999px;
  border: 1px solid #8edbe3;
  color: #22a9b7;
  background: transparent;
  font-size: 0.62rem;
  font-weight: 800;
  cursor: help;
  text-transform: none;
  letter-spacing: 0;
  vertical-align: text-top;
}

.info-icon:hover::after {
  content: attr(data-tooltip);
  position: absolute;
  left: 50%;
  bottom: calc(100% + 0.5rem);
  transform: translateX(-50%);
  z-index: 1000;
  width: max-content;
  max-width: 300px;
  padding: 0.55rem 0.65rem;
  border-radius: 8px;
  background: #f3f6f8;
  color: var(--ink);
  border: 1px solid #dfe7ed;
  box-shadow: 0 8px 22px rgba(8, 22, 33, 0.13);
  font-size: 0.72rem;
  font-weight: 500;
  letter-spacing: 0;
  line-height: 1.35;
  text-transform: none;
  white-space: normal;
  text-align: left;
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

.delete-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.8rem 1rem;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #ffffff;
}

.delete-summary strong {
  color: var(--panel);
}

.delete-summary span {
  color: var(--muted);
  font-size: 0.86rem;
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
  .delete-summary {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.25rem;
  }
}
</style>
"""


def apply_styles() -> None:
    import streamlit as st

    st.markdown(CSS, unsafe_allow_html=True)
