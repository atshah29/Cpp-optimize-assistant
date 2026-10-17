# Optimizer frontend

React/Vite interface for the local C++ optimizer. See the [root README](../README.md) for backend, runner, and benchmark-suite setup.

```sh
npm ci
npm run dev
```

The API must run on `127.0.0.1:8000`; Vite proxies `/api` there. No provider key belongs in frontend environment variables. Run `npm run lint` and `npm run build` to verify. The backend serves the built frontend after restart.
