"""
Test Runner page.

Packages all generated artefacts (feature file + step definitions + page objects)
into a complete, runnable automation project ZIP with one-click run.bat / run.sh.
"""

import streamlit as st
from config.settings import Settings
from services.test_project_generator import generate_project_zip
from utils.helpers import sanitize_filename, count_scenarios
from utils.logger import AppLogger

logger = AppLogger.get_logger("page.test_runner")


def render_test_runner_page():
    st.markdown("## 🚀 Run Automation Tests")
    st.caption(
        "Package all generated artefacts into a complete, runnable automation project. "
        "Download the ZIP, extract it, and double-click **run.bat** — the browser "
        "opens and all tests execute automatically."
    )

    # ------------------------------------------------------------------ #
    #  Status of collected artefacts                                       #
    # ------------------------------------------------------------------ #
    feature = st.session_state.get("generated_feature_file", "")
    step_defs = st.session_state.get("generated_step_definitions", "")
    page_objects = st.session_state.get("generated_page_objects", {})
    base_url = st.session_state.get("crawl_base_url", "https://example.com")

    st.markdown("### 📋 Artefact Status")
    a1, a2, a3 = st.columns(3)
    with a1:
        if feature:
            st.success(f"✓ Feature File ({count_scenarios(feature)} scenarios)")
        else:
            st.error("✗ Feature File — not yet generated")
    with a2:
        if step_defs:
            st.success(f"✓ Step Definitions ({len(step_defs):,} chars)")
        else:
            st.warning("⚠ Step Definitions — not yet generated")
    with a3:
        if page_objects:
            st.success(f"✓ Page Objects ({len(page_objects)} file(s))")
        else:
            st.warning("⚠ Page Objects — not yet generated (optional)")

    if not feature:
        st.info(
            "Generate a feature file first (via **Generate Feature File** or "
            "**Generate from Web App**), then come back here."
        )

    st.markdown("---")

    # ------------------------------------------------------------------ #
    #  Project settings                                                    #
    # ------------------------------------------------------------------ #
    st.markdown("### ⚙️ Project Configuration")
    cfg1, cfg2 = st.columns(2)
    with cfg1:
        project_name = st.text_input("Project Name", value="QAAutomationProject")
        language = st.selectbox(
            "Framework",
            options=["Java Selenium Cucumber", "Python Behave", "C# SpecFlow"],
        )
        browser = st.selectbox("Browser", ["chrome", "firefox", "edge"])
    with cfg2:
        app_url = st.text_input(
            "Application Base URL",
            value=base_url,
            help="Embedded in BaseSetup / environment.py / Hooks.cs",
        )
        feature_filename = st.text_input(
            "Feature file name",
            value=st.session_state.get("feature_file_name", "generated.feature"),
        )

    # ------------------------------------------------------------------ #
    #  Upload missing artefacts                                            #
    # ------------------------------------------------------------------ #
    with st.expander("📎 Upload missing artefacts manually"):
        up1, up2, up3 = st.columns(3)
        with up1:
            f_up = st.file_uploader("Feature file", type=["feature", "txt"], key="pack_feature")
            if f_up:
                feature = f_up.read().decode("utf-8", errors="replace")
        with up2:
            s_up = st.file_uploader("Step definitions", type=["java", "py", "cs", "txt"], key="pack_steps")
            if s_up:
                step_defs = s_up.read().decode("utf-8", errors="replace")
        with up3:
            p_up = st.file_uploader("Page object(s)", type=["java", "py", "cs", "txt"],
                                     accept_multiple_files=True, key="pack_pom")
            if p_up:
                for pf in p_up:
                    page_objects[pf.name] = pf.read().decode("utf-8", errors="replace")

    # ------------------------------------------------------------------ #
    #  Generate ZIP                                                        #
    # ------------------------------------------------------------------ #
    if st.button(
        "📦 Generate Runnable Test Project (ZIP)",
        type="primary",
        use_container_width=True,
        disabled=not feature,
    ):
        with st.spinner("Packaging project…"):
            try:
                zip_bytes = generate_project_zip(
                    feature_content=feature or "",
                    step_definitions=step_defs or _placeholder_steps(language),
                    page_objects=page_objects or {},
                    language=language,
                    project_name=sanitize_filename(project_name) or "QAProject",
                    base_url=app_url,
                    browser=browser,
                    feature_filename=feature_filename or "generated.feature",
                )
                st.session_state["project_zip"] = zip_bytes
                st.session_state["project_zip_name"] = sanitize_filename(project_name) + ".zip"
                st.session_state["project_language"] = language
                logger.info(f"Test project ZIP created: {len(zip_bytes):,} bytes")
                st.success(f"✅ Project packaged ({len(zip_bytes):,} bytes)")
            except Exception as exc:
                logger.error(f"ZIP generation failed: {exc}", exc_info=True)
                st.error(f"❌ Failed: {exc}")

    # ------------------------------------------------------------------ #
    #  Download + instructions                                             #
    # ------------------------------------------------------------------ #
    if st.session_state.get("project_zip"):
        _render_download_and_instructions()


