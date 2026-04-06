import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'

// Define routes that should NOT be processed by Clerk
const isPublicRoute = createRouteMatcher(['/api/chat(.*)'])

export default clerkMiddleware((auth, req) => {
  // If it's a public route (like the chat API), just return and do nothing
  if (isPublicRoute(req)) {
    return;
  }
})

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
}
