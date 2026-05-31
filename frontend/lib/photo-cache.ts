// Caches the most-recent try-on photo as a Blob in IndexedDB so the
// shopper doesn't re-upload every time they click "Try-on" on a product.
// IndexedDB is preferred over localStorage because photos can be a few
// megabytes; localStorage tops out around 5MB total per origin and stores
// strings only.
//
// Single-record store keyed by "last_photo". Overwritten on each upload.

const DB_NAME = "atelier";
const STORE_NAME = "photo_cache";
const RECORD_KEY = "last_photo";
const DB_VERSION = 1;

type CachedPhoto = {
  blob: Blob;
  name: string;
  content_type: string;
  cached_at: number;
};

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB not available"));
      return;
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("idb open failed"));
  });
}

export async function savePhoto(file: File): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const record: CachedPhoto = {
      blob: file,
      name: file.name,
      content_type: file.type || "image/jpeg",
      cached_at: Date.now(),
    };
    tx.objectStore(STORE_NAME).put(record, RECORD_KEY);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error ?? new Error("idb put failed"));
    };
  });
}

export async function loadPhoto(): Promise<File | null> {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const getReq = tx.objectStore(STORE_NAME).get(RECORD_KEY);
      getReq.onsuccess = () => {
        db.close();
        const record = getReq.result as CachedPhoto | undefined;
        if (!record) {
          resolve(null);
          return;
        }
        resolve(
          new File([record.blob], record.name, { type: record.content_type }),
        );
      };
      getReq.onerror = () => {
        db.close();
        reject(getReq.error ?? new Error("idb get failed"));
      };
    });
  } catch {
    return null;
  }
}

export async function hasCachedPhoto(): Promise<boolean> {
  const f = await loadPhoto();
  return f !== null;
}

export async function clearPhoto(): Promise<void> {
  try {
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete(RECORD_KEY);
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
      tx.onerror = () => {
        db.close();
        reject(tx.error ?? new Error("idb delete failed"));
      };
    });
  } catch {
    // ignore — if there's no DB there's nothing to clear
  }
}
