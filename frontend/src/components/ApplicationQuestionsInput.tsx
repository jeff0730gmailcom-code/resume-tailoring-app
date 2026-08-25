import { useState } from "react";

const MAX_QUESTIONS = 12;

interface ApplicationQuestionsInputProps {
  questions: string[];
  onChange: (questions: string[]) => void;
  disabled?: boolean;
}

export default function ApplicationQuestionsInput({
  questions,
  onChange,
  disabled,
}: ApplicationQuestionsInputProps) {
  const [draft, setDraft] = useState("");

  function addQuestion() {
    const text = draft.trim();
    if (!text || disabled) return;
    const exists = questions.some((q) => q.toLowerCase() === text.toLowerCase());
    if (exists || questions.length >= MAX_QUESTIONS) {
      setDraft("");
      return;
    }
    onChange([...questions, text]);
    setDraft("");
  }

  function removeQuestion(index: number) {
    onChange(questions.filter((_, i) => i !== index));
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4">
      <div>
        <p className="font-medium text-slate-700">Application questions</p>
        <p className="mt-1 text-sm text-slate-500">
          Optional. Add employer screening questions one at a time. Answers are written from your tailored resume after you generate.
        </p>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="text"
          value={draft}
          disabled={disabled || questions.length >= MAX_QUESTIONS}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addQuestion();
            }
          }}
          placeholder="e.g. Why do you want this role?"
          className="min-w-0 flex-1 rounded-lg border border-slate-300 p-3 text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50 disabled:text-slate-500"
        />
        <button
          type="button"
          disabled={disabled || draft.trim().length === 0 || questions.length >= MAX_QUESTIONS}
          onClick={addQuestion}
          className="rounded-lg bg-slate-900 px-4 py-3 font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          Add question
        </button>
      </div>
      {questions.length >= MAX_QUESTIONS && (
        <p className="text-xs text-slate-500">You can add up to {MAX_QUESTIONS} questions.</p>
      )}
      {questions.length > 0 && (
        <ol className="flex flex-col gap-2">
          {questions.map((question, index) => (
            <li
              key={`${index}-${question.slice(0, 24)}`}
              className="flex items-start gap-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
            >
              <span className="mt-0.5 text-xs font-medium text-slate-400">{index + 1}.</span>
              <span className="flex-1 text-sm text-slate-800">{question}</span>
              <button
                type="button"
                disabled={disabled}
                onClick={() => removeQuestion(index)}
                className="text-xs font-medium text-slate-500 hover:text-red-600 disabled:text-slate-300"
              >
                Remove
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
