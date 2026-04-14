# Policy | Architecture Guardrails

## Policy

- Derive implementation boundaries from the live architecture and current service seams, not from aspirational or superseded layouts by default.
- Do not add new top-level workflows, endpoints, abstractions, or major aliases unless the governing plan or roadmap is updated in the same slice.
- Prefer tightening semantics and ownership boundaries over widening the surface area opportunistically.
- Keep provider-specific or deployment-specific heuristics at the narrowest layer that can own them cleanly.
- When a change would blur current architecture boundaries, stop and update the governing plan before proceeding.
## Adoption Notes

Use this module when the repo:
- has a service or architecture seam that must stay coherent
- has active refactors or staged migration work
- frequently risks structural drift through ad hoc feature additions