def _render_download_and_instructions():
    zip_bytes = st.session_state["project_zip"]
    zip_name = st.session_state.get("project_zip_name", "QAProject.zip")
    language = st.session_state.get("project_language", "Java Selenium Cucumber")

    st.markdown("---")
    st.markdown("### ⬇️ Download & Run")

    dl_col, _ = st.columns([3, 7])
    with dl_col:
        st.download_button(
            label=f"⬇️ Download {zip_name}",
            data=zip_bytes,
            file_name=zip_name,
            mime="application/zip",
            use_container_width=True,
            type="primary",
        )

    st.markdown("---")
    if language == "Java Selenium Cucumber":
        _java_instructions()
    elif language == "Python Behave":
        _python_instructions()
    elif language == "C# SpecFlow":
        _csharp_instructions()


def _java_instructions():
    st.markdown("### 🚀 Run Instructions — Java Maven Cucumber")
    st.markdown("""
**Prerequisites** (one-time setup):
1. Install [Java 11+](https://adoptium.net)
2. Install [Maven 3.8+](https://maven.apache.org/download.cgi)
3. Install Google Chrome (latest)

**Run all tests (Windows):**
```
1. Extract the ZIP
2. Double-click  run.bat
3. Browser opens, tests run, HTML report opens automatically
```

**Run all tests (macOS / Linux):**
```bash
chmod +x run.sh
./run.sh
```

**Manual Maven commands:**
```bash
mvn clean test                                  # all tests
mvn test -Dcucumber.filter.tags="@smoke"        # smoke only
mvn test -Dcucumber.filter.tags="@regression"   # regression
mvn test -Dcucumber.filter.tags="@negative"     # negative tests
```

**Reports:**
`target/cucumber-reports/report.html`  — full HTML report
`target/cucumber.json`  — JSON for CI integration
`logs/automation.log`  — execution log
    """)


def _python_instructions():
    st.markdown("### 🚀 Run Instructions — Python Behave")
    st.markdown("""
**Prerequisites** (one-time setup):
1. Install [Python 3.9+](https://python.org)
2. Install Google Chrome (latest)

**Run all tests (Windows):**
```
1. Extract the ZIP
2. Double-click  run.bat   (installs deps + runs tests automatically)
```

**Run all tests (macOS / Linux):**
```bash
chmod +x run.sh
./run.sh
```

**Manual commands:**
```bash
pip install -r requirements.txt
behave                          # all tests
behave --tags=@smoke            # smoke
behave --tags=@regression       # regression
behave --tags=@negative         # negative
behave --no-capture             # verbose output
```

**Reports:**
`reports/behave_report.txt`
`reports/screenshots/`  — screenshots on failure
    """)


def _csharp_instructions():
    st.markdown("### 🚀 Run Instructions — C# SpecFlow")
    st.markdown("""
**Prerequisites** (one-time setup):
1. Install [.NET 8 SDK](https://dotnet.microsoft.com/download)
2. Install Google Chrome (latest)

**Run all tests (Windows):**
```
1. Extract the ZIP
2. Double-click  run.bat
3. Browser opens, tests run, HTML report opens automatically
```

**Run all tests (macOS / Linux):**
```bash
chmod +x run.sh
./run.sh
```

**Manual commands:**
```bash
dotnet restore
dotnet build
dotnet test                                        # all tests
dotnet test --filter Category=smoke                # smoke
dotnet test --filter Category=regression           # regression
```

**Reports:**
`reports/TestResults.html`
    """)


def _placeholder_steps(language: str) -> str:
    if language == "Java Selenium Cucumber":
        return """package com.qa.stepdefinitions;
import io.cucumber.java.en.*;
public class Steps {
    // TODO: Add step definitions
}"""
    elif language == "Python Behave":
        return """from behave import given, when, then
# TODO: Add step definitions
"""
    else:
        return """using TechTalk.SpecFlow;
[Binding]
public class Steps {
    // TODO: Add step definitions
}"""
