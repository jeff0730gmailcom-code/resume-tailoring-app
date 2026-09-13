import { useEffect, useState } from "react";
import { ApiError, downloadResume, fetchResumePreviewPdf } from "../services/api";
import type { DownloadSaveResult, TailoredResumeContent } from "../types";

interface ResumePreviewProps {
  resume: TailoredResumeContent | null;
  fileId: string | null;
  generatedFilename?: string | null;
  /** Grow the PDF iframe to fill the parent pane (Create application desktop layout). */
  fillHeight?: boolean;
}

export default function ResumePreview({
  resume,
  fileId,
  generatedFilename,
  fillHeight = false,
}: ResumePreviewProps) {
  const [previewObjectUrl, setPreviewObjectUrl] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [savingFormat, setSavingFormat] = useState<"pdf" | "docx" | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [lastSave, setLastSave] = useState<DownloadSaveResult | null>(null);

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
      const result = await downloadResume(fileId, format);
      setLastSave(result);
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Could not save the resume to Downloads.");
    } finally {
      setSavingFormat(null);
    }
  }

  const frameBoxClass = fillHeight
    ? "flex min-h-[28rem] flex-1 flex-col lg:min-h-0"
    : "aspect-[1/1.414] w-full";
  const frameClass = fillHeight
    ? "h-full min-h-[28rem] w-full flex-1 border-0 lg:min-h-0"
    : "aspect-[1/1.414] w-full border-0";

  if (!resume) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-slate-400 ${
          fillHeight ? "min-h-[28rem] flex-1 lg:min-h-0" : ""
        }`}
      >
        Your tailored resume preview will appear here.
      </div>
    );
  }

  const cvName = resume.contact.name?.trim() || "resume";
  const folderHint = generatedFilename || "Name_stack_company";

  return (
    <div className={`flex flex-col gap-3 ${fillHeight ? "min-h-0 flex-1" : ""}`}>
      <div className={`overflow-hidden rounded-lg border border-slate-200 bg-slate-100 ${fillHeight ? "flex min-h-0 flex-1 flex-col" : ""}`}>
        {isPreviewLoading && (
          <div className={`flex items-center justify-center text-sm text-slate-500 ${frameBoxClass}`}>
            Rendering preview&hellip;
          </div>
        )}
        {!isPreviewLoading && previewError && (
          <div className={`flex flex-col items-center justify-center gap-1 p-8 text-center ${frameBoxClass}`}>
            <p className="text-sm font-medium text-red-600">Couldn&apos;t render the preview</p>
            <p className="text-xs text-slate-500">{previewError}</p>
          </div>
        )}
        {!isPreviewLoading && !previewError && previewObjectUrl && (
          <iframe
            src={`${previewObjectUrl}#toolbar=0`}
            title="Tailored resume preview"
            className={frameClass}
          />
        )}
      </div>

      <p className="shrink-0 text-xs text-slate-500">
        This preview is the exact PDF that will be saved — same template, fonts, and layout.
      </p>

      {fileId && (
        <div className="flex shrink-0 flex-col gap-1">
          <div className="flex gap-2">
            <button
              type="button"
              disabled={savingFormat !== null}
              onClick={() => void handleSave("pdf")}
              className="flex-1 rounded-lg bg-brand px-4 py-3 text-center font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-400"
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
            Downloads a zip{" "}
            <span className="font-medium text-slate-700">{folderHint}.zip</span> containing{" "}
            <span className="font-medium text-slate-700">
              {folderHint}/{cvName}.pdf
            </span>{" "}
            or <span className="font-medium text-slate-700">.docx</span>
          </p>
          {lastSave && (
            <p className="text-center text-xs text-emerald-700">Saved {lastSave.zipName} to your Downloads folder.</p>
          )}
          {saveError && <p className="text-center text-xs text-red-600">{saveError}</p>}
        </div>
      )}
    </div>
  );
}
