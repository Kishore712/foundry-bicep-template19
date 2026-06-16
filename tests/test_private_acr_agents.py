#!/usr/bin/env python3
"""
Private ACR Hosted Agent Test — End-to-End Validation Script

Runs from inside the VNet (ACI container with Managed Identity) and validates:
  1. DNS resolution — all private services resolve to private IPs
  2. ACR connectivity — private endpoint is reachable (HTTP 401)
  3. Hosted agent creation — deploys debug-agent container via Foundry API
  4. ACR probe from hosted compute — agent probes DNS/TCP/TLS/HTTP to private ACR

Configuration via environment variables (set by ACI deployment):
  PROJECT_ENDPOINT  — Foundry project data-plane endpoint
  ACR_HOST          — Private ACR hostname (e.g. myacr.azurecr.io)
  ACR_REGION        — ACR region for data endpoint derivation
  AI_SERVICES_NAME  — AI Services account name
  COSMOS_DB_NAME    — Cosmos DB account name
  STORAGE_NAME      — Storage account name
  AI_SEARCH_NAME    — AI Search service name

Usage:
  python3 /opt/test_agent.py                    # Full E2E test
  python3 /opt/test_agent.py --skip-agent       # DNS + ACR connectivity only
  python3 /opt/test_agent.py --private-acr X    # Override ACR host
"""
import os
import sys
import json
import time
import socket
import ssl
import argparse
import urllib.request

try:
    import requests
    from azure.identity import ManagedIdentityCredential
except ImportError:
    print("ERROR: Missing packages. Run: pip install requests azure-identity")
    sys.exit(2)

# ============================================================================
# CONFIGURATION — from environment or defaults
# ============================================================================
PROJECT_ENDPOINT = os.environ.get("PROJECT_ENDPOINT", "")
ACR_HOST = os.environ.get("ACR_HOST", "")
ACR_REGION = os.environ.get("ACR_REGION", "")
AI_SERVICES_NAME = os.environ.get("AI_SERVICES_NAME", "")
COSMOS_DB_NAME = os.environ.get("COSMOS_DB_NAME", "")
STORAGE_NAME = os.environ.get("STORAGE_NAME", "")
AI_SEARCH_NAME = os.environ.get("AI_SEARCH_NAME", "")

API_VERSION = "2025-11-15-preview"
TOKEN_SCOPE = "https://ai.azure.com/.default"
IMAGE = "e2etestswestus2acr.azurecr.io/samples/python/hosted-agents/invocations/debug-agent:26.06.1201"
AGENT_NAME = "debug-agent-private-acr-test"


def _build_services_map(ai_services, cosmos, storage, search, acr):
    """Build FQDN map from resource names."""
    services = {}
    if ai_services:
        services["AI Services (cognitiveservices)"] = f"{ai_services}.cognitiveservices.azure.com"
        services["AI Services (services.ai)"] = f"{ai_services}.services.ai.azure.com"
    if cosmos:
        services["Cosmos DB"] = f"{cosmos}.documents.azure.com"
    if storage:
        services["Storage (blob)"] = f"{storage}.blob.core.windows.net"
    if search:
        services["AI Search"] = f"{search}.search.windows.net"
    if acr:
        services["ACR"] = acr
    return services


# ============================================================================
# TEST 1: DNS Resolution
# ============================================================================
def test_dns(services):
    print("\n" + "=" * 60)
    print("TEST 1: DNS Resolution — all services must resolve to private IPs")
    print("=" * 60)
    if not services:
        print("  SKIPPED: No service names configured")
        return None
    all_ok = True
    for name, fqdn in services.items():
        try:
            ip = socket.gethostbyname(fqdn)
            is_private = ip.startswith("10.") or ip.startswith("172.") or ip.startswith("192.168.")
            status = "PRIVATE" if is_private else "PUBLIC !!!"
            print(f"  [{status}] {name}: {fqdn} -> {ip}")
            if not is_private:
                all_ok = False
        except Exception as e:
            print(f"  [FAILED] {name}: {fqdn} -> {e}")
            all_ok = False
    if all_ok:
        print("  >>> PASSED: All services resolve to private IPs")
    else:
        print("  >>> FAILED: Some services NOT private")
    return all_ok


