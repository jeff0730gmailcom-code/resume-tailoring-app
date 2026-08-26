import { useEffect, useState } from "react";
import { ApiError, fetchResumeDownload, fetchResumePreviewPdf } from "../services/api";
import {
  preloadLocalDownloadsFolder,
  requestLocalDownloadsFolder,
  triggerBrowserDownload,
  writeResumeIntoFolder,
} from "../services/localFolderSave";
import type { DownloadSaveResult, TailoredResumeContent } from "../types";

interface ResumePreviewProps {
  resume: TailoredResumeContent | null;
  fileId: string | null;
  generatedFilename?: string | null;
}

export default function ResumePreview({
  resume,
  fileId,
  generatedFilename,
}: ResumePreviewProps) {
  const [previewObjectUrl, setPreviewObjectUrl] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [savingFormat, setSavingFormat] = useState<"pdf" | "docx" | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [lastSave, setLastSave] = useState<DownloadSaveResult | null>(null);

  useEffect(() => {
    preloadLocalDownloadsFolder();
  }, []);

  useEffect(() => {
    setLastSave(null);
    setSaveError(null);
  }, [resume, fileId]);

  useEffect(() => {
    if (!resume || !fileId) {
      setPreviewObjectUrl(null);
      setPreviewError(null);
      return;
    }

    let cancelled = false;
    let objectUrl: string | null = null;
    setIsPreviewLoading(true);
    setPreviewError(null);

    // Render the exact same PDF that /download would produce (see backend's
    // /preview/{file_id} route) so what's shown here is guaranteed to be
    // pixel-identical to the saved template - not a separate,
    // hand-rolled approximation of it.
    fetchResumePreviewPdf(fileId)
      .then((blob) => {
        if (cancelled) return;
        // A plain Blob carries no filename, so if the user uses the
        // browser's OWN PDF-viewer download button (inside the iframe,
        // not our "Download PDF" button below) it falls back to the
        // meaningless random blob: URL id (e.g. "8c5f3b01-...pdf").
        // Wrapping it in a File (which has a .name) before creating the
        // object URL makes Chromium/Edge's built-in viewer suggest the
        // real generated filename instead.
        const cvStem = resume.contact.name?.trim() || "resume";
        const filename = `${cvStem}.pdf`;
        const file = new File([blob], filename, { type: "application/pdf" });
        objectUrl = URL.createObjectURL(file);
        setPreviewObjectUrl(objectUrl);
      })
      .catch((err) => {
        if (!cancelled) {
          setPreviewError(err instanceof ApiError ? err.message : "Failed to render the resume preview.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsPreviewLoading(false);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // `resume` changes identity on every successful /tailor call, so this
    // re-renders the preview whenever new tailored content is generated.
  }, [resume, fileId, generatedFilename]);

  async function handleSave(format: "pdf" | "docx") {
    if (!fileId) return;
    setSavingFormat(format);
    setSaveError(null);
    try {
      // Ask for a local folder immediately (user gesture) while the file
      // is still being rendered on the server.
      const folderPromise = requestLocalDownloadsFolder();
      const filePromise = fetchResumeDownload(fileId, format);
      const [localRoot, file] = await Promise.all([folderPromise, filePromise]);
      const folderName = file.folderName || generatedFilename || "resume";
      const fileName = file.fileName || `${resume?.contact.name?.trim() || "resume"}.${format}`;

      if (localRoot) {
        await writeResumeIntoFolder(localRoot, folderName, fileName, file.blob);
        setLastSave({ folderName, fileName, method: "folder" });
      } else {
        triggerBrowserDownload(file.blob, fileName);
        setLastSave({ folderName, fileName, method: "file" });
      }
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Could not save the resume on this computer.");
    } finally {
      setSavingFormat(null);
    }
  }

  if (!resume) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-slate-400">
        Your tailored resume preview will appear here.
      </div>
    );
  }

  const cvName = resume.contact.name?.trim() || "resume";
  const folderHint = generatedFilename || "Name_stack_company";

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-100">
        {isPreviewLoading && (
          <div className="flex aspect-[1/1.414] w-full items-center justify-center text-sm text-slate-500">
            Rendering preview&hellip;
          </div>
        )}
        {!isPreviewLoading && previewError && (
          <div className="flex aspect-[1/1.414] w-full flex-col items-center justify-center gap-1 p-8 text-center">
            <p className="text-sm font-medium text-red-600">Couldn&apos;t render the preview</p>
            <p className="text-xs text-slate-500">{previewError}</p>
          </div>
        )}
        {!isPreviewLoading && !previewError && previewObjectUrl && (
          <iframe
            src={`${previewObjectUrl}#toolbar=0`}
            title="Tailored resume preview"
            className="aspect-[1/1.414] w-full border-0"
          />
        )}
      </div>

      <p className="text-xs text-slate-500">
        This preview is the exact PDF that will be saved — same template, fonts, and layout.
      </p>

      {fileId && (
        <div className="flex flex-col gap-1">
          <div className="flex gap-2">
            <button
              type="button"
              disabled={savingFormat !== null}
              onClick={() => void handleSave("pdf")}
              className="flex-1 rounded-lg bg-slate-900 px-4 py-3 text-center font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {savingFormat === "pdf" ? "Saving PDF…" : "Download PDF"}
            </button>
            <button
              type="button"
              disabled={savingFormat !== null}
              onClick={() => void handleSave("docx")}
              className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-3 text-center font-medium text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:bg-slate-100"
            >
              {savingFormat === "docx" ? "Saving DOCX…" : "Download DOCX"}
            </button>
          </div>
          <p className="text-center text-xs text-slate-500">
            Saves on this computer as{" "}
            <span className="font-medium text-slate-700">
              {folderHint}/{cvName}.pdf
            </span>{" "}
            or <span className="font-medium text-slate-700">.docx</span>. When asked, choose your{" "}
            <span className="font-medium text-slate-700">Downloads</span> folder.
          </p>
          {lastSave?.method === "folder" && (
            <p className="text-center text-xs text-emerald-700">
              Saved on this computer: {lastSave.folderName}/{lastSave.fileName}
            </p>
          )}
          {lastSave?.method === "file" && (
            <p className="text-center text-xs text-emerald-700">
              Saved {lastSave.fileName} to this computer — check your Downloads folder.
            </p>
          )}
          {saveError && <p className="text-center text-xs text-red-600">{saveError}</p>}
        </div>
      )}
    </div>
  );
}
