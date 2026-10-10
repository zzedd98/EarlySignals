"""
Script to import seed list CSV into Early Signals API
"""
import csv
import sys
import argparse
import httpx
from pathlib import Path
from typing import List, Dict, Any


def normalize_domain(domain_str: str) -> str:
    """Normalize domain string"""
    domain_str = domain_str.strip().lower()
    if "://" in domain_str:
        domain_str = domain_str.split("://")[1]
    domain_str = domain_str.rstrip("/")
    if domain_str.startswith("www."):
        domain_str = domain_str[4:]
    return domain_str


def read_csv_domains(csv_path: Path) -> List[Dict[str, Any]]:
    """Read domains (and optional working_paths) from CSV file"""
    domains: List[Dict[str, Any]] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Try "domain" column first, then first column
            domain_str = row.get("domain") or (list(row.values())[0] if row else None)
            if domain_str:
                normalized = normalize_domain(domain_str)
                if normalized:
                    item: Dict[str, Any] = {"domain": normalized}
                    # Propager éventuellement la colonne working_paths telle quelle
                    working_paths_raw = row.get("working_paths")
                    if working_paths_raw:
                        item["working_paths"] = working_paths_raw
                    domains.append(item)
    return domains


def import_domains(
    api_url: str,
    email: str,
    password: str,
    domains: List[Dict[str, Any]],
    org_id: str = None,
) -> Dict[str, int]:
    """Import domains to API"""
    # Authenticate
    print(f"Authenticating to {api_url}...")
    with httpx.Client(timeout=30.0) as client:
        # Login
        login_response = client.post(
            f"{api_url}/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        if login_response.status_code != 200:
            print(f"❌ Authentication failed: {login_response.status_code}")
            print(login_response.text)
            return {"imported": 0, "skipped": 0, "errors": len(domains)}
        
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Import domains via CSV upload endpoint
        # We'll create a temporary CSV in memory
        import io
        
        csv_content = io.StringIO()
        writer = csv.writer(csv_content)
        # On inclut la colonne working_paths si elle existe dans au moins une ligne
        has_working_paths = any("working_paths" in d and d["working_paths"] for d in domains)
        header = ["domain"]
        if has_working_paths:
            header.append("working_paths")
        writer.writerow(header)
        for d in domains:
            row = [d["domain"]]
            if has_working_paths:
                row.append(d.get("working_paths", ""))
            writer.writerow(row)
        
        csv_content.seek(0)
        
        # Upload CSV
        files = {
            "file": ("domains.csv", csv_content.getvalue().encode("utf-8"), "text/csv")
        }
        
        print(f"Importing {len(domains)} domains...")
        import_response = client.post(
            f"{api_url}/api/v1/domains/import",
            files=files,
            headers=headers,
        )
        
        if import_response.status_code == 200:
            result = import_response.json()
            print(f"✅ Import completed:")
            print(f"   - Imported: {result.get('imported', 0)}")
            print(f"   - Skipped: {result.get('skipped', 0)}")
            if result.get("errors"):
                print(f"   - Errors: {len(result['errors'])}")
                for error in result["errors"][:5]:  # Show first 5 errors
                    print(f"     • {error}")
            return result
        else:
            print(f"❌ Import failed: {import_response.status_code}")
            print(import_response.text)
            return {"imported": 0, "skipped": 0, "errors": len(domains)}


def main():
    parser = argparse.ArgumentParser(description="Import seed list CSV to Early Signals API")
    parser.add_argument(
        "csv_file",
        type=str,
        help="Path to CSV file with domains (must have 'domain' column)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8000",
        help="API URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--email",
        type=str,
        required=True,
        help="Admin email for authentication",
    )
    parser.add_argument(
        "--password",
        type=str,
        required=True,
        help="Admin password for authentication",
    )
    
    args = parser.parse_args()
    
    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"❌ CSV file not found: {csv_path}")
        sys.exit(1)
    
    # Read domains
    print(f"Reading domains from {csv_path}...")
    domains = read_csv_domains(csv_path)
    print(f"Found {len(domains)} domains")
    
    if not domains:
        print("❌ No domains found in CSV file")
        sys.exit(1)
    
    # Import
    result = import_domains(
        api_url=args.api_url,
        email=args.email,
        password=args.password,
        domains=domains,
    )
    
    if result.get("imported", 0) > 0:
        print(f"\n✅ Successfully imported {result['imported']} domains!")
        sys.exit(0)
    else:
        print("\n❌ No domains were imported")
        sys.exit(1)


if __name__ == "__main__":
    main()
