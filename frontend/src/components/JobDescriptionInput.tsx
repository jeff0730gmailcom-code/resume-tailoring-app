interface JobDescriptionInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export default function JobDescriptionInput({ value, onChange, disabled }: JobDescriptionInputProps) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor="job-description" className="font-medium text-slate-700">
        Job description
      </label>
      <textarea
        id="job-description"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Paste the job description here"
        className="min-h-[160px] rounded-lg border border-slate-300 p-3 text-slate-800 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50 disabled:text-slate-500"
      />
    </div>
  );
}
