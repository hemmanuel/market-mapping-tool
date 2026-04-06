import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'

// Protect all routes by default
const isProtectedRoute = createRouteMatcher(['/(.*)'])
// Keep the chat API public from Clerk's perspective so Gemini works
const isPublicApiRoute = createRouteMatcher(['/api/chat(.*)'])

export default clerkMiddleware((auth, req) => {
  // Bypass Clerk for the AI chat endpoint
  if (isPublicApiRoute(req)) return;
  // Protect everything else
  if (isProtectedRoute(req)) auth().protect();
})

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
}
