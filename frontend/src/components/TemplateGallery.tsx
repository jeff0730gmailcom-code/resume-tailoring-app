import { useEffect, useState } from "react";
import { ApiError, fetchTemplates } from "../services/api";
import type { ResumeTemplateInfo } from "../types";
import Modal from "./Modal";

interface TemplateGalleryProps {
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
  disabled?: boolean;
  /** Only show "required" validation error once the user has tried to submit. */
  showValidation?: boolean;
}

export default function TemplateGallery({ selectedSlug, onSelect, disabled, showValidation }: TemplateGalleryProps) {
  const [templates, setTemplates] = useState<ResumeTemplateInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewTemplate, setPreviewTemplate] = useState<ResumeTemplateInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchTemplates()
      .then((result) => {
        if (!cancelled) setTemplates(result);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load resume templates.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectionMissing = showValidation && !selectedSlug;

  if (isLoading) {
    return <p className="text-sm text-slate-500">Loading templates&hellip;</p>;
  }

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  return (
    <div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-5">
        {templates.map((template) => {
          const isSelected = template.slug === selectedSlug;
          return (
            <button
              key={template.slug}
              type="button"
              disabled={disabled}
              onClick={() => {
                onSelect(template.slug);
                setPreviewTemplate(template);
              }}
              className={`flex flex-col overflow-hidden rounded-lg border-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                isSelected ? "border-indigo-500 ring-2 ring-indigo-200" : "border-slate-200 hover:border-indigo-300"
              }`}
            >
              <div className="aspect-[3/4] w-full overflow-hidden bg-slate-100">
                <img
                  src={template.thumbnailUrl}
                  alt={`${template.name} resume template preview`}
                  className="h-full w-full object-cover object-top"
                  loading="lazy"
                />
              </div>
              <div className="p-2">
                <p className="text-sm font-medium text-slate-800">{template.name}</p>
                {template.description && (
                  <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{template.description}</p>
                )}
              </div>
            </button>
          );
        })}
      </div>
      {selectionMissing && <p className="mt-2 text-xs text-red-600">Please select a resume template.</p>}

      {previewTemplate && (
        <Modal onClose={() => setPreviewTemplate(null)}>
          <div className="flex flex-col items-center gap-3">
            <img
              src={previewTemplate.thumbnailUrl}
              alt={`${previewTemplate.name} resume template preview`}
              className="max-h-[85vh] max-w-[90vw] rounded-lg object-contain shadow-2xl"
            />
            <div className="text-center text-white">
              <p className="font-medium">{previewTemplate.name}</p>
              {previewTemplate.description && (
                <p className="mt-0.5 text-sm text-slate-300">{previewTemplate.description}</p>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
