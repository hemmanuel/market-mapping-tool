import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const API_BASE_URL =
  process.env.API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8100";

const REQUEST_HEADERS_TO_SKIP = new Set([
  "connection",
  "content-length",
  "host",
]);

const RESPONSE_HEADERS_TO_SKIP = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "transfer-encoding",
]);

function buildTargetUrl(pathParts: string[], request: NextRequest): string {
  const baseUrl = API_BASE_URL.endsWith("/") ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
  const upstreamPath = pathParts.join("/");
  const incomingUrl = new URL(request.url);
  return `${baseUrl}/${upstreamPath}${incomingUrl.search}`;
}

async function proxyRequest(
  request: NextRequest,
  { params }: { params: { path: string[] } }
): Promise<Response> {
  const targetUrl = buildTargetUrl(params.path, request);
  const headers = new Headers();

  for (const [key, value] of Array.from(request.headers.entries())) {
    if (!REQUEST_HEADERS_TO_SKIP.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  }

  const hasBody = !["GET", "HEAD"].includes(request.method.toUpperCase());
  const body = hasBody ? await request.arrayBuffer() : undefined;

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown proxy error";
    return Response.json(
      {
        error: "backend_proxy_error",
        message,
        target_url: targetUrl,
      },
      { status: 502 }
    );
  }

  const responseHeaders = new Headers(upstream.headers);
  for (const key of Array.from(RESPONSE_HEADERS_TO_SKIP)) {
    responseHeaders.delete(key);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export async function GET(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}

export async function POST(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}

export async function PUT(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}

export async function PATCH(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}

export async function DELETE(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}

export async function OPTIONS(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}

export async function HEAD(request: NextRequest, context: { params: { path: string[] } }) {
  return proxyRequest(request, context);
}
