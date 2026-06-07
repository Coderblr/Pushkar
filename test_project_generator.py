"""
Generates a complete, runnable automation project as a ZIP archive.

Java  → Maven + Cucumber + Selenium + WebDriverManager + TestNG
Python → pytest-bdd (or Behave) + Selenium
C#    → .NET + SpecFlow + Selenium

Each project includes a one-click run.bat (Windows) and run.sh (Unix).
"""

import io
import zipfile
from typing import Dict, List, Optional
from services.web_crawler import PageInfo
from utils.logger import AppLogger

logger = AppLogger.get_logger("test_project_generator")

# ------------------------------------------------------------------ #
#  Public entry point                                                  #
# ------------------------------------------------------------------ #

def generate_project_zip(
    feature_content: str,
    step_definitions: str,
    page_objects: Dict[str, str],          # filename → code
    language: str = "Java Selenium Cucumber",
    project_name: str = "QAAutomationProject",
    base_url: str = "https://example.com",
    browser: str = "chrome",
    feature_filename: str = "generated.feature",
) -> bytes:
    """Return bytes of a ZIP file containing the full test project."""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if language == "Java Selenium Cucumber":
            _build_java(zf, feature_content, step_definitions, page_objects,
                        project_name, base_url, browser, feature_filename)
        elif language == "Python Behave":
            _build_python(zf, feature_content, step_definitions, page_objects,
                          project_name, base_url, browser, feature_filename)
        elif language == "C# SpecFlow":
            _build_csharp(zf, feature_content, step_definitions, page_objects,
                          project_name, base_url, browser, feature_filename)

    logger.info(f"Test project ZIP generated for {language}: {len(buf.getvalue()):,} bytes")
    return buf.getvalue()


# ================================================================== #
#  JAVA MAVEN                                                          #
# ================================================================== #

def _build_java(zf, feature_content, step_defs, page_objects,
                project_name, base_url, browser, feature_filename):
    pkg = "com/qa"
    feature_name = feature_filename.replace(".feature", "")
    step_class = _to_pascal(feature_name) + "Steps"
    runner_class = "TestRunner"

    _add(zf, f"{project_name}/pom.xml", _java_pom(project_name))
    _add(zf, f"{project_name}/src/test/resources/features/{feature_filename}", feature_content)
    _add(zf, f"{project_name}/src/test/resources/cucumber.properties",
         _java_cucumber_properties(pkg))
    _add(zf, f"{project_name}/src/test/resources/log4j2.xml", _log4j2_xml())
    _add(zf, f"{project_name}/src/test/java/{pkg}/runners/{runner_class}.java",
         _java_runner(pkg, feature_name))
    _add(zf, f"{project_name}/src/test/java/{pkg}/base/BaseSetup.java",
         _java_base_setup(pkg, base_url, browser))
    _add(zf, f"{project_name}/src/test/java/{pkg}/stepdefinitions/{step_class}.java",
         step_defs)
    for fname, code in page_objects.items():
        _add(zf, f"{project_name}/src/test/java/{pkg}/pages/{fname}", code)
    _add(zf, f"{project_name}/run.bat", _java_bat(project_name))
    _add(zf, f"{project_name}/run.sh", _java_sh(project_name))
    _add(zf, f"{project_name}/README.txt", _java_readme(project_name, base_url))


