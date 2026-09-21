import { useRef, useState } from "react";
import type { DragEvent } from "react";

interface CvUploadProps {
  onFileSelected: (file: File) => void;
  /** When set, user can pick several files at once; each is passed to onFileSelected. */
  onFilesSelected?: (files: File[]) => void;
  multiple?: boolean;
  fileName?: string | null;
  isUploading?: boolean;
  error?: string | null;
  /** Override the empty-state hint (e.g. “Add another master CV”). */
  emptyLabel?: string;
}

const ACCEPTED_EXTENSIONS = [".pdf", ".doc", ".docx"];

function hasAcceptedExtension(fileName: string): boolean {
  const lower = fileName.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export default function CvUpload({
  onFileSelected,
  onFilesSelected,
  multiple = false,
  fileName,
  isUploading,
  error,
  emptyLabel,
}: CvUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  function handleFiles(files: FileList | null) {
    if (!files?.length) return;
    const accepted = Array.from(files).filter((file) => hasAcceptedExtension(file.name));
    if (!accepted.length) return;
    if (multiple || onFilesSelected) {
      (onFilesSelected ?? ((list) => list.forEach(onFileSelected)))(accepted);
    } else {
      onFileSelected(accepted[0]);
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    handleFiles(event.dataTransfer.files);
  }

  return (
    <div>
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`cursor-pointer rounded-lg border-2 border-dashed p-5 text-center transition-colors ${
          isDragging ? "border-indigo-400 bg-indigo-50" : "border-slate-300 hover:border-indigo-300"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="hidden"
          multiple={multiple}
          onChange={(event) => {
            handleFiles(event.target.files);
            event.target.value = "";
          }}
        />
        {isUploading ? (
          <p className="font-medium text-slate-600">Uploading &amp; extracting your CV&hellip;</p>
        ) : fileName && !multiple ? (
          <>
            <p className="font-medium text-slate-800">{fileName}</p>
            <p className="text-sm text-slate-500">Click or drop a file to replace it</p>
          </>
        ) : (
          <>
            <p className="font-medium text-slate-700">
              {emptyLabel ?? (multiple ? "Click to upload or drag and drop" : "Click to upload or drag and drop")}
            </p>
            <p className="text-sm text-slate-500">
              {multiple ? "PDF, DOC, or DOCX — one or more files, up to 10MB each" : "PDF, DOC, or DOCX, up to 10MB"}
            </p>
          </>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
