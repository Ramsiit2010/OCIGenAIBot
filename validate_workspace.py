#!/usr/bin/env python3
"""
Workspace Configuration Validator
Validates all configuration files and dependencies for OCIGenAIBot deployments
"""

import os
import sys
from pathlib import Path
import json

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{text:^60}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.END}\n")

def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")

def check_file_exists(filepath, required=True):
    """Check if file exists"""
    if Path(filepath).exists():
        print_success(f"{filepath} exists")
        return True
    else:
        if required:
            print_error(f"{filepath} NOT FOUND (required)")
        else:
            print_warning(f"{filepath} NOT FOUND (optional)")
        return False

def check_python_files():
    """Validate Python application files"""
    print_header("Python Application Files")
    
    files = [
        ("AskMeChatBot.py", True),
        ("RCOEGenAIAgents.py", True),
        ("mcp_servers/__init__.py", True),
        ("mcp_servers/base_server.py", True),
        ("mcp_servers/advisors.py", True),
    ]
    
    all_ok = True
    for filepath, required in files:
        if not check_file_exists(filepath, required):
            all_ok = False
    
    return all_ok

def check_function_files():
    """Validate OCI Functions files"""
    print_header("OCI Functions Files")
    
    files = [
        ("func_askme.py", True),
        ("func_askme.yaml", True),
        ("func_rcoe.py", True),
        ("func_rcoe.yaml", True),
    ]
    
    all_ok = True
    for filepath, required in files:
        if not check_file_exists(filepath, required):
            all_ok = False
    
    # Validate YAML configuration
    if Path("func_askme.yaml").exists():
        with open("func_askme.yaml") as f:
            content = f.read()
            if "<agent-endpoint-id>" in content:
                print_warning("func_askme.yaml contains placeholder agentEndpointId")
            else:
                print_success("func_askme.yaml agentEndpointId configured")
    
    if Path("func_rcoe.yaml").exists():
        with open("func_rcoe.yaml") as f:
            content = f.read()
            if "<agent-endpoint-id>" in content:
                print_warning("func_rcoe.yaml contains placeholder agentEndpointId")
            else:
                print_success("func_rcoe.yaml agentEndpointId configured")
    
    return all_ok

def check_colab_files():
    """Validate Colab notebook files"""
    print_header("Colab Deployment Files")
    
    files = [
        ("RCOE_OCIGenAIBot.ipynb", True),
        ("Colab_Deploy_RCOE_GenAI_Apps.ipynb", True),
    ]
    
    all_ok = True
    for filepath, required in files:
        if not check_file_exists(filepath, required):
            all_ok = False
    
    # Check notebook configuration
    if Path("RCOE_OCIGenAIBot.ipynb").exists():
        try:
            with open("RCOE_OCIGenAIBot.ipynb", encoding='utf-8') as f:
                notebook = json.load(f)
                # Find APP_MODULE cell
                for cell in notebook.get("cells", []):
                    if cell.get("cell_type") == "code":
                        source = "".join(cell.get("source", []))
                        if "APP_MODULE" in source and "AskMeChatBot:app" in source:
                            print_success("RCOE_OCIGenAIBot.ipynb configured for AskMeChatBot")
                            break
        except Exception as e:
            print_warning(f"Could not validate RCOE_OCIGenAIBot.ipynb: {e}")
    
    if Path("Colab_Deploy_RCOE_GenAI_Apps.ipynb").exists():
        try:
            with open("Colab_Deploy_RCOE_GenAI_Apps.ipynb", encoding='utf-8') as f:
                notebook = json.load(f)
                for cell in notebook.get("cells", []):
                    if cell.get("cell_type") == "code":
                        source = "".join(cell.get("source", []))
                        if "RCOEGenAIAgents.py" in source:
                            print_success("Colab_Deploy_RCOE_GenAI_Apps.ipynb configured for RCOEGenAIAgents")
                            break
        except Exception as e:
            print_warning(f"Could not validate Colab_Deploy_RCOE_GenAI_Apps.ipynb: {e}")
    
    return all_ok

def check_config_files():
    """Validate configuration files"""
    print_header("Configuration Files")
    
    all_ok = True
    
    # Check requirements.txt
    if check_file_exists("requirements.txt", True):
        with open("requirements.txt") as f:
            content = f.read()
            required_packages = ["Flask", "oci", "requests", "python-dotenv", "pyngrok"]
            for pkg in required_packages:
                if pkg in content:
                    print_success(f"requirements.txt includes {pkg}")
                else:
                    print_warning(f"requirements.txt missing {pkg}")
                    all_ok = False
    
    # Check .env and .env.example
    if not check_file_exists(".env", False):
        print_info("Copy .env.example to .env and configure your credentials")
        all_ok = False
    
    check_file_exists(".env.example", True)
    
    if Path(".env.example").exists():
        with open(".env.example") as f:
            content = f.read()
            if "OCI_USER_OCID" in content and "OCI_KEY_FILE" in content:
                print_success(".env.example includes OCI SDK variables")
            else:
                print_warning(".env.example missing OCI SDK variables")
    
    # Check config.properties
    if check_file_exists("config.properties", True):
        with open("config.properties") as f:
            content = f.read()
            if "genai_region=us-chicago-1" in content:
                print_success("config.properties genai_region configured")
            if "genai_intent_mode=" in content:
                print_success("config.properties genai_intent_mode configured")
    
    # Check API spec files
    api_specs = [
        "api_spec_general.json",
        "api_spec_finance.json",
        "api_spec_hr.json",
        "api_spec_orders.json",
        "api_spec_reports.json"
    ]
    for spec in api_specs:
        check_file_exists(spec, True)
    
    return all_ok