# ============================================================================
# TEST 2: ACR Connectivity
# ============================================================================
def test_acr_connectivity(acr_host):
    print("\n" + "=" * 60)
    print(f"TEST 2: ACR Connectivity — {acr_host}")
    print("=" * 60)
    if not acr_host:
        print("  SKIPPED: No ACR host configured")
        return None
    try:
        ip = socket.gethostbyname(acr_host)
        is_private = ip.startswith("10.") or ip.startswith("172.") or ip.startswith("192.168.")
        print(f"  DNS: {acr_host} -> {ip} ({'PRIVATE' if is_private else 'PUBLIC !!!'})")
        if not is_private:
            print("  >>> FAILED: ACR resolves to public IP")
            return False
    except Exception as e:
        print(f"  DNS FAILED: {e}")
        return False

    ctx = ssl.create_default_context()
    url = f"https://{acr_host}/v2/"
    try:
        urllib.request.urlopen(urllib.request.Request(url), timeout=10, context=ctx)
        print(f"  HTTP: {url} -> 200 (reachable)")
        print("  >>> PASSED")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print(f"  HTTP: {url} -> 401 Unauthorized (EXPECTED — registry reachable)")
            print("  >>> PASSED")
            return True
        else:
            print(f"  HTTP: {url} -> {e.code} {e.reason} (reachable)")
            return True
    except Exception as e:
        print(f"  HTTP FAILED: {e}")
        return False


# ============================================================================
# TEST 3: Hosted Agent Creation + Invocation
# ============================================================================
def test_hosted_agent(project_endpoint, acr_host, acr_region):
    print("\n" + "=" * 60)
    print("TEST 3: Hosted Agent — create, activate, invoke with ACR probe")
    print("=" * 60)
    if not project_endpoint:
        print("  SKIPPED: PROJECT_ENDPOINT not set")
        return None

    print("  Acquiring token via Managed Identity...")
    try:
        cred = ManagedIdentityCredential()
        tok = cred.get_token(TOKEN_SCOPE)
    except Exception as e:
        print(f"  Auth FAILED: {e}")
        return False

    headers = {
        "Authorization": f"Bearer {tok.token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Foundry-Features": "HostedAgents=V1Preview,AgentEndpoints=V1Preview",
    }

    # Create version
    print(f"  Creating hosted agent: {AGENT_NAME}")
    url = f"{project_endpoint}/agents/{AGENT_NAME}/versions?api-version={API_VERSION}"
    body = {
        "definition": {
            "kind": "hosted",
            "image": IMAGE,
            "cpu": "0.5",
            "memory": "1Gi",
            "environment_variables": {},
            "container_protocol_versions": [
                {"protocol": "invocations", "version": "1.0.0"}
            ],
        }
    }
    resp = requests.post(url, headers=headers, json=body, timeout=120)
    print(f"  Create status: {resp.status_code}")
    if not resp.ok:
        print(f"  ERROR: {resp.text[:500]}")
        return False

    result = resp.json()
    version_id = result.get("version") or result.get("id")
    print(f"  Version: {version_id}, Status: {result.get('status')}")

    # Poll for active
    print("  Polling for active...")
    status = ""
    for i in range(30):
        time.sleep(10)
        poll_url = f"{project_endpoint}/agents/{AGENT_NAME}/versions/{version_id}?api-version={API_VERSION}"
        resp = requests.get(poll_url, headers=headers, timeout=30)
        data = resp.json()
        status = (data.get("status") or "").lower()
        print(f"    Poll {i+1}/30: status={status}")
        if status == "active":
            break
        if status == "failed":
            print(f"    FAILED: {json.dumps(data, indent=2)}")
            return False

    if status != "active":
        print("  ERROR: Timed out waiting for active")
        return False

    # Invoke with ACR probe hosts
    hosts_to_probe = [acr_host] if acr_host else []
    if acr_host and acr_region and ".data." not in acr_host:
        hosts_to_probe.append(acr_host.replace(".azurecr.io", f".{acr_region}.data.azurecr.io"))

    print(f"  Invoking with probe hosts: {hosts_to_probe}")
    invoke_url = (
        f"{project_endpoint}/agents/{AGENT_NAME}/endpoint/protocols/invocations"
        f"?api-version={API_VERSION}&agent_session_id=test-{int(time.time())}"
    )
    resp = requests.post(invoke_url, headers=headers, json={"hosts": hosts_to_probe}, timeout=120)
    print(f"  Invoke status: {resp.status_code}")

    invoke_ok = False
    if resp.ok:
        body = resp.json()
        overall = body.get("status", "unknown")
        print(f"  Result: status={overall}")

        checks = body.get("checks", {})
        for host_result in checks.get("hosts", []):
            h = host_result.get("host", "?")
            dns_ok = host_result.get("dns", {}).get("all_private", False)
            tcp_ok = host_result.get("tcp_443", {}).get("status") == "ok"
            tls_ok = host_result.get("tls_443", {}).get("status") == "ok"
            http_code = host_result.get("http_get", {}).get("code", "?")
            print(f"    {h}: dns_private={dns_ok} tcp={tcp_ok} tls={tls_ok} http={http_code}")

        if overall == "ok":
            print("  >>> PASSED: All probes OK from hosted compute")
            invoke_ok = True
        else:
            print(f"  >>> WARNING: status={overall}")
            print(f"  Full response:\n{json.dumps(body, indent=2)}")
    else:
        print(f"  ERROR: {resp.text[:500]}")

    # Cleanup
    print(f"  Deleting version {version_id}...")
    del_url = f"{project_endpoint}/agents/{AGENT_NAME}/versions/{version_id}?api-version={API_VERSION}"
    del_resp = requests.delete(del_url, headers=headers, timeout=60)
    print(f"  Delete: {del_resp.status_code}")

    return invoke_ok


