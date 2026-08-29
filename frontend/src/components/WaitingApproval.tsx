interface WaitingApprovalProps {
  name: string;
  onSignOut: () => void;
}

export default function WaitingApproval({ name, onSignOut }: WaitingApprovalProps) {
  return (
    <div className="suit-pinstripe min-h-screen text-navy">
      <header className="border-b-2 border-gold bg-navy">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-4">
          <div>
            <p className="font-sans text-[10px] font-semibold tracking-[0.35em] text-gold-200">ATELIER</p>
            <h1 className="font-display text-xl font-semibold text-ivory">Resume Tailor</h1>
          </div>
          <button
            type="button"
            onClick={onSignOut}
            className="border border-gold-200 px-3 py-1.5 font-sans text-xs font-semibold tracking-wide text-gold-200 hover:bg-navy-800"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-lg px-4 py-20 text-center">
        <p className="font-sans text-[11px] font-semibold tracking-[0.35em] text-navy-600">MEMBERSHIP PENDING</p>
        <h2 className="mt-3 font-display text-4xl">Thank you, {name}</h2>
        <p className="mt-4 font-suit text-xl italic text-navy-700">
          Your account is ready. An administrator must allow you before you can tailor resumes.
        </p>
        <p className="mt-6 font-sans text-sm text-navy-600">
          Sign in again after you have been allowed. Until then, this atelier stays closed.
        </p>
      </main>
    </div>
  );
}
