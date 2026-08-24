import { useRef, useState } from "react";
import type { DragEvent } from "react";

interface CvUploadProps {
  onFileSelected: (file: File) => void;
  fileName?: string | null;
  isUploading?: boolean;
  error?: string | null;
}

const ACCEPTED_EXTENSIONS = [".pdf", ".doc", ".docx"];

function hasAcceptedExtension(fileName: string): boolean {
  const lower = fileName.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export default function CvUpload({ onFileSelected, fileName, isUploading, error }: CvUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    if (!hasAcceptedExtension(file.name)) return;
    onFileSelected(file);
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
        className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
          isDragging ? "border-indigo-400 bg-indigo-50" : "border-slate-300 hover:border-indigo-300"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="hidden"
          onChange={(event) => handleFiles(event.target.files)}
        />
        {isUploading ? (
          <p className="font-medium text-slate-600">Uploading &amp; extracting your CV&hellip;</p>
        ) : fileName ? (
          <>
            <p className="font-medium text-slate-800">{fileName}</p>
            <p className="text-sm text-slate-500">Click or drop a file to replace it</p>
          </>
        ) : (
          <>
            <p className="font-medium text-slate-700">Click to upload or drag and drop</p>
            <p className="text-sm text-slate-500">PDF, DOC, or DOCX, up to 10MB</p>
          </>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
