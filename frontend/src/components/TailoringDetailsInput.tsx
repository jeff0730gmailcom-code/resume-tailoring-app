interface TailoringDetailsInputProps {
  mainStack: string;
  onMainStackChange: (value: string) => void;
  companyName: string;
  onCompanyNameChange: (value: string) => void;
  jobLink: string;
  onJobLinkChange: (value: string) => void;
  disabled?: boolean;
  /** Only show "required" validation errors once the user has tried to submit. */
  showValidation?: boolean;
}

function looksLikeJobLink(value: string): boolean {
  const link = value.trim();
  return link.startsWith("http://") || link.startsWith("https://");
}

export default function TailoringDetailsInput({
  mainStack,
  onMainStackChange,
  companyName,
  onCompanyNameChange,
  jobLink,
  onJobLinkChange,
  disabled,
  showValidation,
}: TailoringDetailsInputProps) {
  const mainStackMissing = showValidation && mainStack.trim().length === 0;
  const companyNameMissing = showValidation && companyName.trim().length === 0;
  const jobLinkMissing = showValidation && !looksLikeJobLink(jobLink);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <label htmlFor="main-stack" className="font-medium text-slate-700">
            Main Technology Stack <span className="text-red-500">*</span>
          </label>
          <input
            id="main-stack"
            type="text"
            value={mainStack}
            disabled={disabled}
            onChange={(event) => onMainStackChange(event.target.value)}
            placeholder="e.g. Node.js, Python, React"
            className={`rounded-lg border p-3 text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50 disabled:text-slate-500 ${
              mainStackMissing ? "border-red-400 focus:border-red-400" : "border-slate-300 focus:border-indigo-400"
            }`}
          />
          {mainStackMissing && <p className="text-xs text-red-600">Main technology stack cannot be empty.</p>}
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="company-name" className="font-medium text-slate-700">
            Target Company Name <span className="text-red-500">*</span>
          </label>
          <input
            id="company-name"
            type="text"
            value={companyName}
            disabled={disabled}
            onChange={(event) => onCompanyNameChange(event.target.value)}
            placeholder="e.g. Sequencer, Google, Amazon"
            className={`rounded-lg border p-3 text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50 disabled:text-slate-500 ${
              companyNameMissing ? "border-red-400 focus:border-red-400" : "border-slate-300 focus:border-indigo-400"
            }`}
          />
          {companyNameMissing && <p className="text-xs text-red-600">Target company name cannot be empty.</p>}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="job-link" className="font-medium text-slate-700">
          Job description link <span className="text-red-500">*</span>
        </label>
        <input
          id="job-link"
          type="url"
          value={jobLink}
          disabled={disabled}
          onChange={(event) => onJobLinkChange(event.target.value)}
          placeholder="https://..."
          className={`rounded-lg border p-3 text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50 disabled:text-slate-500 ${
            jobLinkMissing ? "border-red-400 focus:border-red-400" : "border-slate-300 focus:border-indigo-400"
          }`}
        />
        {jobLinkMissing && <p className="text-xs text-red-600">Enter the full job posting URL (http:// or https://).</p>}
      </div>
    </div>
  );
}
