import type { CoverLetterContent } from "../types";

interface CoverLetterPreviewProps {
  includeCoverLetter: boolean;
  coverLetter: CoverLetterContent | null;
  isGenerating: boolean;
  hasResume: boolean;
  lastGenerateIncludedLetter: boolean;
}

function formatLetterDate(): string {
  return new Date().toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function CoverLetterPreview({
  includeCoverLetter,
  coverLetter,
  isGenerating,
  hasResume,
  lastGenerateIncludedLetter,
}: CoverLetterPreviewProps) {
  if (!includeCoverLetter) {
    return null;
  }

  const showPlaceholder = !hasResume && !isGenerating;
  const showRetryHint = hasResume && !isGenerating && !coverLetter && !lastGenerateIncludedLetter;
  const showFailure = hasResume && !isGenerating && !coverLetter && lastGenerateIncludedLetter;

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-slate-800">4. Cover letter preview</h2>
      {showPlaceholder && (
        <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-slate-400">
          Your cover letter preview will appear here after you generate a tailored resume.
        </div>
      )}
      {isGenerating && (
        <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
          Writing cover letter from the job description and tailored resume&hellip;
        </div>
      )}
      {showRetryHint && (
        <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
          Generate again with &quot;Yes, generate a cover letter&quot; to write a letter from this job description and tailored resume.
        </div>
      )}
      {showFailure && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
          The resume was generated, but the cover letter could not be created. Generate again to retry.
        </div>
      )}
      {coverLetter && !isGenerating && (
        <article className="rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
          <header className="border-b border-slate-100 pb-4">
            <p className="text-lg font-semibold text-slate-900">{coverLetter.senderName}</p>
            <p className="mt-1 text-sm text-slate-500">
              {[coverLetter.senderLocation, coverLetter.senderEmail, coverLetter.senderPhone]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </header>
          <p className="mt-6 text-sm text-slate-600">{formatLetterDate()}</p>
          <p className="mt-4 text-sm text-slate-700">Hiring Team</p>
          <p className="text-sm font-medium text-slate-800">{coverLetter.recipientCompany}</p>
          <p className="mt-6 text-slate-800">{coverLetter.greeting}</p>
          <div className="mt-4 flex flex-col gap-4 text-[15px] leading-relaxed text-slate-700">
            {coverLetter.paragraphs.map((paragraph, index) => (
              <p key={index}>{paragraph}</p>
            ))}
          </div>
          <p className="mt-6 text-slate-800">{coverLetter.closing}</p>
          <p className="mt-6 font-medium text-slate-900">{coverLetter.senderName}</p>
          <p className="mt-8 text-xs text-slate-400">Preview only — this cover letter is not saved as a downloadable file.</p>
        </article>
      )}
    </section>
  );
}
