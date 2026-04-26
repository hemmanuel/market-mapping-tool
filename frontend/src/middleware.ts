import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

// Protect all routes by default
const isProtectedRoute = createRouteMatcher(['/(.*)'])
// Keep internal API routes public from Clerk's perspective so they can proxy or stream correctly
const isPublicApiRoute = createRouteMatcher(['/api/chat(.*)', '/api/backend(.*)'])

export default clerkMiddleware((auth, req) => {
  // Bypass Clerk for internal API routes that proxy or stream
  if (isPublicApiRoute(req)) return NextResponse.next()
  if (req.nextUrl.pathname === '/dashboard') {
    const rewriteUrl = req.nextUrl.clone()
    rewriteUrl.pathname = '/dashboard-live'
    return NextResponse.rewrite(rewriteUrl)
  }
  if (/^\/pipeline\/[^/]+\/graph-progress$/.test(req.nextUrl.pathname)) {
    const rewriteUrl = req.nextUrl.clone()
    rewriteUrl.pathname = `${req.nextUrl.pathname}-live`
    return NextResponse.rewrite(rewriteUrl)
  }
  // Protect everything else
  if (isProtectedRoute(req)) auth().protect();
})

export const config = {
  // Exclude Next.js internals so chunk, CSS, and font requests reach the asset server directly.
  matcher: ['/((?!_next|favicon.ico).*)'],
}
