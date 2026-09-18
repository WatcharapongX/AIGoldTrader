"use client";

import { useEffect } from "react";
import { purgeLegacyAuthStorage } from "@/lib/auth-token-memory";

// Synchronous purge at client module evaluation time before components mount
if (typeof window !== "undefined") {
  purgeLegacyAuthStorage();
}

/**
 * Global client component mounted once in RootLayout.
 * Ensures legacy persistent auth tokens (access_token, refresh_token)
 * in localStorage and sessionStorage are purged on every route entry (/login, /dashboard, etc.)
 * without reading, decoding, migrating, or transmitting them, and without touching volatile memory tokens.
 */
export function AuthStorageSanitizer() {
  useEffect(() => {
    purgeLegacyAuthStorage();
  }, []);

  return null;
}