def _java_pom(project_name: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.qa</groupId>
  <artifactId>{project_name.lower().replace(' ', '-')}</artifactId>
  <version>1.0.0</version>
  <packaging>jar</packaging>
  <name>{project_name}</name>

  <properties>
    <maven.compiler.source>11</maven.compiler.source>
    <maven.compiler.target>11</maven.compiler.target>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <selenium.version>4.21.0</selenium.version>
    <cucumber.version>7.18.0</cucumber.version>
    <testng.version>7.10.2</testng.version>
    <wdm.version>5.9.1</wdm.version>
  </properties>

  <dependencies>
    <!-- Selenium -->
    <dependency>
      <groupId>org.seleniumhq.selenium</groupId>
      <artifactId>selenium-java</artifactId>
      <version>${{selenium.version}}</version>
    </dependency>

    <!-- WebDriverManager (automatic driver download) -->
    <dependency>
      <groupId>io.github.bonigarcia</groupId>
      <artifactId>webdrivermanager</artifactId>
      <version>${{wdm.version}}</version>
    </dependency>

    <!-- Cucumber -->
    <dependency>
      <groupId>io.cucumber</groupId>
      <artifactId>cucumber-java</artifactId>
      <version>${{cucumber.version}}</version>
    </dependency>
    <dependency>
      <groupId>io.cucumber</groupId>
      <artifactId>cucumber-testng</artifactId>
      <version>${{cucumber.version}}</version>
    </dependency>

    <!-- TestNG -->
    <dependency>
      <groupId>org.testng</groupId>
      <artifactId>testng</artifactId>
      <version>${{testng.version}}</version>
    </dependency>

    <!-- Logging -->
    <dependency>
      <groupId>org.apache.logging.log4j</groupId>
      <artifactId>log4j-core</artifactId>
      <version>2.23.1</version>
    </dependency>
    <dependency>
      <groupId>org.apache.logging.log4j</groupId>
      <artifactId>log4j-api</artifactId>
      <version>2.23.1</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
        <configuration>
          <suiteXmlFiles>
            <suiteXmlFile>testng.xml</suiteXmlFile>
          </suiteXmlFiles>
        </configuration>
      </plugin>
      <plugin>
        <groupId>net.masterthought</groupId>
        <artifactId>maven-cucumber-reporting</artifactId>
        <version>5.8.0</version>
        <executions>
          <execution>
            <id>execution</id>
            <phase>verify</phase>
            <goals><goal>generate</goal></goals>
            <configuration>
              <projectName>{project_name}</projectName>
              <outputDirectory>${{project.build.directory}}/cucumber-html-reports</outputDirectory>
              <jsonFiles>
                <param>${{project.build.directory}}/cucumber.json</param>
              </jsonFiles>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
"""


def _java_runner(pkg: str, feature_name: str) -> str:
    return f"""package {pkg.replace('/', '.')}.runners;

import io.cucumber.testng.AbstractTestNGCucumberTests;
import io.cucumber.testng.CucumberOptions;
import org.testng.annotations.DataProvider;

@CucumberOptions(
    features = "src/test/resources/features",
    glue = {{"{pkg.replace('/', '.')}.stepdefinitions", "{pkg.replace('/', '.')}.hooks"}},
    plugin = {{
        "pretty",
        "html:target/cucumber-reports/report.html",
        "json:target/cucumber.json",
        "junit:target/cucumber-reports/report.xml"
    }},
    monochrome = true,
    tags = "not @skip"
)
public class TestRunner extends AbstractTestNGCucumberTests {{

    @Override
    @DataProvider(parallel = false)
    public Object[][] scenarios() {{
        return super.scenarios();
    }}
}}
"""


def _java_base_setup(pkg: str, base_url: str, browser: str) -> str:
    pkg_java = pkg.replace("/", ".")
    return f"""package {pkg_java}.base;

import io.github.bonigarcia.wdm.WebDriverManager;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.openqa.selenium.firefox.FirefoxDriver;
import org.openqa.selenium.edge.EdgeDriver;

import java.time.Duration;

public class BaseSetup {{

    private static final ThreadLocal<WebDriver> DRIVER = new ThreadLocal<>();
    public static final String BASE_URL = "{base_url}";
    public static final int DEFAULT_WAIT = 10;

    public static WebDriver getDriver() {{
        return DRIVER.get();
    }}

    public static void initDriver(String browser) {{
        WebDriver driver;
        switch (browser.toLowerCase()) {{
            case "firefox":
                WebDriverManager.firefoxdriver().setup();
                driver = new FirefoxDriver();
                break;
            case "edge":
                WebDriverManager.edgedriver().setup();
                driver = new EdgeDriver();
                break;
            default:
                WebDriverManager.chromedriver().setup();
                ChromeOptions opts = new ChromeOptions();
                // opts.addArguments("--headless");  // uncomment for CI
                opts.addArguments("--start-maximized");
                opts.addArguments("--disable-notifications");
                driver = new ChromeDriver(opts);
        }}
        driver.manage().timeouts().implicitlyWait(Duration.ofSeconds(0));
        driver.manage().timeouts().pageLoadTimeout(Duration.ofSeconds(30));
        driver.manage().window().maximize();
        DRIVER.set(driver);
    }}

    public static void tearDownDriver() {{
        WebDriver driver = DRIVER.get();
        if (driver != null) {{
            driver.quit();
            DRIVER.remove();
        }}
    }}
}}
"""


def _java_cucumber_properties(pkg: str) -> str:
    return f"cucumber.publish.quiet=true\n"


def _log4j2_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <Console name="Console" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{HH:mm:ss} [%t] %-5level %logger{36} - %msg%n"/>
    </Console>
    <File name="File" fileName="logs/automation.log" append="false">
      <PatternLayout pattern="%d{yyyy-MM-dd HH:mm:ss} [%t] %-5level - %msg%n"/>
    </File>
  </Appenders>
  <Loggers>
    <Root level="INFO">
      <AppenderRef ref="Console"/>
      <AppenderRef ref="File"/>
    </Root>
  </Loggers>
</Configuration>
"""


def _java_bat(project_name: str) -> str:
    return f"""@echo off
title {project_name} — Selenium Automation Suite
echo ============================================================
echo  {project_name}  -  Automated Test Execution
echo ============================================================
echo.

where mvn >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Maven (mvn) not found. Please install Maven and add to PATH.
    echo         Download: https://maven.apache.org/download.cgi
    pause
    exit /b 1
)

where java >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Java not found. Please install JDK 11+ and add to PATH.
    echo         Download: https://adoptium.net
    pause
    exit /b 1
)

echo [INFO] Java version:
java -version
echo.
echo [INFO] Maven version:
mvn -version
echo.
echo [INFO] Starting test execution...
echo.

mvn clean test -Dcucumber.filter.tags="not @skip"

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] All tests completed.
    echo [INFO]    HTML Report: target\\cucumber-reports\\report.html
    start "" "target\\cucumber-reports\\report.html"
) else (
    echo.
    echo [FAILURE] Some tests failed. Check report at:
    echo           target\\cucumber-reports\\report.html
    start "" "target\\cucumber-reports\\report.html"
)

pause
"""


def _java_sh(project_name: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

echo "============================================================"
echo " {project_name} — Automated Test Execution"
echo "============================================================"

command -v mvn  >/dev/null 2>&1 || {{ echo "[ERROR] Maven not found."; exit 1; }}
command -v java >/dev/null 2>&1 || {{ echo "[ERROR] Java not found."; exit 1; }}

echo "[INFO] Starting tests..."
mvn clean test -Dcucumber.filter.tags="not @skip"

echo ""
echo "[INFO] Report: target/cucumber-reports/report.html"
"""


def _java_readme(project_name: str, base_url: str) -> str:
    return f"""=== {project_name} — Selenium Cucumber TestNG Automation ===

TARGET APPLICATION: {base_url}

PREREQUISITES
-------------
• Java 11 or higher  (https://adoptium.net)
• Apache Maven 3.8+  (https://maven.apache.org/download.cgi)
• Google Chrome (latest)

QUICK START — WINDOWS
---------------------
1. Extract this ZIP to any folder
2. Double-click run.bat
3. The browser opens, tests execute, HTML report opens automatically.

QUICK START — LINUX / macOS
----------------------------
1. chmod +x run.sh
2. ./run.sh
3. Open target/cucumber-reports/report.html

MANUAL EXECUTION
----------------
mvn clean test                              # run all tests
mvn test -Dcucumber.filter.tags="@smoke"   # run smoke tests only
mvn test -Dcucumber.filter.tags="@regression"

REPORTS
-------
HTML report : target/cucumber-reports/report.html
JSON report : target/cucumber.json
Log file    : logs/automation.log

PROJECT STRUCTURE
-----------------
src/test/resources/features/    Feature files
src/test/java/com/qa/
  runners/                       Cucumber runner (TestNG)
  stepdefinitions/               Step definitions
  pages/                         Page Object Model classes
  base/                          WebDriver setup
"""


# ================================================================== #
#  PYTHON BEHAVE                                                       #
# ================================================================== #

def _build_python(zf, feature_content, step_defs, page_objects,
                  project_name, base_url, browser, feature_filename):
    _add(zf, f"{project_name}/features/{feature_filename}", feature_content)
    _add(zf, f"{project_name}/features/steps/steps.py", step_defs)
    _add(zf, f"{project_name}/environment.py", _python_environment(base_url, browser))
    _add(zf, f"{project_name}/behave.ini", _behave_ini())
    _add(zf, f"{project_name}/requirements.txt", _python_requirements())
    for fname, code in page_objects.items():
        _add(zf, f"{project_name}/pages/{fname}", code)
    _add(zf, f"{project_name}/run.bat", _python_bat(project_name))
    _add(zf, f"{project_name}/run.sh", _python_sh(project_name))
    _add(zf, f"{project_name}/README.txt", _python_readme(project_name, base_url))


def _python_environment(base_url: str, browser: str) -> str:
    return f"""from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import os


BASE_URL = "{base_url}"
BROWSER = os.getenv("BROWSER", "{browser}").lower()


def before_all(context):
    context.base_url = BASE_URL


def before_scenario(context, scenario):
    opts = Options()
    # opts.add_argument("--headless")  # uncomment for CI
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-notifications")
    context.driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()),
        options=opts
    )
    context.driver.implicitly_wait(0)


def after_scenario(context, scenario):
    if scenario.status == "failed":
        context.driver.save_screenshot(f"reports/screenshots/{{scenario.name}}.png")
    context.driver.quit()


def after_all(context):
    pass
"""


def _behave_ini() -> str:
    return """[behave]
stdout_capture = false
stderr_capture = false
log_capture = false
format = pretty
outfile = reports/behave_report.txt
"""


def _python_requirements() -> str:
    return """selenium>=4.21.0
behave>=1.2.6
webdriver-manager>=4.0.1
Pillow>=10.3.0
allure-behave>=2.13.5
"""


def _python_bat(project_name: str) -> str:
    return f"""@echo off
title {project_name} — Behave Automation Suite
echo ============================================================
echo  {project_name}  -  Automated Test Execution  (Python Behave)
echo ============================================================

where python >nul 2>&1 || where python3 >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found. Install Python 3.9+ from https://python.org
    pause & exit /b 1
)

echo [INFO] Installing dependencies...
pip install -r requirements.txt --quiet

if not exist reports mkdir reports
if not exist reports\\screenshots mkdir reports\\screenshots

echo [INFO] Running tests...
behave --no-capture

if %ERRORLEVEL% equ 0 (
    echo [SUCCESS] All tests passed.
) else (
    echo [FAILURE] Some tests failed. Check reports folder.
)
pause
"""


def _python_sh(project_name: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail
echo "=== {project_name} — Behave Automation ==="
pip install -r requirements.txt -q
mkdir -p reports/screenshots
behave --no-capture
echo "Done. Check reports/ folder."
"""


def _python_readme(project_name: str, base_url: str) -> str:
    return f"""=== {project_name} — Python Behave Selenium Automation ===

TARGET: {base_url}

PREREQUISITES
-------------
Python 3.9+  (https://python.org)
Google Chrome (latest)

QUICK START
-----------
Windows:  Double-click run.bat
Linux/Mac: chmod +x run.sh && ./run.sh

MANUAL
------
pip install -r requirements.txt
behave                                # all tests
behave --tags=@smoke                  # smoke only
behave --tags=@regression             # regression only

STRUCTURE
---------
features/          Feature files
features/steps/    Step definitions
pages/             Page Object classes
environment.py     Behave hooks (driver setup/teardown)
reports/           Screenshots on failure
"""


# ================================================================== #
#  C# SPECFLOW                                                         #
# ================================================================== #

def _build_csharp(zf, feature_content, step_defs, page_objects,
                  project_name, base_url, browser, feature_filename):
    safe = project_name.replace(" ", "")
    _add(zf, f"{project_name}/{safe}.csproj", _csharp_csproj(safe))
    _add(zf, f"{project_name}/Features/{feature_filename}", feature_content)
    _add(zf, f"{project_name}/StepDefinitions/Steps.cs", step_defs)
    _add(zf, f"{project_name}/Hooks/Hooks.cs", _csharp_hooks(safe, base_url, browser))
    _add(zf, f"{project_name}/appsettings.json", f'{{"BaseUrl": "{base_url}", "Browser": "{browser}"}}')
    for fname, code in page_objects.items():
        _add(zf, f"{project_name}/PageObjects/{fname}", code)
    _add(zf, f"{project_name}/run.bat", _csharp_bat(project_name, safe))
    _add(zf, f"{project_name}/run.sh", _csharp_sh(project_name, safe))
    _add(zf, f"{project_name}/README.txt", _csharp_readme(project_name, base_url))


def _csharp_csproj(safe: str) -> str:
    return f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <IsPackable>false</IsPackable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Selenium.WebDriver" Version="4.21.0" />
    <PackageReference Include="Selenium.Support" Version="4.21.0" />
    <PackageReference Include="WebDriverManager" Version="2.17.4" />
    <PackageReference Include="SpecFlow.NUnit" Version="3.9.74" />
    <PackageReference Include="SpecFlow.Plus.LivingDocPlugin" Version="3.9.57" />
    <PackageReference Include="NUnit" Version="4.1.0" />
    <PackageReference Include="NUnit3TestAdapter" Version="4.5.0" />
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.9.0" />
  </ItemGroup>
  <ItemGroup>
    <None Update="appsettings.json">
      <CopyToOutputDirectory>Always</CopyToOutputDirectory>
    </None>
  </ItemGroup>
</Project>
"""


def _csharp_hooks(safe: str, base_url: str, browser: str) -> str:
    return f"""using BoDi;
using OpenQA.Selenium;
using OpenQA.Selenium.Chrome;
using OpenQA.Selenium.Firefox;
using WebDriverManager;
using WebDriverManager.DriverConfigs.Impl;
using TechTalk.SpecFlow;

namespace {safe}.Hooks
{{
    [Binding]
    public class Hooks
    {{
        private readonly IObjectContainer _container;
        public static readonly string BaseUrl = "{base_url}";

        public Hooks(IObjectContainer container) => _container = container;

        [BeforeScenario]
        public void BeforeScenario()
        {{
            string browser = System.Environment.GetEnvironmentVariable("BROWSER") ?? "{browser}";
            IWebDriver driver = browser.ToLower() switch
            {{
                "firefox" => new FirefoxDriver(),
                _ => CreateChromeDriver()
            }};
            driver.Manage().Timeouts().PageLoad = TimeSpan.FromSeconds(30);
            driver.Manage().Window.Maximize();
            _container.RegisterInstanceAs(driver);
        }}

        [AfterScenario]
        public void AfterScenario(IWebDriver driver, ScenarioContext scenarioContext)
        {{
            if (scenarioContext.TestError != null)
            {{
                var screenshot = ((ITakesScreenshot)driver).GetScreenshot();
                screenshot.SaveAsFile($"reports/{{scenarioContext.ScenarioInfo.Title}}.png");
            }}
            driver.Quit();
        }}

        private static IWebDriver CreateChromeDriver()
        {{
            new DriverManager().SetUpDriver(new ChromeConfig());
            var opts = new ChromeOptions();
            // opts.AddArgument("--headless");  // uncomment for CI
            opts.AddArgument("--start-maximized");
            opts.AddArgument("--disable-notifications");
            return new ChromeDriver(opts);
        }}
    }}
}}
"""


def _csharp_bat(project_name: str, safe: str) -> str:
    return f"""@echo off
title {project_name} — SpecFlow Automation
echo ============================================================
echo  {project_name}  —  SpecFlow + Selenium Test Suite
echo ============================================================

where dotnet >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] .NET SDK not found. Install from https://dotnet.microsoft.com/download
    pause & exit /b 1
)

