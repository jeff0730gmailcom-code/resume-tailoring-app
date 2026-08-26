/**
 * Save a resume onto the user's own computer (not the Railway container).
 *
 * Chrome/Edge can create a real subfolder via the File System Access API after
 * the user picks Downloads once. Other browsers fall back to a normal file
 * download into the browser's Downloads folder.
 */
const DB_NAME = "resume-tailor";
const STORE = "handles";
const HANDLE_KEY = "downloadsRoot";

type Writable = {
  write: (data: Blob) => Promise<void>;
  close: () => Promise<void>;
};

export type LocalDirectoryHandle = {
  getDirectoryHandle: (name: string, options: { create: boolean }) => Promise<LocalDirectoryHandle>;
  getFileHandle: (name: string, options: { create: boolean }) => Promise<{ createWritable: () => Promise<Writable> }>;
  queryPermission?: (options: { mode: "readwrite" }) => Promise<PermissionState>;
  requestPermission?: (options: { mode: "readwrite" }) => Promise<PermissionState>;
};

let memoryHandle: LocalDirectoryHandle | null = null;

function pickerWindow(): Window & {
  showDirectoryPicker?: (options?: {
    id?: string;
    mode?: "read" | "readwrite";
    startIn?: "downloads" | "desktop" | "documents";
  }) => Promise<LocalDirectoryHandle>;
} {
  return window;
}

function openHandleDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) {
        request.result.createObjectStore(STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function readStoredHandle(): Promise<LocalDirectoryHandle | null> {
  try {
    const db = await openHandleDb();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const req = tx.objectStore(STORE).get(HANDLE_KEY);
      req.onsuccess = () => resolve((req.result as LocalDirectoryHandle | undefined) ?? null);
      req.onerror = () => reject(req.error);
    });
  } catch {
    return null;
  }
}

async function storeHandle(handle: LocalDirectoryHandle): Promise<void> {
  try {
    const db = await openHandleDb();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(handle, HANDLE_KEY);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    // Persistence is optional; a later download can ask again.
  }
}

async function permissionGranted(handle: LocalDirectoryHandle): Promise<boolean> {
  if (!handle.queryPermission) return true;
  const current = await handle.queryPermission({ mode: "readwrite" });
  if (current === "granted") return true;
  if (!handle.requestPermission) return false;
  return (await handle.requestPermission({ mode: "readwrite" })) === "granted";
}

/**
 * Must be called from a click handler (before awaiting a slow network call)
 * so Chrome still treats it as a user gesture. Does not await IndexedDB
 * first — that would consume the gesture and block the folder picker.
 */
export async function requestLocalDownloadsFolder(): Promise<LocalDirectoryHandle | null> {
  const showPicker = pickerWindow().showDirectoryPicker;
  if (!showPicker) return null;

  if (memoryHandle && (await permissionGranted(memoryHandle))) return memoryHandle;

  try {
    const handle = await showPicker({
      id: "resume-tailor-downloads",
      mode: "readwrite",
      startIn: "downloads",
    });
    memoryHandle = handle;
    void storeHandle(handle);
    return handle;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return null;
    return null;
  }
}

/** Restore a previously granted Downloads handle after a page reload. */
export function preloadLocalDownloadsFolder(): void {
  void readStoredHandle().then(async (stored) => {
    if (!stored || memoryHandle) return;
    try {
      const state = stored.queryPermission
        ? await stored.queryPermission({ mode: "readwrite" })
        : "granted";
      if (state === "granted") memoryHandle = stored;
    } catch {
      // ignore
    }
  });
}

export async function writeResumeIntoFolder(
  root: LocalDirectoryHandle,
  folderName: string,
  fileName: string,
  blob: Blob,
): Promise<void> {
  const folder = await root.getDirectoryHandle(folderName, { create: true });
  const fileHandle = await folder.getFileHandle(fileName, { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(blob);
  await writable.close();
}

export function triggerBrowserDownload(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}
