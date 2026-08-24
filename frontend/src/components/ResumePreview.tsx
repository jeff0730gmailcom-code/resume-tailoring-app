import { useEffect, useState } from "react";
import { ApiError, fetchResumePreviewPdf } from "../services/api";
import type { TailoredResumeContent } from "../types";

interface ResumePreviewProps {
  resume: TailoredResumeContent | null;
  fileId: string | null;
  pdfDownloadUrl: string | null;
  docxDownloadUrl: string | null;
  generatedFilename?: string | null;
}

export default function ResumePreview({
  resume,
  fileId,
  pdfDownloadUrl,
  docxDownloadUrl,
  generatedFilename,
}: ResumePreviewProps) {
  const [previewObjectUrl, setPreviewObjectUrl] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

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
    // pixel-identical to the downloaded template - not a separate,
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
        const filename = generatedFilename ? `${generatedFilename}.pdf` : "resume.pdf";
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

  if (!resume) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-slate-400">
        Your tailored resume preview will appear here.
      </div>
    );
  }

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
            src={previewObjectUrl}
            title="Tailored resume preview"
            className="aspect-[1/1.414] w-full border-0"
          />
        )}
      </div>

      <p className="text-xs text-slate-500">
        This preview is the exact PDF you&apos;ll download - same template, fonts, and layout.
      </p>

      {(pdfDownloadUrl || docxDownloadUrl) && (
        <div className="flex flex-col gap-1">
          <div className="flex gap-2">
            {pdfDownloadUrl && (
              <a
                href={pdfDownloadUrl}
                className="flex-1 rounded-lg bg-slate-900 px-4 py-3 text-center font-medium text-white hover:bg-slate-800"
              >
                Download PDF
              </a>
            )}
            {docxDownloadUrl && (
              <a
                href={docxDownloadUrl}
                className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-3 text-center font-medium text-slate-800 hover:bg-slate-50"
              >
                Download DOCX
              </a>
            )}
          </div>
          {generatedFilename && (
            <p className="text-center text-xs text-slate-500">
              Will download as <span className="font-medium text-slate-700">{generatedFilename}.pdf</span> /{" "}
              <span className="font-medium text-slate-700">.docx</span>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
