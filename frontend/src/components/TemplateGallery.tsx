import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  deleteResumeTemplate,
  fetchTemplates,
  setDefaultResumeTemplate,
  uploadResumeTemplate,
} from "../services/api";
import type { ResumeTemplateInfo } from "../types";
import Modal from "./Modal";

interface TemplateGalleryProps {
  selectedSlug: string | null;
  onSelect: (slug: string | null) => void;
  disabled?: boolean;
  /** Only show "required" validation error once the user has tried to submit. */
  showValidation?: boolean;
  /** Compact layout for the Create application left pane. */
  dense?: boolean;
}

export default function TemplateGallery({
  selectedSlug,
  onSelect,
  disabled,
  showValidation,
  dense = false,
}: TemplateGalleryProps) {
  const [templates, setTemplates] = useState<ResumeTemplateInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lightboxTemplate, setLightboxTemplate] = useState<ResumeTemplateInfo | null>(null);
  const [busySlug, setBusySlug] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const didAutoSelect = useRef(false);

  const selectedTemplate = useMemo(
    () => templates.find((t) => t.slug === selectedSlug) ?? null,
    [templates, selectedSlug]
  );

  async function loadTemplates() {
    setIsLoading(true);
    try {
      const result = await fetchTemplates();
      setTemplates(result);
      setError(null);
      if (!didAutoSelect.current) {
        const preferred = result.find((t) => t.isDefault) ?? result[0];
        if (preferred && !selectedSlug) {
          onSelect(preferred.slug);
        }
        didAutoSelect.current = true;
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load resume templates.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on mount; selection callback is stable enough
  }, []);

  async function handleUpload(file: File | undefined) {
    if (!file || disabled) return;
    setIsUploading(true);
    setError(null);
    try {
      const created = await uploadResumeTemplate(file);
      setTemplates((current) => {
        const next = created.isDefault
          ? current.map((t) => ({ ...t, isDefault: false })).concat(created)
          : current.concat(created);
        return next;
      });
      onSelect(created.slug);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upload that template.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleSetDefault(slug: string) {
    setBusySlug(slug);
    setError(null);
    try {
      const updated = await setDefaultResumeTemplate(slug);
      setTemplates((current) =>
        current.map((t) => ({
          ...t,
          isDefault: t.slug === updated.slug,
        }))
      );
      onSelect(updated.slug);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not set default template.");
    } finally {
      setBusySlug(null);
    }
  }

  async function handleDelete(template: ResumeTemplateInfo) {
    if (template.isBuiltin) return;
    if (!window.confirm(`Remove template “${template.name}”?`)) return;
    setBusySlug(template.slug);
    setError(null);
    try {
      await deleteResumeTemplate(template.slug);
      const remaining = templates.filter((t) => t.slug !== template.slug);
      setTemplates(remaining);
      if (selectedSlug === template.slug) {
        const next = remaining.find((t) => t.isDefault) ?? remaining[0];
        onSelect(next?.slug ?? null);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete that template.");
    } finally {
      setBusySlug(null);
    }
  }

  const selectionMissing = showValidation && !selectedSlug;

  if (isLoading) {
    return <p className="text-sm text-slate-500">Loading templates&hellip;</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="hidden"
          disabled={disabled || isUploading}
          onChange={(event) => void handleUpload(event.target.files?.[0])}
        />
        <button
          type="button"
          disabled={disabled || isUploading}
          onClick={() => fileInputRef.current?.click()}
          className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {isUploading ? "Uploading…" : "Upload template (PDF/DOCX)"}
        </button>
        <p className="text-xs text-slate-500">Only your templates appear here. Upload a sample CV to add one.</p>
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {templates.length === 0 ? (
        <p className="text-sm text-slate-500">No templates yet. Upload a PDF or DOCX sample CV to get started.</p>
      ) : (
        <div
          className={
            dense
              ? "flex flex-col gap-2"
              : "grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(220px,320px)]"
          }
        >
          <div
            className={
              dense
                ? "grid grid-cols-3 gap-1.5 sm:grid-cols-4"
                : "grid grid-cols-2 gap-3 sm:grid-cols-3"
            }
          >
            {templates.map((template) => {
              const isSelected = template.slug === selectedSlug;
              return (
                <div
                  key={template.slug}
                  className={`flex flex-col overflow-hidden rounded-md border bg-white ${
                    isSelected ? "border-indigo-500 ring-1 ring-indigo-200" : "border-slate-200"
                  }`}
                >
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onSelect(template.slug)}
                    onDoubleClick={() => setLightboxTemplate(template)}
                    className="flex flex-col text-left disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <div
                      className={`w-full overflow-hidden bg-slate-100 ${
                        dense ? "aspect-[3/2.6] max-h-28" : "aspect-[3/4]"
                      }`}
                    >
                      <img
                        src={template.thumbnailUrl}
                        alt={`${template.name} resume template preview`}
                        className="h-full w-full object-cover object-top"
                        loading="lazy"
                      />
                    </div>
                    <div className={dense ? "px-1.5 py-1" : "p-2"}>
                      <div className="flex min-w-0 items-center gap-1">
                        <p
                          className={`truncate font-medium text-slate-800 ${
                            dense ? "text-[11px] leading-tight" : "text-sm"
                          }`}
                        >
                          {template.name}
                        </p>
                        {template.isDefault ? (
                          <span className="shrink-0 rounded bg-emerald-50 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-emerald-700">
                            Default
                          </span>
                        ) : null}
                      </div>
                      {template.description && !dense ? (
                        <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{template.description}</p>
                      ) : null}
                    </div>
                  </button>
                  <div
                    className={`flex flex-wrap gap-0.5 border-t border-slate-100 ${
                      dense ? "px-1 py-0.5" : "px-2 py-1.5"
                    }`}
                  >
                    {!template.isDefault ? (
                      <button
                        type="button"
                        disabled={disabled || busySlug === template.slug}
                        onClick={() => void handleSetDefault(template.slug)}
                        className={`rounded font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50 ${
                          dense ? "px-1 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]"
                        }`}
                      >
                        Set default
                      </button>
                    ) : null}
                    {!template.isBuiltin ? (
                      <button
                        type="button"
                        disabled={disabled || busySlug === template.slug}
                        onClick={() => void handleDelete(template)}
                        className={`rounded font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 ${
                          dense ? "px-1 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]"
                        }`}
                      >
                        Delete
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>

          {!dense ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Preview</p>
              {selectedTemplate ? (
                <button
                  type="button"
                  onClick={() => setLightboxTemplate(selectedTemplate)}
                  className="group flex w-full flex-col items-stretch text-left"
                >
                  <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
                    <img
                      src={selectedTemplate.thumbnailUrl}
                      alt={`${selectedTemplate.name} large preview`}
                      className="mx-auto max-h-[28rem] w-full object-contain object-top"
                    />
                  </div>
                  <div className="mt-2">
                    <p className="text-sm font-semibold text-slate-900">{selectedTemplate.name}</p>
                    {selectedTemplate.description ? (
                      <p className="mt-0.5 text-xs text-slate-500">{selectedTemplate.description}</p>
                    ) : null}
                    <p className="mt-1 text-[11px] text-indigo-600 group-hover:underline">Click to enlarge</p>
                  </div>
                </button>
              ) : (
                <div className="flex min-h-[16rem] items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white px-4 text-center">
                  <p className="text-sm text-slate-500">Select a template to preview it here.</p>
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}
      {selectionMissing && <p className="text-xs text-red-600">Please select a resume template.</p>}

      {lightboxTemplate && (
        <Modal onClose={() => setLightboxTemplate(null)}>
          <div className="flex flex-col items-center gap-3">
            <img
              src={lightboxTemplate.thumbnailUrl}
              alt={`${lightboxTemplate.name} resume template preview`}
              className="max-h-[85vh] max-w-[90vw] rounded-lg object-contain shadow-2xl"
            />
            <div className="text-center text-white">
              <p className="font-medium">{lightboxTemplate.name}</p>
              {lightboxTemplate.description && (
                <p className="mt-0.5 text-sm text-slate-300">{lightboxTemplate.description}</p>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
