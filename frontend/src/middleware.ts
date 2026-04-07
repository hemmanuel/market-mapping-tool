import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'

// Protect all routes by default
const isProtectedRoute = createRouteMatcher(['/(.*)'])
// Keep the chat API public from Clerk's perspective so Gemini works
const isPublicApiRoute = createRouteMatcher(['/api/chat(.*)'])
// Match static files
const isStaticAsset = createRouteMatcher(['/_next(.*)', '/favicon.ico'])

export default clerkMiddleware((auth, req) => {
  // Bypass Clerk completely for static assets to prevent 404 crashes
  if (isStaticAsset(req)) return;
  // Bypass Clerk for the AI chat endpoint
  if (isPublicApiRoute(req)) return;
  // Protect everything else
  if (isProtectedRoute(req)) auth().protect();
})

export const config = {
  // Run middleware on ALL routes so auth() never crashes on 404s
  matcher: ['/(.*)'],
}
