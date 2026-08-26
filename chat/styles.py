"""Visual system for the chat interface."""

from __future__ import annotations


CSS = """
<style>
:root {
  --bg: #0b0b0b;
  --sidebar: #0b0b0b;
  --sidebar-line: #202020;
  --panel: #151515;
  --panel-hover: #202020;
  --panel-active: #2b2b2b;
  --ink: #f2f2f2;
  --muted: #a8a8a8;
  --subtle: #828282;
  --line: #303030;
  --accent: #d9c7a5;
  --error: #f87171;
}

html,
body,
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stAppViewBlockContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
[data-testid="stSidebarContent"],
[data-testid="stSidebarUserContent"],
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stVerticalBlockBorderWrapper"] > div,
.main,
section.main {
  background: var(--bg) !important;
  color: var(--ink);
}

* {
  scrollbar-color: #3a3a3a #111111;
}

::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

::-webkit-scrollbar-track {
  background: #111111;
}

::-webkit-scrollbar-thumb {
  background: #3a3a3a;
  border-radius: 999px;
}

.stApp > div,
[data-testid="stVerticalBlock"],
[data-testid="stHorizontalBlock"],
[data-testid="stElementContainer"],
[data-testid="column"] {
  background: transparent !important;
}

header[data-testid="stHeader"],
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stDeployButton"],
[data-testid="stMainMenu"],
.stAppToolbar,
.stAppHeader,
#MainMenu,
footer {
  display: none !important;
}

[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"],
[data-testid="stChatFloatingInputContainer"],
[data-testid="stChatInput"] {
  background: var(--bg) !important;
}

[data-testid="stBottom"] {
  border-top: 1px solid #232323;
}

[data-testid="stBottomBlockContainer"] {
  max-width: 980px !important;
  padding: 1rem 1.5rem 1.25rem !important;
}

.stApp, button, input, textarea {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

input,
textarea,
[data-baseweb="input"],
[data-baseweb="textarea"],
[data-baseweb="base-input"],
[data-baseweb="input"] > div,
[data-baseweb="textarea"] > div {
  background: var(--panel) !important;
  color: var(--ink) !important;
  border-color: #2d2d2d !important;
  box-shadow: none !important;
}

input::selection,
textarea::selection {
  background: #2563eb;
  color: #ffffff;
}

.block-container {
  max-width: 980px;
  padding-top: 1rem;
  padding-bottom: 8.5rem;
}

section[data-testid="stSidebar"] {
  width: 320px !important;
  background: var(--sidebar);
  border-right: 1px solid var(--sidebar-line);
}

section[data-testid="stSidebar"] * {
  color: var(--ink);
}

section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stCaptionContainer {
  color: var(--muted);
}

section[data-testid="stSidebar"] .stTextInput input {
  background: var(--panel) !important;
  border: 1px solid #2d2d2d;
  color: var(--ink);
  border-radius: 10px;
  height: 2.35rem;
  box-shadow: none;
}

section[data-testid="stSidebar"] .stTextInput input:focus {
  border-color: #4a4a4a;
  box-shadow: none;
}

section[data-testid="stSidebar"] .stButton button {
  justify-content: flex-start;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--ink);
  box-shadow: none;
  min-height: 2.35rem;
}

section[data-testid="stSidebar"] .stButton button:hover {
  background: var(--panel-hover);
  color: var(--ink);
  border: 0;
}

section[data-testid="stSidebar"] .stButton button[kind="primary"] {
  justify-content: center;
  min-height: 2rem;
  background: #2563eb;
  color: #ffffff;
  border-radius: 8px;
  font-size: 0.78rem;
  font-weight: 650;
  padding: 0.22rem 0.5rem;
}

section[data-testid="stSidebar"] .stButton button[kind="primary"]:hover {
  background: #1d4ed8;
  color: #ffffff;
}

section[data-testid="stSidebar"] div[data-testid="column"]:first-child .stButton button {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

section[data-testid="stSidebar"] .stTextInput [data-baseweb="input"] {
  background: var(--panel) !important;
  border-radius: 10px !important;
  box-shadow: none !important;
}

section[data-testid="stSidebar"] .stTextInput input {
  font-weight: 600;
}

.sidebar-brand {
  padding: 0.25rem 0.15rem 0.9rem;
}

.sidebar-brand h2 {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 1.3rem;
  font-weight: 700;
  letter-spacing: -0.035em;
  color: #ffffff;
}

.sidebar-brand p {
  display: none;
}

.sidebar-section {
  margin: 1rem 0 0.3rem;
  padding-left: 0.2rem;
  color: var(--muted);
  font-size: 0.82rem;
  font-weight: 500;
}

.sidebar-runtime {
  margin-top: 1.2rem;
  padding: 0.7rem 0.25rem 0;
  border-top: 1px solid #202020;
  color: var(--subtle);
  font-size: 0.78rem;
}

.session-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  min-height: 2.15rem;
  margin: 0.04rem 0;
  padding: 0 0.38rem 0 0.5rem;
  border-radius: 9px;
  transition: background 120ms ease, color 120ms ease;
}

.session-main {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  min-width: 0;
  flex: 1;
  color: #cfcfcf !important;
  text-decoration: none !important;
}

.session-row:hover {
  background: var(--panel-hover);
}

.session-row.active {
  background: var(--panel-active);
}

.session-row:hover .session-main,
.session-row.active .session-main {
  color: #ffffff !important;
}

.session-dot {
  width: 4px;
  height: 4px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: #777;
  opacity: 0.75;
}

.session-title {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 0.9rem;
}

.session-edit {
  flex: 0 0 auto;
  width: 1.45rem;
  height: 1.45rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  color: #d7d7d7 !important;
  opacity: 0;
  text-decoration: none !important;
  transition: opacity 120ms ease, background 120ms ease;
}

.session-row:hover .session-edit,
.session-row.active .session-edit {
  opacity: 1;
}

.session-edit:hover {
  background: #444;
}

.chat-topbar {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin: -0.25rem 0 2rem;
  padding: 0.35rem 0 0.65rem;
  background: rgba(11, 11, 11, 0.94);
  border-bottom: 1px solid rgba(58, 58, 58, 0.72);
  backdrop-filter: blur(16px);
}

.chat-title {
  margin: 0;
  max-width: 620px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: #e8e8e8;
  font-size: 0.98rem;
  font-weight: 600;
  letter-spacing: -0.015em;
}

.chat-subtitle {
  margin-top: 0.12rem;
  color: var(--subtle);
  font-size: 0.78rem;
}

.topbar-meta {
  color: var(--muted);
  font-size: 0.82rem;
  white-space: nowrap;
}

.landing-card {
  max-width: 780px;
  margin: 15vh auto 0;
  padding: 0 0.2rem;
}

.landing-card h1 {
  margin: 0;
  color: #eaeaea;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(2.35rem, 6vw, 4.6rem);
  font-weight: 700;
  letter-spacing: -0.06em;
  line-height: 0.98;
}

.landing-card p {
  margin: 1rem 0 0;
  max-width: 640px;
  color: var(--muted);
  font-size: 1.02rem;
  line-height: 1.55;
}

.example-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem;
  margin-top: 1.3rem;
}

.example-card {
  padding: 0.85rem 0.95rem;
  border-radius: 13px;
  background: var(--panel);
  border: 1px solid #2d2d2d;
  color: #cfcfcf;
  font-size: 0.91rem;
  line-height: 1.35;
}

.answer-meta {
  margin: 0.75rem 0 0.25rem;
  color: var(--subtle);
  font-size: 0.78rem;
}

.metric-pill {
  display: inline;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--subtle);
  font-size: 0.78rem;
  font-weight: 400;
}

.source-card {
  padding: 0.72rem 0;
  border-top: 1px solid var(--line);
  background: transparent;
}

.source-card strong {
  color: #e2e2e2;
}

.source-text {
  margin-top: 0.45rem;
  color: #b8b8b8;
  font-size: 0.88rem;
  line-height: 1.52;
}

div[data-testid="stChatMessage"] {
  background: transparent;
  padding: 0.42rem 0 1.15rem;
}

div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
  color: #e5e5e5;
  font-size: 1.02rem;
  line-height: 1.62;
}

div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
  margin-bottom: 0.85rem;
}

div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] strong {
  color: #f3f3f3;
}

div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] code {
  background: #191919;
  border: 1px solid #333;
  color: #e8e8e8;
}

div[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-user"],
div[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-assistant"] {
  background: #202020;
}

.composer-shell {
  max-width: 860px;
  margin: 2.25rem auto 0;
}

div[data-testid="stForm"] {
  max-width: 860px;
  margin: 0 auto;
  padding: 0.72rem 0.78rem 0.62rem !important;
  background: var(--panel) !important;
  border: 1px solid #2a2a2a !important;
  border-radius: 17px !important;
  box-shadow: none !important;
}

div[data-testid="stForm"] [data-testid="stTextArea"],
div[data-testid="stForm"] [data-testid="stTextArea"] > div,
div[data-testid="stForm"] [data-baseweb="textarea"],
div[data-testid="stForm"] [data-baseweb="base-input"],
.stTextArea,
.stTextArea > div,
.stTextArea [data-baseweb="textarea"],
.stTextArea [data-baseweb="base-input"] {
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
}

div[data-testid="stForm"] textarea,
div[data-testid="stForm"] [data-testid="stTextArea"] textarea,
.stTextArea textarea,
textarea[aria-label="Message"] {
  min-height: 118px !important;
  background: var(--panel) !important;
  border: 0 !important;
  outline: 0 !important;
  color: #f1f1f1 !important;
  caret-color: #f1f1f1 !important;
  box-shadow: none !important;
  resize: none !important;
  font-size: 0.98rem !important;
  line-height: 1.45 !important;
  padding: 0.35rem 0.25rem 0.1rem !important;
}

div[data-testid="stForm"] textarea:focus,
div[data-testid="stForm"] [data-testid="stTextArea"] textarea:focus,
.stTextArea textarea:focus,
textarea[aria-label="Message"]:focus {
  background: var(--panel) !important;
  border: 0 !important;
  outline: 0 !important;
  box-shadow: none !important;
}

div[data-testid="stForm"] textarea::placeholder,
.stTextArea textarea::placeholder,
textarea[aria-label="Message"]::placeholder {
  color: #8a8a8a !important;
  opacity: 1 !important;
}

.composer-meta {
  color: #8b8b8b;
  font-size: 0.82rem;
  line-height: 2.1rem;
  white-space: nowrap;
}

div[data-testid="stForm"] button[kind="primary"] {
  justify-content: center;
  min-height: 2rem;
  min-width: 4.4rem;
  margin-left: auto;
  background: #2a2a2a !important;
  border: 1px solid #363636 !important;
  border-radius: 10px !important;
  color: #e7e7e7 !important;
  box-shadow: none !important;
  font-size: 0 !important;
}

div[data-testid="stForm"] button[kind="primary"]::after {
  content: "Send";
  font-size: 0.82rem;
  font-weight: 700;
  line-height: 1;
}

div[data-testid="stForm"] button[kind="primary"]:hover {
  background: #3a3a3a !important;
  border-color: #4a4a4a !important;
}

.stExpander {
  border-color: var(--line) !important;
  background: transparent !important;
}

div[data-testid="stExpander"] {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: transparent;
}

div[data-testid="stExpander"] summary {
  color: #bdbdbd;
  font-size: 0.86rem;
}

div[data-testid="stStatusWidget"] {
  background: #181818;
  border: 1px solid #303030;
  border-radius: 13px;
}

hr {
  border-color: var(--line);
}

@media (max-width: 760px) {
  section[data-testid="stSidebar"] {
    width: auto !important;
  }
  .block-container {
    padding-left: 1rem;
    padding-right: 1rem;
  }
  .chat-topbar {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.2rem;
  }
  .example-grid {
    grid-template-columns: 1fr;
  }
}
</style>
"""