if not exist reports mkdir reports

echo [INFO] Restoring packages...
dotnet restore

echo [INFO] Building project...
dotnet build --no-restore

echo [INFO] Running tests...
dotnet test --no-build --logger "html;LogFileName=reports/TestResults.html"

if %ERRORLEVEL% equ 0 (
    echo [SUCCESS] All tests passed.
    start "" "reports\\TestResults.html"
) else (
    echo [FAILURE] Some tests failed.
    start "" "reports\\TestResults.html"
)
pause
"""


def _csharp_sh(project_name: str, safe: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail
echo "=== {project_name} — SpecFlow Automation ==="
mkdir -p reports
dotnet restore
dotnet build --no-restore
dotnet test --no-build --logger "html;LogFileName=reports/TestResults.html"
echo "Done. Check reports/TestResults.html"
"""


def _csharp_readme(project_name: str, base_url: str) -> str:
    return f"""=== {project_name} — C# SpecFlow Selenium Automation ===

TARGET: {base_url}

PREREQUISITES
-------------
.NET 8 SDK (https://dotnet.microsoft.com/download)
Google Chrome (latest)

QUICK START
-----------
Windows:  Double-click run.bat
Linux/Mac: chmod +x run.sh && ./run.sh

MANUAL
------
dotnet restore
dotnet build
dotnet test                                        # all tests
dotnet test --filter Category=smoke                # smoke only

STRUCTURE
---------
Features/          Feature files
StepDefinitions/   Step definitions
PageObjects/       Page Object classes
Hooks/             BeforeScenario / AfterScenario
reports/           Test results HTML
"""


# ------------------------------------------------------------------ #
#  Utility                                                             #
# ------------------------------------------------------------------ #

def _add(zf: zipfile.ZipFile, path: str, content: str):
    zf.writestr(path, content.encode("utf-8"))


def _to_pascal(s: str) -> str:
    import re
    words = re.sub(r"[^a-zA-Z0-9 ]", " ", s).split()
    return "".join(w.capitalize() for w in words) or "Feature"
