import { useEffect, useState } from "react";
import { ApiError, downloadSavedResume, fetchAdminUser, fetchMyActivity } from "../services/api";
import type { AdminUserActivity, UserPublic } from "../types";

interface ActivityHistoryProps {
  currentUser: UserPublic;
  /** When set, an administrator is viewing another member. */
  memberId?: number | null;
}

export function formatWhen(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export default function ActivityHistory({ currentUser, memberId = null }: ActivityHistoryProps) {
  const viewingOther = memberId != null && memberId !== currentUser.id;
  const [name, setName] = useState(viewingOther ? "Member" : currentUser.name);
  const [email, setEmail] = useState(viewingOther ? "" : currentUser.email);
  const [rows, setRows] = useState<AdminUserActivity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    const load = viewingOther && memberId != null ? fetchAdminUser(memberId).then((member) => {
      if (cancelled) return;
      setName(member.name);
      setEmail(member.email);
      setRows(member.activity);
    }) : fetchMyActivity().then((activity) => {
      if (cancelled) return;
      setName(currentUser.name);
      setEmail(currentUser.email);
      setRows(activity);
    });

    load
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load activity.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [currentUser.email, currentUser.name, memberId, viewingOther]);

  async function handleDownload(recordId: number) {
    setDownloadingId(recordId);
    setDownloadError(null);
    try {
      await downloadSavedResume(recordId);
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "Could not download that CV.");
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="font-sans text-[11px] font-semibold tracking-[0.35em] text-navy-600">CUTTING RECORD</p>
        <h2 className="font-display text-3xl text-navy">{viewingOther ? `${name}'s activity` : "My activity"}</h2>
        <p className="mt-1 font-suit text-lg italic text-navy-700">
          {email ? `${email} · ` : ""}
          {viewingOther ? "Every tailor job this member has run." : "Every tailor job you have run."}
        </p>
      </div>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {downloadError ? <p className="text-sm text-red-700">{downloadError}</p> : null}
      {isLoading ? <p className="font-sans text-sm text-navy-600">Loading activity…</p> : null}

      {!isLoading && !error && rows.length === 0 ? (
        <p className="font-sans text-sm text-navy-600">No tailor jobs yet.</p>
      ) : null}

      {!isLoading && rows.length > 0 ? (
        <div className="overflow-x-auto border border-navy/10 bg-white/90 p-4 shadow-sm">
          <table className="w-full min-w-[520px] text-left font-sans text-sm">
            <thead>
              <tr className="border-b border-navy/15 text-xs tracking-wide text-navy-600">
                <th className="py-2 pr-3 font-semibold">When</th>
                <th className="py-2 pr-3 font-semibold">Candidate</th>
                <th className="py-2 pr-3 font-semibold">Company</th>
                <th className="py-2 pr-3 font-semibold">Stack</th>
                <th className="py-2 pr-3 font-semibold">Job link</th>
                <th className="py-2 pr-3 font-semibold">File</th>
                <th className="py-2 font-semibold">CV</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-navy/10">
                  <td className="py-2 pr-3 whitespace-nowrap">{formatWhen(row.created_at)}</td>
                  <td className="py-2 pr-3">{row.candidate_name}</td>
                  <td className="py-2 pr-3">{row.company_name}</td>
                        <td className="py-2 pr-3">{row.main_stack}</td>
                        <td className="py-2 pr-3">
                          {row.job_link ? (
                            <a
                              href={row.job_link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="break-all text-navy underline"
                            >
                              {row.job_link}
                            </a>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="py-2 pr-3">{row.generated_filename}</td>
                        <td className="py-2">
                          {row.cv_saved ? (
                            <button
                              type="button"
                              disabled={downloadingId === row.id}
                              onClick={() => void handleDownload(row.id)}
                              className="border border-navy px-2 py-1 text-xs font-semibold text-navy disabled:opacity-50"
                            >
                              {downloadingId === row.id ? "Saving…" : "Download"}
                            </button>
                          ) : (
                            <span className="text-xs text-navy-600">Not saved yet</span>
                          )}
                        </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
