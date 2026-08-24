import { useEffect, useState } from "react";
import CvUpload from "./components/CvUpload";
import JobDescriptionInput from "./components/JobDescriptionInput";
import ResumePreview from "./components/ResumePreview";
import TailoringDetailsInput from "./components/TailoringDetailsInput";
import TemplateGallery from "./components/TemplateGallery";
import { ApiError, checkApiHealth, getDownloadUrl, tailorResume, uploadCv } from "./services/api";
import type { TailoredResumeContent, UploadedCv } from "./types";

function App() {
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");

  const [cv, setCv] = useState<UploadedCv | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [jobDescription, setJobDescription] = useState("");
  const [mainStack, setMainStack] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [selectedTemplateSlug, setSelectedTemplateSlug] = useState<string | null>(null);
  const [attemptedGenerate, setAttemptedGenerate] = useState(false);

  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [resume, setResume] = useState<TailoredResumeContent | null>(null);
  const [generatedFilename, setGeneratedFilename] = useState<string | null>(null);

  useEffect(() => {
    checkApiHealth()
      .then(() => setApiStatus("online"))
      .catch(() => setApiStatus("offline"));
  }, []);

  async function handleFileSelected(file: File) {
    setIsUploading(true);
    setUploadError(null);
    setResume(null);
    setGeneratedFilename(null);
    try {
      const uploaded = await uploadCv(file);
      setCv(uploaded);
    } catch (err) {
      setCv(null);
      setUploadError(err instanceof ApiError ? err.message : "Failed to upload CV. Please try again.");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleGenerate() {
    setAttemptedGenerate(true);
    if (!cv || !mainStack.trim() || !companyName.trim() || !selectedTemplateSlug) return;
    setIsGenerating(true);
    setGenerateError(null);
    try {
      // ATS matching/scoring happens entirely on the backend (see
      // app/services/ats_scorer.py) and is intentionally never surfaced in
      // the UI - result.atsMatch is available in the API response for
      // backend/internal use but is deliberately not read here.
      const result = await tailorResume(
        cv.fileId,
        jobDescription,
        mainStack.trim(),
        companyName.trim(),
        selectedTemplateSlug
      );
      setResume(result.resume);
      setGeneratedFilename(result.generatedFilename);
    } catch (err) {
      setGenerateError(
        err instanceof ApiError ? err.message : "Failed to generate a tailored resume. Please try again."
      );
    } finally {
      setIsGenerating(false);
    }
  }

  const canGenerate =
    Boolean(cv) &&
    jobDescription.trim().length > 0 &&
    mainStack.trim().length > 0 &&
    companyName.trim().length > 0 &&
    Boolean(selectedTemplateSlug) &&
    !isGenerating &&
    !isUploading;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-4">
          <h1 className="text-xl font-semibold text-slate-900">Resume Tailor AI</h1>
          <span
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              apiStatus === "online"
                ? "bg-green-100 text-green-700"
                : apiStatus === "offline"
                  ? "bg-red-100 text-red-700"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            API: {apiStatus}
          </span>
        </div>
      </header>

      <main className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-10">
        <section className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold text-slate-800">1. Upload master CV</h2>
          <CvUpload onFileSelected={handleFileSelected} fileName={cv?.fileName} isUploading={isUploading} error={uploadError} />
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold text-slate-800">2. Paste job description</h2>
          <JobDescriptionInput value={jobDescription} onChange={setJobDescription} />
          <TailoringDetailsInput
            mainStack={mainStack}
            onMainStackChange={setMainStack}
            companyName={companyName}
            onCompanyNameChange={setCompanyName}
            showValidation={attemptedGenerate}
          />
          <div className="flex flex-col gap-2">
            <span className="font-medium text-slate-700">
              Resume Template <span className="text-red-500">*</span>
            </span>
            <TemplateGallery
              selectedSlug={selectedTemplateSlug}
              onSelect={setSelectedTemplateSlug}
              showValidation={attemptedGenerate}
            />
          </div>
        </section>

        <section className="flex flex-col gap-2">
          <button
            disabled={!canGenerate}
            onClick={handleGenerate}
            className="w-full rounded-lg bg-indigo-600 px-4 py-3 font-medium text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300"
          >
            {isGenerating ? "Generating…" : "Generate Tailored Resume"}
          </button>
          {generateError && <p className="text-sm text-red-600">{generateError}</p>}
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold text-slate-800">3. Preview &amp; download</h2>
          <ResumePreview
            resume={resume}
            fileId={cv?.fileId ?? null}
            pdfDownloadUrl={resume && cv ? getDownloadUrl(cv.fileId, "pdf") : null}
            docxDownloadUrl={resume && cv ? getDownloadUrl(cv.fileId, "docx") : null}
            generatedFilename={generatedFilename}
          />
        </section>
      </main>
    </div>
  );
}

export default App;