def check_sensitive_files():
    """Check for sensitive files and git status"""
    print_header("Security and Git Configuration")
    
    # Check .gitignore
    if check_file_exists(".gitignore", True):
        with open(".gitignore") as f:
            gitignore = f.read()
            checks = [
                (".env", ".env in .gitignore"),
                ("oci_api_key.pem", "oci_api_key.pem in .gitignore"),
                ("*.pem", "*.pem in .gitignore"),
                (".jython_cache", ".jython_cache in .gitignore"),
            ]
            for pattern, desc in checks:
                if pattern in gitignore:
                    print_success(desc)
                else:
                    print_warning(f"{desc} - NOT FOUND")
    
    # Check if sensitive files exist but are not in git
    import subprocess
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            check=True
        )
        untracked = result.stdout
        
        if "oci_api_key.pem" in untracked or ".env" in untracked:
            print_warning("Sensitive files appear in git status (ensure they're in .gitignore)")
        else:
            print_success("Sensitive files properly excluded from git")
    except:
        print_info("Git check skipped (not a git repository or git not installed)")
    
    # Check if sensitive files exist
    if Path("oci_api_key.pem").exists():
        print_success("oci_api_key.pem present (required for OCI SDK)")
    else:
        print_warning("oci_api_key.pem NOT FOUND (download from OCI Console)")
    
    if Path(".env").exists():
        print_success(".env present")
    else:
        print_warning(".env NOT FOUND (copy from .env.example)")

def check_venv():
    """Check virtual environment status"""
    print_header("Virtual Environment")
    
    if not Path(".venv").exists():
        print_warning("Virtual environment not found")
        print_info("Run: python -m venv .venv")
        print_info("Or run: ./setup_env.ps1 (Windows)")
        return False
    
    print_success("Virtual environment exists")
    
    # Check pyvenv.cfg
    if Path(".venv/pyvenv.cfg").exists():
        with open(".venv/pyvenv.cfg") as f:
            content = f.read()
            current_dir = str(Path.cwd())
            if current_dir.replace("\\", "/") not in content.replace("\\", "/"):
                print_warning("Virtual environment created in different directory")
                print_info("Consider recreating venv: Remove-Item -Recurse .venv; python -m venv .venv")
            else:
                print_success("Virtual environment path is correct")
    
    return True

def check_documentation():
    """Check documentation files"""
    print_header("Documentation Files")
    
    files = [
        ("README.md", True),
        ("README_RCOEGenAIAgents.md", True),
        ("IMPLEMENTATION_GUIDE.md", True),
        ("IMPLEMENTATION_GUIDE_RCOEGenAIAgents.md", True),
        ("DEPLOYMENT_SETUP.md", True),
        ("OCI_FUNCTIONS_README.md", True),
    ]
    
    all_ok = True
    for filepath, required in files:
        if not check_file_exists(filepath, required):
            all_ok = False
    
    return all_ok

def main():
    """Main validation function"""
    print_header("OCIGenAIBot Workspace Validation")
    
    # Check if running in correct directory
    if not Path("AskMeChatBot.py").exists():
        print_error("Not in OCIGenAIBot project root!")
        print_info("Please run this script from the project root directory")
        sys.exit(1)
    
    results = {
        "Python Files": check_python_files(),
        "Function Files": check_function_files(),
        "Colab Files": check_colab_files(),
        "Configuration": check_config_files(),
        "Virtual Environment": check_venv(),
        "Documentation": check_documentation(),
    }
    
    check_sensitive_files()
    
    # Summary
    print_header("Validation Summary")
    
    all_passed = True
    for category, passed in results.items():
        if passed:
            print_success(f"{category}: PASSED")
        else:
            print_warning(f"{category}: NEEDS ATTENTION")
            all_passed = False
    
    print()
    if all_passed:
        print_success("All validations passed! Workspace is properly configured.")
        print_info("Ready for:")
        print_info("  • Local development (python AskMeChatBot.py / RCOEGenAIAgents.py)")
        print_info("  • OCI Functions deployment (see OCI_FUNCTIONS_README.md)")
        print_info("  • Google Colab deployment (upload notebooks to Colab)")
    else:
        print_warning("Some validations failed. Please review warnings above.")
        print_info("Run ./setup_env.ps1 (Windows) or see DEPLOYMENT_SETUP.md for help")
    
    print()
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
