# Vue 3 + TypeScript + Vite

This template should help get you started developing with Vue 3 and TypeScript in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about the recommended Project Setup and IDE Support in the [Vue Docs TypeScript Guide](https://vuejs.org/guide/typescript/overview.html#project-setup).

## Dependency installation in restricted environments

If `npm install` fails because of registry/proxy restrictions, use:

```bash
./scripts/install_deps.sh
```

The script tries:
1. default `npm install`,
2. retry without proxy env vars (`http_proxy`, `https_proxy`, etc.),
3. prints actionable instructions (internal mirror / proxy config) if both attempts fail.
