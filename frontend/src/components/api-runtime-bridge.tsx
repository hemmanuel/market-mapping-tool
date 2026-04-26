"use client";

const LEGACY_API_ORIGIN = "http://localhost:8000";
const FRONTEND_PROXY_PREFIX = "/api/backend";

declare global {
  interface Window {
    __marketApiRuntimeBridgeInstalled?: boolean;
  }
}

function rewriteLegacyApiUrl(rawUrl: string): string {
  if (typeof window === "undefined" || !rawUrl.startsWith(LEGACY_API_ORIGIN)) {
    return rawUrl;
  }

  const parsedUrl = new URL(rawUrl);
  return `${window.location.origin}${FRONTEND_PROXY_PREFIX}${parsedUrl.pathname}${parsedUrl.search}`;
}

function installRuntimeBridge() {
  if (typeof window === "undefined" || window.__marketApiRuntimeBridgeInstalled) {
    return;
  }

  window.__marketApiRuntimeBridgeInstalled = true;

  const originalFetch = window.fetch.bind(window);
  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === "string") {
      return originalFetch(rewriteLegacyApiUrl(input), init);
    }

    if (input instanceof URL) {
      return originalFetch(new URL(rewriteLegacyApiUrl(input.toString())), init);
    }

    if (input.url.startsWith(LEGACY_API_ORIGIN)) {
      return originalFetch(new Request(rewriteLegacyApiUrl(input.url), input), init);
    }

    return originalFetch(input, init);
  }) as typeof window.fetch;

  const OriginalEventSource = window.EventSource;
  class BridgedEventSource extends OriginalEventSource {
    constructor(url: string | URL, eventSourceInitDict?: EventSourceInit) {
      super(rewriteLegacyApiUrl(typeof url === "string" ? url : url.toString()), eventSourceInitDict);
    }
  }

  window.EventSource = BridgedEventSource as typeof EventSource;
}

installRuntimeBridge();

export function ApiRuntimeBridge() {
  return null;
}
