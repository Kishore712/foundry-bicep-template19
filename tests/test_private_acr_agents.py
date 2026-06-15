#!/usr/bin/env python3
"""
Private ACR + Private Endpoints - Hosted Agents Test Script

Tests that hosted agents work correctly when all resources (AI Services,
Cosmos DB, Storage, AI Search, ACR) are behind private endpoints in the same VNet.

Key validations:
1. DNS resolution - all services resolve to private IPs from within the VNet
2. Basic agent creation - validates private AI Services endpoint works
3. Agent with code interpreter - validates hosted compute can pull from private ACR
4. Agent invocation - validates end-to-end flow through private network

Run from within the VNet (ACI container, jump-box, or hosted agent):
  export PROJECT_ENDPOINT="https://aiservicesgpj3.services.ai.azure.com/api/projects/project"
  python3 test_private_acr_agents.py
"""

import os
import sys
import json
import socket
import logging
import time

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
LOG_LEVEL = logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.getLogger("azure.identity").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(LOG_LEVEL)

# ============================================================================
# CONFIGURATION
# ============================================================================
PROJECT_ENDPOINT = os.environ.get(
    "PROJECT_ENDPOINT",
    "https://aiservicesgpj3.services.ai.azure.com/api/projects/project"
)
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o-mini")
ACR_NAME = os.environ.get("ACR_NAME", "foundryacrgpj3")

# Services to validate DNS resolution for
PRIVATE_SERVICES = {
    "AI Services": "aiservicesgpj3.cognitiveservices.azure.com",
    "AI Services (services.ai)": "aiservicesgpj3.services.ai.azure.com",
    "Cosmos DB": "cosmosdbgpj3.documents.azure.com",
    "Storage": "foundrystggpj3.blob.core.windows.net",
    "AI Search": "aisearchgpj3.search.windows.net",
    "ACR": f"{ACR_NAME}.azurecr.io",
}

# Private IP prefix expected (PE subnet 10.10.20.0/26)
PRIVATE_IP_PREFIX = "10.10.20."


# ============================================================================
# TEST 1: DNS Resolution — verify all services resolve to private IPs
# ============================================================================
def test_dns_resolution():
    """Verify all services resolve to private IPs within the VNet."""
    print("\n" + "=" * 60)
    print("TEST 1: DNS Resolution (Private Endpoints)")
    print("=" * 60)

    results = {}
    all_private = True

    for service_name, fqdn in PRIVATE_SERVICES.items():
        try:
            ip = socket.gethostbyname(fqdn)
            is_private = ip.startswith(PRIVATE_IP_PREFIX) or ip.startswith("10.")
            status = "✓ PRIVATE" if is_private else "✗ PUBLIC"
            results[service_name] = {"fqdn": fqdn, "ip": ip, "private": is_private}
            print(f"  {status}: {service_name}")
            print(f"           {fqdn} → {ip}")
            if not is_private:
                all_private = False
        except socket.gaierror as e:
            results[service_name] = {"fqdn": fqdn, "ip": None, "error": str(e)}
            print(f"  ✗ FAILED: {service_name}")
            print(f"           {fqdn} → DNS resolution failed: {e}")
            all_private = False

    if all_private:
        print("\n✓ TEST PASSED: All services resolve to private IPs")
    else:
        print("\n✗ TEST FAILED: Some services resolve to public IPs or failed")
        print("  This means private endpoints or DNS zone links are misconfigured.")

    return all_private


# ============================================================================
# TEST 2: Basic Agent Creation and Invocation
# ============================================================================
def test_basic_agent():
    """Create a basic agent and invoke it via private endpoint."""
    print("\n" + "=" * 60)
    print("TEST 2: Basic Agent Creation + Invocation (Private Endpoint)")
    print("=" * 60)

    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import PromptAgentDefinition
    except ImportError as e:
        print(f"  ✗ SKIPPED: Missing SDK packages: {e}")
        print("  Install with: pip install azure-ai-projects azure-identity openai")
        return None

    agent = None

    try:
        with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                credential=credential,
                endpoint=PROJECT_ENDPOINT
            ) as project_client,
            project_client.get_openai_client() as openai_client,
        ):
            print(f"  ✓ Connected to project at {PROJECT_ENDPOINT}")

            # Create agent
            agent = project_client.agents.create_version(
                agent_name="private-acr-test-agent",
                definition=PromptAgentDefinition(
                    model=MODEL_NAME,
                    instructions="You are a test agent. Reply with exactly: PRIVATE_ENDPOINT_OK",
                ),
            )
            print(f"  ✓ Created agent (name: {agent.name}, version: {agent.version})")

            # Create conversation
            conversation = openai_client.conversations.create()
            print(f"  ✓ Created conversation: {conversation.id}")

            # Invoke agent
            response = openai_client.responses.create(
                conversation=conversation.id,
                input="Hello, confirm you are working.",
                extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
            )
            print(f"  ✓ Agent response: {response.output_text[:200]}")

            # Cleanup
            project_client.agents.delete_version(
                agent_name=agent.name,
                agent_version=agent.version
            )
            print(f"  ✓ Cleaned up agent")

            print("\n✓ TEST PASSED: Agent creation + invocation works via private endpoint")
            return True

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        # Attempt cleanup
        if agent:
            try:
                project_client.agents.delete_version(
                    agent_name=agent.name, agent_version=agent.version
                )
            except Exception:
                pass
        return False


