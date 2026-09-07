interface WaitingApprovalProps {
  name: string;
  onSignOut: () => void;
}

export default function WaitingApproval({ name, onSignOut }: WaitingApprovalProps) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brand">Resume Tailor</p>
          <button
            type="button"
            onClick={onSignOut}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-lg px-4 py-20 text-center">
        <h2 className="text-3xl font-bold text-slate-900">Thank you, {name}</h2>
        <p className="mt-4 text-slate-600">
          Your account is ready. An administrator must allow you before you can tailor resumes.
        </p>
        <p className="mt-6 text-sm text-slate-500">Sign in again after you have been allowed.</p>
      </main>
    </div>
  );
}
