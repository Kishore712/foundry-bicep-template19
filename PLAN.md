# foundry-bicep — Build Plan

> Bicep port of [microsoft-foundry/foundry-samples #19 — `19-private-network-agents-tools-setup`](https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/19-private-network-agents-tools-setup), wrapped in the same hub-spoke + Firewall + jump-box + diagnostics structure as [`nthewara/foundry`](https://github.com/nthewara/foundry) (which is Terraform).

**Status:** 🟡 Plan only — no Bicep written yet. Awaiting review.

---

## 🎯 Goals

1. **Same shape as `nthewara/foundry`** — RG layout, hub-spoke VNet topology, Firewall + UDR egress, Windows jump-box, optional Bastion, full diagnostics to LAW + storage, sanitised `*.bicepparam.example` files.
2. **Same Foundry capability as upstream sample #19** — private AI Services account with network injection into a private VNet, Cosmos DB + AI Search + Storage on private endpoints, capability host, project, model deployment, role assignments.
3. **Bicep-native** — modules, `.bicepparam`, no Terraform, no ARM JSON authoring (only generated `main.json` artifacts if useful).
4. **Pluggable tool servers** — keep upstream's `a2a-server`, `mcp-http-server`, `openapi-server`, `azure-function-server` (toggleable).

---

## 🧱 Architecture (target)

```
                            INTERNET
                                │
                                ▼
┌──────────────────────────────── HUB VNET (10.100.0.0/23) ─────────────────────────────┐
│  AzureFirewallSubnet  AzureBastionSubnet  AzureFirewallMgmtSubnet  GatewaySubnet      │
│       │                    │                                                          │
│  ┌────▼──────┐        ┌────▼─────┐                                                    │
│  │ Azure FW  │        │ Bastion  │ (optional)                                         │
│  │ + Policy  │        └──────────┘                                                    │
│  └───────────┘                                                                        │
└──────────────────┬─────────────────────────────────┬──────────────────────────────────┘
                   │ peering                         │ peering
   ┌───────────────▼─────────┐         ┌─────────────▼──────────────────────────────────┐
   │ SPOKE 1 — VM (10.10.10) │         │ SPOKE 2 — AI APP (10.10.20.0/23)              │
   │  ┌─────────────────┐    │         │  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
   │  │ Win jump-box    │    │         │  │ pe       │  │ agents   │  │ mcp      │    │
   │  └─────────────────┘    │         │  │ /26      │  │ /26 deleg│  │ /26 deleg│    │
   └─────────────────────────┘         │  │ PEs ×N   │  │ App env  │  │ ACA      │    │
                                       │  └──────────┘  └──────────┘  └──────────┘    │
                                       └────────────────────────────────────────────────┘
                                                            │
                                       Private DNS zones (linked to spoke + hub)
                                       AI Foundry account (PNA disabled, networkInjections)
                                       Cosmos DB / Storage / AI Search (private)
                                       Capability host + project + model deployment
```

### Deltas vs. upstream sample #19
| Area | Upstream | This repo |
|---|---|---|
| VNet | single new VNet OR existing | **Hub + 2 spokes** (mirrors `nthewara/foundry`) |
| Egress | direct | **Azure Firewall + UDR** on agent/pe/mcp subnets |
| Mgmt access | (none) | **Windows jump-box** + optional **Bastion** |
| Observability | (none) | **LAW + storage** diagnostics on every resource (VNets, NSGs, PIPs, KV, ACR, FW, AIS, Cosmos, Search, Storage) |
| MCP subnet | yes | yes (kept) |
| Tool servers | yes | yes (a2a, mcp, openapi, function) — flag-gated |
| Secrets | inline params | **Key Vault reference** in `.bicepparam` for `vmAdminPassword`, etc. |
| Naming | `uniqueString` | `prefix-<role>-<random>` to match nthewara/foundry style |

---

## 📁 Repo layout (proposed)

```
foundry-bicep/
├── README.md                          # full docs (architecture, deploy, troubleshoot, costs)
├── PLAN.md                            # this file
├── SECURITY_REVIEW.md                 # ported from nthewara/foundry (Defender, NSG, PE posture)
├── main.bicep                         # top-level subscription/RG-scope orchestrator
├── main.bicepparam.example            # sanitised parameters (committed)
├── .gitignore                         # blocks *.bicepparam (real), *.tfvars, backend.hcl
├── modules/
│   ├── networking/
│   │   ├── hub-vnet.bicep             # hub VNet + AzFW/Bastion/Mgmt/Gateway subnets
│   │   ├── spoke-vm.bicep             # VM spoke + peering
│   │   ├── spoke-aiapp.bicep          # AI app spoke + pe/agents/mcp subnets + delegations
│   │   ├── peering.bicep              # bidirectional hub<->spoke
│   │   └── route-table.bicep          # UDR forcing 0.0.0.0/0 → Firewall
│   ├── firewall/
│   │   ├── firewall.bicep             # AzFW (Basic/Standard SKU), policy, PIP
│   │   └── firewall-rules.bicep       # rule collection group (web + RFC1918)
│   ├── bastion/
│   │   └── bastion.bicep              # optional, Developer or Basic SKU
│   ├── vm/
│   │   └── jumpbox.bicep              # Windows jump-box NIC + VM (+ KV password ref)
│   ├── foundry/                       # ← ported from upstream `modules-network-secured/`
│   │   ├── vnet.bicep                 # new VNet flow (we will NOT use; spoke-aiapp covers it)
│   │   ├── existing-vnet.bicep        # we feed our spoke-aiapp here
│   │   ├── subnet.bicep
│   │   ├── network-agent-vnet.bicep
│   │   ├── private-endpoint-and-dns.bicep
│   │   ├── standard-dependent-resources.bicep   # Cosmos + Storage + AI Search
│   │   ├── ai-account-identity.bicep
│   │   ├── ai-project-identity.bicep
│   │   ├── ai-project-identity-unique.bicep
│   │   ├── format-project-workspace-id.bicep
│   │   ├── add-project-capability-host.bicep
│   │   ├── validate-existing-resources.bicep
│   │   ├── ai-search-role-assignments.bicep
│   │   ├── azure-storage-account-role-assignment.bicep
│   │   ├── blob-storage-container-role-assignments.bicep
│   │   ├── blob-storage-container-role-assignments-unique.bicep
│   │   ├── cosmos-container-role-assignments.bicep
│   │   └── cosmosdb-account-role-assignment.bicep
│   ├── diagnostics/
│   │   ├── law.bicep                  # Log Analytics workspace
│   │   ├── storage-diag.bicep         # Diagnostics archive storage account
│   │   └── diag-setting.bicep         # reusable module: one per resource
│   └── project/
│       ├── add-project.bicep          # standalone project add (mirrors upstream)
│       └── add-project.bicepparam.example
├── add-project.bicep                  # top-level wrapper (matches upstream layout)
├── tool-servers/                      # ported as-is from upstream, code unchanged
│   ├── a2a-server/                    # Dockerfile + main.py + requirements.txt
│   ├── mcp-http-server/
│   ├── openapi-server/
│   └── azure-function-server/         # incl. deploy-function.bicep
├── scripts/
│   ├── createCapHost.sh               # ported from upstream
│   ├── deleteCapHost.sh               # ported from upstream
│   └── get-existing-resources.ps1     # ported from upstream
├── tests/                             # ported from upstream
│   └── …all 7 test_*_agents_v2.py + TESTING-GUIDE.md
├── diagrams/                          # ported + regenerate with our hub-spoke
└── dashboards/
    ├── dashboard.json                 # from nthewara/foundry
    └── workbook.json                  # from nthewara/foundry
```

---

## 🔧 Parameter surface (`main.bicep`)

Mirrors `nthewara/foundry` variables + upstream Foundry params:

```bicep
// General
param subscriptionId string                  // for tag/scope only
param location string = 'australiaeast'
param prefix string = 'aifoundrybicep'

// VNet config
param hubVnetPrefix string = '10.100.0.0/23'
param vmVnetPrefix string = '10.10.10.0/23'
param aiappVnetPrefix string = '10.10.20.0/23'

// Feature toggles
param fwProvision bool = true
param fwSku string = 'Standard'
param vmDeploy bool = true
param bastionProvision bool = false

// Foundry / model
param aiServicesName string = 'aiservices'
param projectName string = 'project'
param modelName string = 'gpt-4o-mini'
param modelFormat string = 'OpenAI'
param modelVersion string = '2024-07-18'
param modelSkuName string = 'GlobalStandard'
param modelCapacity int = 30

// Secrets via Key Vault
@secure() param vmAdminPassword string       // resolved from KV in .bicepparam
param vmAdminUsername string = 'azureadmin'

// DNS zones (defaults match upstream + nthewara/foundry merged set)
param privateDnsZones array = [
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.services.ai.azure.com'
  'privatelink.blob.core.windows.net'
  'privatelink.search.windows.net'
  'privatelink.documents.azure.com'
]
```

`main.bicepparam` will be **gitignored**; only `main.bicepparam.example` committed.

---

## 🛠 Deploy flow (target UX)

```bash
# 1. Real params live outside repo
~/workspace/tfvars/foundry-bicep.bicepparam     # gitignored sibling

# 2. Subscription-scope deploy (creates RG + everything)
az deployment sub create \
  --location australiaeast \
  --template-file main.bicep \
  --parameters ~/workspace/tfvars/foundry-bicep.bicepparam

# 3. After main deploy → capability host (existing upstream script)
./scripts/createCapHost.sh <rg> <aiservicesAccountName> <projectName>

# 4. Add another project later
az deployment group create \
  -g <rg> \
  --template-file add-project.bicep \
  --parameters ~/workspace/tfvars/foundry-bicep-project2.bicepparam
```

---

## 📦 Phased build (suggested PRs)

| Phase | Scope | Branch | Approx LOC |
|---|---|---|---|
| **P0** | Repo skeleton, README, PLAN, .gitignore, `main.bicepparam.example` (placeholders only) | `chore/scaffold` | ~150 |
| **P1** | Networking modules: hub VNet, 2 spokes, peering, UDR | `feat/networking` | ~400 |
| **P2** | Firewall + Bastion + Jump-box modules | `feat/edge-and-mgmt` | ~350 |
| **P3** | Diagnostics module (LAW + storage + reusable diag-setting) | `feat/diagnostics` | ~250 |
| **P4** | Port upstream Foundry `modules-network-secured/` into `modules/foundry/`, wire to spoke-aiapp | `feat/foundry-core` | ~800 |
| **P5** | Top-level `main.bicep` orchestration + `add-project.bicep` | `feat/orchestrator` | ~250 |
| **P6** | Port tool servers (a2a, mcp, openapi, function) as-is | `feat/tool-servers` | unchanged copy |
| **P7** | Port scripts, tests, diagrams, dashboards | `feat/ops-assets` | unchanged copy |
| **P8** | E2E deploy in lab sub, fix bugs, lock in `lab-tracker` entry | `lab/foundrybicep-v1` | n/a |

Each phase = 1 PR, reviewable in isolation. P1–P3 are pure-infra and can run before any Foundry bits land.

---

## ✅ Acceptance criteria

- `bicep build main.bicep` succeeds with **zero warnings** in strict mode.
- `az deployment sub validate` passes against the lab sub.
- End-to-end deploy in `australiaeast` produces:
  - Working hub-spoke with peering + UDRs pointing at Firewall
  - Reachable jump-box via Bastion (when enabled) or via FW DNAT
  - AI Foundry account with `publicNetworkAccess = Disabled` + `networkInjections`
  - All 4 dependent resources (AIS, Cosmos, Storage, AI Search) on private endpoints, no public access
  - All 6 private DNS zones linked to spoke-aiapp + hub
  - Diagnostics enabled on every resource with logs flowing to LAW
  - At least one chat completion works from inside jump-box
  - All 7 upstream `test_*_agents_v2.py` tests pass
- Lab tracker updated with RG name, region, ~$/day cost estimate, deallocate/restore commands.

---

## 🚦 Open questions for review

1. **Firewall SKU default** — keep `Standard` (matches nthewara/foundry) or default to `Basic` to save ~$25/day for short-lived labs?
2. **Bastion default** — leave `bastionProvision = false` and rely on FW DNAT for RDP, or flip to `true` and skip Firewall NAT rules?
3. **DNS zones** — upstream creates them in the same RG. Want a flag to point at an existing shared DNS RG instead (some tenants centralise these)?
4. **Tool servers** — port all four (a2a, mcp, openapi, function) day-1, or just `mcp-http-server` + `azure-function-server` since they're the ones exercised in the tests?
5. **`add-project` standalone** — keep upstream's pattern of a separate top-level `add-project.bicep`, or fold it into `main.bicep` behind a `param projectsToAdd array`?
6. **Lab tracker entry** — name the lab `foundrybicep-<rand>` once we deploy P8?

---

## 🔗 References

- Upstream sample: <https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/19-private-network-agents-tools-setup>
- Terraform predecessor: <https://github.com/nthewara/foundry>
- Foundry BYO VNet docs: <https://learn.microsoft.com/azure/ai-foundry/how-to/configure-private-link>