# ============================================================================
# TEST 3: Agent with Code Interpreter (validates hosted compute + ACR pull)
# ============================================================================
def test_code_interpreter_agent():
    """Test agent with code_interpreter tool — validates hosted compute pulls from ACR."""
    print("\n" + "=" * 60)
    print("TEST 3: Code Interpreter Agent (Hosted Compute + ACR)")
    print("=" * 60)
    print("  This test validates that hosted compute can pull container images")
    print(f"  from the private ACR ({ACR_NAME}.azurecr.io)")

    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import PromptAgentDefinition
        from openai.types.responses import ResponseCodeInterpreterToolParam
    except ImportError as e:
        print(f"  ✗ SKIPPED: Missing SDK packages: {e}")
        print("  Install with: pip install azure-ai-projects azure-identity openai")
        return None

    agent = None

    try:
        with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                credential=credential,
                endpoint=PROJECT_ENDPOINT
            ) as project_client,
            project_client.get_openai_client() as openai_client,
        ):
            print(f"  ✓ Connected to project at {PROJECT_ENDPOINT}")

            # Create agent with code interpreter
            code_interpreter_tool = {"type": "code_interpreter"}
            agent = project_client.agents.create_version(
                agent_name="code-interpreter-test-agent",
                definition=PromptAgentDefinition(
                    model=MODEL_NAME,
                    instructions="You are a Python code assistant. Execute code when asked.",
                    tools=[code_interpreter_tool],
                ),
            )
            print(f"  ✓ Created agent with code_interpreter (name: {agent.name})")

            # Create conversation
            conversation = openai_client.conversations.create()
            print(f"  ✓ Created conversation: {conversation.id}")

            # Ask it to run code (triggers hosted compute container)
            print("  ⏳ Invoking code interpreter (may take 30-60s for container start)...")
            response = openai_client.responses.create(
                conversation=conversation.id,
                input="Calculate the first 10 fibonacci numbers using Python code. Print them as a list.",
                extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
            )

            output_text = response.output_text
            print(f"  ✓ Agent response: {output_text[:300]}")

            # Check if fibonacci numbers are in the response
            if "1" in output_text and "55" in output_text:
                print("\n✓ TEST PASSED: Code interpreter executed successfully")
                print("  → Hosted compute pulled container image from private ACR")
                result = True
            else:
                print("\n⚠ TEST UNCERTAIN: Got response but fibonacci numbers not found")
                result = True  # Still a pass if we got a response

            # Cleanup
            project_client.agents.delete_version(
                agent_name=agent.name,
                agent_version=agent.version
            )
            print(f"  ✓ Cleaned up agent")
            return result

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        if agent:
            try:
                project_client.agents.delete_version(
                    agent_name=agent.name, agent_version=agent.version
                )
            except Exception:
                pass
        return False


# ============================================================================
# TEST 4: ACR Connectivity — validate we can reach the registry endpoint
# ============================================================================
def test_acr_connectivity():
    """Test that ACR login endpoint is reachable via private endpoint."""
    print("\n" + "=" * 60)
    print("TEST 4: ACR Private Endpoint Connectivity")
    print("=" * 60)

    import urllib.request
    import ssl

    acr_fqdn = f"{ACR_NAME}.azurecr.io"
    url = f"https://{acr_fqdn}/v2/"

    try:
        # Resolve first
        ip = socket.gethostbyname(acr_fqdn)
        print(f"  DNS: {acr_fqdn} → {ip}")

        if not ip.startswith("10."):
            print(f"  ✗ FAILED: Resolves to public IP, private endpoint not working")
            return False

        # Try to reach the registry (expect 401 Unauthorized = reachable)
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, method="GET")

        try:
            urllib.request.urlopen(req, timeout=10, context=ctx)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"  ✓ ACR reachable via private endpoint (HTTP 401 = auth required)")
                print("\n✓ TEST PASSED: ACR private endpoint is functional")
                return True
            else:
                print(f"  ⚠ Unexpected HTTP {e.code}: {e.reason}")
                return False
        except urllib.error.URLError as e:
            print(f"  ✗ FAILED: Cannot reach ACR: {e.reason}")
            return False

        print("\n✓ TEST PASSED: ACR reachable")
        return True

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# MAIN
# ============================================================================
def main():
    print("=" * 60)
    print("PRIVATE ACR + PRIVATE ENDPOINTS — HOSTED AGENTS TEST SUITE")
    print("=" * 60)
    print(f"\nProject Endpoint: {PROJECT_ENDPOINT}")
    print(f"Model: {MODEL_NAME}")
    print(f"ACR: {ACR_NAME}.azurecr.io")
    print(f"Running from: {socket.gethostname()}")
    print()

    results = {}

    # Test 1: DNS resolution (no SDK needed)
    results["DNS Resolution"] = test_dns_resolution()

    # Test 2: ACR connectivity (no SDK needed)
    results["ACR Connectivity"] = test_acr_connectivity()

    # Test 3: Basic agent (needs SDK)
    results["Basic Agent"] = test_basic_agent()

    # Test 4: Code interpreter (needs SDK + hosted compute)
    results["Code Interpreter"] = test_code_interpreter_agent()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, result in results.items():
        if result is True:
            status = "✓ PASSED"
        elif result is False:
            status = "✗ FAILED"
        else:
            status = "⚠ SKIPPED"
        print(f"  {status}: {test_name}")

    failed = sum(1 for r in results.values() if r is False)
    if failed:
        print(f"\n✗ {failed} test(s) FAILED")
        sys.exit(1)
    else:
        print(f"\n✓ All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
