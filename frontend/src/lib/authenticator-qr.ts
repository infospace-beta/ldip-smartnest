/** Encode Supabase's raw SVG data URL so Next/Image and browsers preserve it. */
export function authenticatorQrSource(source: string): string {
  const value = source.trim();
  const separator = value.indexOf(",");
  if (separator === -1) return value;
  const header = value.slice(0, separator);
  const payload = value.slice(separator + 1);
  if (/^data:image\/svg\+xml(?:;|$)/i.test(header) &&
      !/;base64(?:;|$)/i.test(header) && payload.trimStart().startsWith("<")) {
    return `${header},${encodeURIComponent(payload)}`;
  }
  return value;
}
