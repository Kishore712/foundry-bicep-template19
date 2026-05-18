# foundry-bicep

Bicep port of [microsoft-foundry/foundry-samples #19 — private-network-agents-tools-setup](https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/19-private-network-agents-tools-setup), wrapped in the hub-spoke + Firewall + jump-box + full-diagnostics structure from [`nthewara/foundry`](https://github.com/nthewara/foundry) (Terraform).

🚧 **Currently in planning** — see [PLAN.md](./PLAN.md) for the full build plan, parameter surface, phased PRs, and open questions.

## Quick links
- 📋 [Build plan](./PLAN.md)
- 🔗 Upstream Bicep sample: <https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/19-private-network-agents-tools-setup>
- 🔗 Terraform predecessor: <https://github.com/nthewara/foundry>

## Status

| Phase | Status |
|---|---|
| P0 — Scaffold + plan | ✅ in this commit |
| P1 — Networking modules | ⏳ pending review of PLAN.md |
| P2 — Firewall + Bastion + jump-box | ⏳ |
| P3 — Diagnostics | ⏳ |
| P4 — Foundry core modules | ⏳ |
| P5 — Orchestrator | ⏳ |
| P6 — Tool servers | ⏳ |
| P7 — Ops assets | ⏳ |
| P8 — E2E lab deploy | ⏳ |
