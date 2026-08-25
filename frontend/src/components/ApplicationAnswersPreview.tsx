import type { ApplicationAnswerItem } from "../types";

interface ApplicationAnswersPreviewProps {
  sectionNumber: number;
  questions: string[];
  answers: ApplicationAnswerItem[];
  isGenerating: boolean;
  hasResume: boolean;
  lastGenerateHadQuestions: boolean;
}

export default function ApplicationAnswersPreview({
  sectionNumber,
  questions,
  answers,
  isGenerating,
  hasResume,
  lastGenerateHadQuestions,
}: ApplicationAnswersPreviewProps) {
  if (questions.length === 0 && answers.length === 0) {
    return null;
  }

  const showPlaceholder = !hasResume && !isGenerating && answers.length === 0;
  const showRetryHint =
    hasResume && !isGenerating && answers.length === 0 && questions.length > 0 && !lastGenerateHadQuestions;
  const showFailure =
    hasResume && !isGenerating && answers.length === 0 && lastGenerateHadQuestions;

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-slate-800">{sectionNumber}. Application answers</h2>
      {showPlaceholder && (
        <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-slate-400">
          Answers to your application questions will appear here after you generate.
        </div>
      )}
      {isGenerating && questions.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
          Writing answers from the job description and tailored resume&hellip;
        </div>
      )}
      {showRetryHint && (
        <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
          Generate again to write answers for the questions you added.
        </div>
      )}
      {showFailure && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
          The resume was generated, but answers to the application questions could not be created. Generate again to retry.
        </div>
      )}
      {answers.length > 0 && !isGenerating && (
        <div className="flex flex-col gap-4">
          {answers.map((item, index) => (
            <article key={`${index}-${item.question.slice(0, 24)}`} className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
              <p className="text-sm font-semibold text-slate-900">
                {index + 1}. {item.question}
              </p>
              <p className="mt-3 whitespace-pre-wrap text-[15px] leading-relaxed text-slate-700">{item.answer}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
