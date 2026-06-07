import sys
from pathlib import Path

# Ensure project root is on the path regardless of how the app is launched
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

# ------------------------------------------------------------------ #
#  Page config — must be the very first Streamlit call                 #
# ------------------------------------------------------------------ #
st.set_page_config(
    page_title="QA Automation Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "AI-Powered QA Automation Assistant — Feature File & Step Definition Generator",
    },
)

# ------------------------------------------------------------------ #
#  Global CSS                                                          #
# ------------------------------------------------------------------ #
st.markdown(
    """
    <style>
    /* Top bar */
    header[data-testid="stHeader"] { background: #0F172A; }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #0F172A;
        border-right: 1px solid #1E293B;
    }
    section[data-testid="stSidebar"] * { color: #E2E8F0 !important; }
    section[data-testid="stSidebar"] hr { border-color: #1E293B; }

    /* Nav buttons */
    section[data-testid="stSidebar"] button {
        background: transparent !important;
        border: 1px solid #1E293B !important;
        color: #CBD5E1 !important;
        text-align: left !important;
        font-size: 0.9rem !important;
        margin-bottom: 2px !important;
    }
    section[data-testid="stSidebar"] button:hover {
        background: #1E293B !important;
        border-color: #3B82F6 !important;
        color: #F8FAFC !important;
    }

    /* Main area */
    .block-container { padding-top: 1.5rem; }

    /* Metric cards */
    [data-testid="metric-container"] {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 10px 16px;
    }

    /* Hide default Streamlit footer */
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ #
#  Session state defaults                                              #
# ------------------------------------------------------------------ #
_DEFAULTS = {
    "page": "Home",
    "logs": [],
    "generated_feature_file": None,
    "generated_step_definitions": None,
    "generated_page_objects": None,
    "crawl_pages_data": None,
    "crawl_dom_text": "",
    "crawl_summary": "",
    "crawl_base_url": "",
    "project_zip": None,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ------------------------------------------------------------------ #
#  Sidebar                                                             #
# ------------------------------------------------------------------ #
with st.sidebar:
    st.markdown(
        "<div style='font-size:1.3rem;font-weight:700;padding:8px 0 4px'>🤖 QA Assistant</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='font-size:0.75rem;color:#94A3B8;margin-bottom:12px'>"
        "AI-Powered QA Automation</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown(
        "<div style='font-size:0.7rem;color:#64748B;text-transform:uppercase;"
        "letter-spacing:0.05em;padding:4px 0'>From Documents</div>",
        unsafe_allow_html=True,
    )

    NAV_DOC = {
        "🏠  Home": "Home",
        "📄  Generate Feature File": "Generate Feature File",
    }
    for label, page_id in NAV_DOC.items():
        if st.button(label, key=f"nav_{page_id}", use_container_width=True):
            st.session_state.page = page_id
            st.rerun()

    st.markdown(
        "<div style='font-size:0.7rem;color:#64748B;text-transform:uppercase;"
        "letter-spacing:0.05em;padding:8px 0 4px'>From Web Application</div>",
        unsafe_allow_html=True,
    )

    NAV_WEB = {
        "🌐  Crawl Web App": "Crawl Web App",
    }
    for label, page_id in NAV_WEB.items():
        if st.button(label, key=f"nav_{page_id}", use_container_width=True):
            st.session_state.page = page_id
            st.rerun()

    st.markdown(
        "<div style='font-size:0.7rem;color:#64748B;text-transform:uppercase;"
        "letter-spacing:0.05em;padding:8px 0 4px'>Generate Artefacts</div>",
        unsafe_allow_html=True,
    )

    NAV_ARTEFACTS = {
        "⚙️  Step Definitions": "Generate Step Definitions",
        "📦  Page Objects": "Generate Page Objects",
        "🚀  Run Tests": "Run Tests",
    }
    for label, page_id in NAV_ARTEFACTS.items():
        if st.button(label, key=f"nav_{page_id}", use_container_width=True):
            st.session_state.page = page_id
            st.rerun()

    st.markdown(
        "<div style='font-size:0.7rem;color:#64748B;text-transform:uppercase;"
        "letter-spacing:0.05em;padding:8px 0 4px'>System</div>",
        unsafe_allow_html=True,
    )

    NAV_SYS = {
        "📋  Execution Logs": "Execution Logs",
        "🔧  Settings": "Settings",
    }
    for label, page_id in NAV_SYS.items():
        if st.button(label, key=f"nav_{page_id}", use_container_width=True):
            st.session_state.page = page_id
            st.rerun()

    st.divider()

    # Session state indicators
    has_crawl = bool(st.session_state.get("crawl_pages_data"))
    has_feature = bool(st.session_state.get("generated_feature_file"))
    has_steps = bool(st.session_state.get("generated_step_definitions"))
    has_pom = bool(st.session_state.get("generated_page_objects"))

    st.markdown(
        f"<div style='font-size:0.75rem;color:#94A3B8'>"
        f"{'✓' if has_crawl else '○'} DOM crawled &nbsp;"
        f"{'✓' if has_feature else '○'} Feature file &nbsp;"
        f"{'✓' if has_steps else '○'} Steps &nbsp;"
        f"{'✓' if has_pom else '○'} POM"
        f"</div>",
        unsafe_allow_html=True,
    )

    from config.settings import Settings as _Cfg
    _cfg = _Cfg()
    _status = "Azure OpenAI ✓" if _cfg.is_configured() else "Azure OpenAI — not configured"
    if _cfg.is_configured():
        st.success(_status)
    else:
        st.warning(_status)

    st.markdown(
        "<div style='font-size:0.72rem;color:#64748B;margin-top:4px'>"
        "v2.0.0 · GPT-4.1 · ChromaDB · Playwright</div>",
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------ #
#  Page router                                                         #
# ------------------------------------------------------------------ #
_page = st.session_state.get("page", "Home")

if _page == "Home":
    from pages.home import render_home
    render_home()

elif _page == "Generate Feature File":
    from pages.generate_feature_file import render_generate_feature_file
    render_generate_feature_file()

elif _page == "Crawl Web App":
    from pages.url_crawler_page import render_url_crawler_page
    render_url_crawler_page()

elif _page == "Generate Step Definitions":
    from pages.generate_step_definitions import render_generate_step_definitions
    render_generate_step_definitions()

elif _page == "Generate Page Objects":
    from pages.generate_page_objects_page import render_generate_page_objects_page
    render_generate_page_objects_page()

elif _page == "Run Tests":
    from pages.test_runner_page import render_test_runner_page
    render_test_runner_page()

elif _page == "Execution Logs":
    from pages.execution_logs import render_execution_logs
    render_execution_logs()

elif _page == "Settings":
    from pages.settings_page import render_settings
    render_settings()
