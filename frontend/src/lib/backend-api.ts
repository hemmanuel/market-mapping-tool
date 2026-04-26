export function backendApiPath(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `/api/backend${normalizedPath}`;
}