# ============================================================================
# MAIN
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Private ACR + Hosted Agent — End-to-End Validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Environment variables override defaults. See script header for details.",
    )
    parser.add_argument("--private-acr", default=ACR_HOST, help="ACR hostname to test")
    parser.add_argument("--region", default=ACR_REGION, help="ACR region")
    parser.add_argument("--project-endpoint", default=PROJECT_ENDPOINT, help="Foundry project endpoint")
    parser.add_argument("--skip-agent", action="store_true", help="Skip hosted agent test (DNS + ACR only)")
    args = parser.parse_args()

    services = _build_services_map(AI_SERVICES_NAME, COSMOS_DB_NAME, STORAGE_NAME, AI_SEARCH_NAME, args.private_acr)

    print("=" * 60)
    print("PRIVATE ACR + HOSTED AGENTS — END-TO-END VALIDATION")
    print("=" * 60)
    print(f"  ACR:      {args.private_acr or '(not set)'}")
    print(f"  Region:   {args.region or '(not set)'}")
    print(f"  Endpoint: {args.project_endpoint or '(not set)'}")
    print(f"  Host:     {socket.gethostname()}")
    print(f"  Services: {len(services)} configured")

    results = {}
    results["DNS Resolution"] = test_dns(services)
    results["ACR Connectivity"] = test_acr_connectivity(args.private_acr)

    if not args.skip_agent:
        results["Hosted Agent"] = test_hosted_agent(args.project_endpoint, args.private_acr, args.region)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, ok in results.items():
        if ok is True:
            s = "✓ PASSED"
        elif ok is False:
            s = "✗ FAILED"
        else:
            s = "⚠ SKIPPED"
        print(f"  {s}: {name}")

    failed = sum(1 for v in results.values() if v is False)
    if failed:
        print(f"\n✗ {failed} test(s) FAILED")
        sys.exit(1)
    else:
        print("\n✓ All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
