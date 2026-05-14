#!/usr/bin/env python3
"""Verify MLflow setup is complete and ready to run."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def check_environment_variables():
    """Check all required environment variables are set."""
    print("\n📋 Checking environment variables...")

    # Load .env.local
    env_local = Path(".env.local")
    if env_local.exists():
        load_dotenv(env_local)
    else:
        print("   ⚠️  .env.local not found")
        return False

    required_vars = {
        "CA_PATH": "Certificate path",
        "SERVICE_DATABASE_URL": "Service database URL",
        "MLFLOW_DATABASE_URL": "MLflow database URL",
        "AWS_ACCESS_KEY_ID": "AWS access key",
        "AWS_SECRET_ACCESS_KEY": "AWS secret key",
        "AWS_DEFAULT_REGION": "AWS region",
        "MLFLOW_ARTIFACTS_BUCKET": "MLflow artifacts bucket",
    }

    all_set = True
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if "PASSWORD" in var or "KEY" in var or "SECRET" in var:
                display_value = value[:20] + "***" if len(value) > 20 else "***"
            else:
                display_value = value
            print(f"   ✅ {var}: {display_value}")
        else:
            print(f"   ❌ {var}: NOT SET")
            all_set = False

    return all_set


def check_config_file():
    """Check mlflow.yaml configuration file."""
    print("\n⚙️  Checking configuration file...")

    config_path = Path("config/mlflow.yaml")
    if config_path.exists():
        print(f"   ✅ {config_path} exists")
        return True
    else:
        print(f"   ❌ {config_path} not found")
        return False


def check_certificate():
    """Check SSL certificate exists."""
    print("\n🔐 Checking SSL certificate...")

    cert_path = Path("config/certs/ca.pem")
    if cert_path.exists():
        size = cert_path.stat().st_size
        print(f"   ✅ {cert_path} exists ({size} bytes)")
        return True
    else:
        print(f"   ❌ {cert_path} not found")
        return False


def check_dependencies():
    """Check required Python packages."""
    print("\n📦 Checking Python dependencies...")

    required_packages = {
        "mlflow": "MLflow",
        "pymysql": "PyMySQL",
        "dotenv": "python-dotenv",
        "yaml": "PyYAML",
        "boto3": "boto3",
    }

    all_installed = True
    for module, display_name in required_packages.items():
        try:
            __import__(module)
            print(f"   ✅ {display_name}")
        except ImportError:
            print(f"   ❌ {display_name} not installed")
            all_installed = False

    return all_installed


def check_database_connectivity():
    """Test database connection."""
    print("\n🔗 Testing database connectivity...")

    try:
        import mysql.connector
    except ImportError:
        print("   ⚠️  mysql-connector-python not installed (optional)")
        return None

    mlflow_url = os.getenv("MLFLOW_DATABASE_URL")
    if not mlflow_url:
        print("   ❌ MLFLOW_DATABASE_URL not set")
        return False

    # Parse connection details from URL
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(mlflow_url)

    try:
        conn = mysql.connector.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.strip("/"),
            ssl_disabled=False,
            ssl_ca=os.path.expanduser(os.getenv("CA_PATH"))
        )
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                      (parsed.path.strip("/"),))
        table_count = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        print(f"   ✅ MLflow database connected ({table_count} tables)")
        return True
    except Exception as e:
        print(f"   ❌ Database connection failed: {e}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 70)
    print("MLflow Setup Verification")
    print("=" * 70)

    checks = [
        ("Environment Variables", check_environment_variables),
        ("Configuration File", check_config_file),
        ("SSL Certificate", check_certificate),
        ("Python Dependencies", check_dependencies),
        ("Database Connectivity", check_database_connectivity),
    ]

    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"\n   ❌ Error during {name}: {e}")
            results[name] = False

    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)

    for name, result in results.items():
        if result is True:
            status = "✅ PASS"
        elif result is False:
            status = "❌ FAIL"
        else:
            status = "⚠️  SKIP"
        print(f"{name}: {status}")

    # Overall status
    required_passed = all(v is not False for v in results.values())

    print("\n" + "=" * 70)
    if required_passed:
        print("✨ Setup is ready! You can start MLflow with:")
        print("   python script/run_mlflow.py")
        print("\nThen access it at: http://localhost:5001")
        print("=" * 70)
        return 0
    else:
        print("⚠️  Setup has issues. Please fix the failures above.")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
