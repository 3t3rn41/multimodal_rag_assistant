export function csrfHeaders() {
  if (typeof document === "undefined") return {};
  const entry = document.cookie.split(";").map(x => x.trim()).find(x => x.startsWith("mmrag_csrf="));
  return entry ? { "X-CSRF-Token": decodeURIComponent(entry.slice("mmrag_csrf=".length)) } : {};
}
