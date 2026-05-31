/**
 * Convert iPhone HEIC/HEIF photos to JPEG so the browser can preview
 * them. Chrome and Firefox can't decode HEIC natively; Safari can,
 * but we still want a consistent JPEG everywhere so caching and
 * thumbnail rendering behave the same across browsers.
 *
 * Uses ``heic2any``, which loads a WASM decoder lazily. We import it
 * dynamically so the cost (~1 MB) is only paid on the first HEIC
 * upload — most customers upload JPEGs and never trigger this.
 */

const HEIC_MIMES = new Set(["image/heic", "image/heif"]);

function isHeic(file: File): boolean {
  if (HEIC_MIMES.has(file.type.toLowerCase())) return true;
  // Some browsers report empty mime for files dragged from Finder.
  if (!file.type && /\.(heic|heif)$/i.test(file.name)) return true;
  return false;
}

/**
 * Returns the file unchanged if it isn't HEIC; otherwise returns a
 * new ``File`` containing a JPEG version of the same image.
 *
 * If the conversion fails for any reason we fall back to the original
 * — the backend can still process HEIC, only the in-browser preview
 * was ever broken.
 */
export async function maybeConvertHeic(file: File): Promise<File> {
  if (!isHeic(file)) return file;
  try {
    const heic2any = (await import("heic2any")).default;
    const result = await heic2any({
      blob: file,
      toType: "image/jpeg",
      quality: 0.9,
    });
    // ``heic2any`` may return Blob or Blob[] depending on whether the
    // HEIC is single- or multi-image. We take the first frame either way.
    const blob = Array.isArray(result) ? result[0] : result;
    const newName = file.name.replace(/\.(heic|heif)$/i, ".jpg");
    return new File([blob], newName, { type: "image/jpeg" });
  } catch {
    // Backend still handles HEIC fine; only the preview was broken.
    return file;
  }
}
