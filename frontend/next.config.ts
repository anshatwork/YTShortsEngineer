import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  compiler: {
    // Strip client/server `console.*` from production bundles (dev keeps them).
    // `console.error` is preserved so genuine failures still surface. Diagnostics
    // are recorded regardless via the in-memory debug buffer in lib/debugLog.ts.
    removeConsole:
      process.env.NODE_ENV === "production" ? { exclude: ["error"] } : false,
  },
};

export default nextConfig;
