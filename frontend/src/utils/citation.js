/** Signed URLs only use browser-safe HTTP(S) protocols. */
export function safePreviewUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

export function pdfPageUrl(url, page) {
  const safe = safePreviewUrl(url);
  if (!safe) return null;
  const target = new URL(safe);
  const number = Number(page);
  if (Number.isSafeInteger(number) && number > 0) target.hash = `page=${number}`;
  return target.href;
}
