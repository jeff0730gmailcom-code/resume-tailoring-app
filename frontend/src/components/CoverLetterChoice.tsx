interface CoverLetterChoiceProps {
  value: boolean;
  onChange: (needsCoverLetter: boolean) => void;
  disabled?: boolean;
}

export default function CoverLetterChoice({ value, onChange, disabled }: CoverLetterChoiceProps) {
  return (
    <fieldset className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4" disabled={disabled}>
      <legend className="px-1 font-medium text-slate-700">Need a cover letter?</legend>
      <p className="text-sm text-slate-500">
        Optional. If yes, a letter is written from this job description and the tailored resume, then shown as a preview only (no download file).
      </p>
      <div className="flex flex-col gap-2 sm:flex-row sm:gap-6">
        <label className="flex cursor-pointer items-center gap-2 text-slate-800">
          <input
            type="radio"
            name="need-cover-letter"
            value="yes"
            checked={value === true}
            onChange={() => onChange(true)}
            className="h-4 w-4 accent-indigo-600"
          />
          Yes, generate a cover letter
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-slate-800">
          <input
            type="radio"
            name="need-cover-letter"
            value="no"
            checked={value === false}
            onChange={() => onChange(false)}
            className="h-4 w-4 accent-indigo-600"
          />
          No, resume only
        </label>
      </div>
    </fieldset>
  );
}
