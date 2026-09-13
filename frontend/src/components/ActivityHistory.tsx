import { useEffect, useMemo, useState } from "react";
import { ApiError, downloadSavedResume, fetchAdminUser, fetchMyActivity } from "../services/api";
import type { AdminUserActivity, UserPublic } from "../types";

interface ActivityHistoryProps {
  currentUser: UserPublic;
  /** When set, an administrator is viewing another member. */
  memberId?: number | null;
}

const PAGE_SIZE = 10;

const fieldClass =
  "h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20";

export function formatWhen(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatTableDate(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function dayStamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function hostFromLink(link: string): string {
  try {
    return new URL(link).hostname.replace(/^www\./, "");
  } catch {
    return link;
  }
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

  const [jobTitle, setJobTitle] = useState("");
  const [company, setCompany] = useState("");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    const load =
      viewingOther && memberId != null
        ? fetchAdminUser(memberId).then((member) => {
            if (cancelled) return;
            setName(member.name);
            setEmail(member.email);
            setRows(member.activity);
          })
        : fetchMyActivity().then((activity) => {
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

  const filtered = useMemo(() => {
    const titleQ = jobTitle.trim().toLowerCase();
    const companyQ = company.trim().toLowerCase();
    return rows.filter((row) => {
      if (titleQ && !row.candidate_name.toLowerCase().includes(titleQ)) return false;
      if (companyQ && !row.company_name.toLowerCase().includes(companyQ)) return false;
      const created = dayStamp(row.created_at);
      if (createdFrom && created && created < createdFrom) return false;
      if (createdTo && created && created > createdTo) return false;
      return true;
    });
  }, [rows, jobTitle, company, createdFrom, createdTo]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pageRows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
    setSelectedIds(new Set());
  }, [jobTitle, company, createdFrom, createdTo, rows]);

  function toggleRow(id: number) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function togglePage() {
    const ids = pageRows.map((row) => row.id);
    const allSelected = ids.length > 0 && ids.every((id) => selectedIds.has(id));
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allSelected) ids.forEach((id) => next.delete(id));
      else ids.forEach((id) => next.add(id));
      return next;
    });
  }

  function selectAllMatching() {
    setSelectedIds(new Set(filtered.map((row) => row.id)));
  }

  function resetFilters() {
    setJobTitle("");
    setCompany("");
    setCreatedFrom("");
    setCreatedTo("");
  }

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

  const pageSelectedCount = pageRows.filter((row) => selectedIds.has(row.id)).length;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-slate-900">
          {viewingOther ? `${name}'s applications` : "Applications"}
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          {email ? `${email} · ` : ""}
          {viewingOther ? "Every tailored resume this member has generated." : "Search and open the tailored resumes you have generated."}
        </p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            Job title
            <input
              value={jobTitle}
              onChange={(event) => setJobTitle(event.target.value)}
              placeholder="Candidate or title"
              className={fieldClass}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            Company
            <input
              value={company}
              onChange={(event) => setCompany(event.target.value)}
              placeholder="Company"
              className={fieldClass}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            Created from
            <input type="date" value={createdFrom} onChange={(event) => setCreatedFrom(event.target.value)} className={fieldClass} />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            Created to
            <input type="date" value={createdTo} onChange={(event) => setCreatedTo(event.target.value)} className={fieldClass} />
          </label>
          <div className="flex items-end">
            <button
              type="button"
              onClick={resetFilters}
              title="Reset filters"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 12a9 9 0 1 0 3-6.7" />
                <path d="M3 4v5h5" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
        <p>
          {selectedIds.size} of {filtered.length} selected — {pageRows.length} on this page
          {rows.length > 0 ? ` · ${rows.length} total from database` : ""}
        </p>
        <button
          type="button"
          onClick={selectAllMatching}
          disabled={filtered.length === 0}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
        >
          Select all matching
        </button>
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {downloadError ? <p className="text-sm text-red-600">{downloadError}</p> : null}
      {isLoading ? <p className="text-sm text-slate-500">Loading applications…</p> : null}

      {!isLoading && !error && filtered.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white px-6 py-16 text-center text-sm text-slate-500">
          {rows.length === 0 ? "No applications yet. Create one from the Create application tab." : "No applications match these filters."}
        </div>
      ) : null}

      {!isLoading && pageRows.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[880px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={pageRows.length > 0 && pageSelectedCount === pageRows.length}
                      onChange={togglePage}
                      className="h-4 w-4 rounded border-slate-300 text-brand focus:ring-brand"
                    />
                  </th>
                  <th className="px-3 py-3">Job</th>
                  <th className="px-3 py-3">Company</th>
                  <th className="px-3 py-3">Profile</th>
                  <th className="px-3 py-3">Description</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3">Resume files</th>
                  <th className="px-3 py-3">Created</th>
                  <th className="px-3 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/70">
                    <td className="px-4 py-4">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(row.id)}
                        onChange={() => toggleRow(row.id)}
                        className="h-4 w-4 rounded border-slate-300 text-brand focus:ring-brand"
                      />
                    </td>
                    <td className="px-3 py-4">
                      <p className="font-semibold text-slate-900">{row.candidate_name}</p>
                      {row.job_link ? (
                        <a
                          href={row.job_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-1 inline-flex items-center gap-1 text-xs text-brand hover:underline"
                        >
                          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M10 13a5 5 0 0 0 7.07 0l1.41-1.41a5 5 0 0 0-7.07-7.07L10 5.93" />
                            <path d="M14 11a5 5 0 0 0-7.07 0L5.52 12.41a5 5 0 0 0 7.07 7.07L14 18.07" />
                          </svg>
                          Open job
                        </a>
                      ) : (
                        <span className="mt-1 block text-xs text-slate-400">No job link</span>
                      )}
                    </td>
                    <td className="px-3 py-4 text-slate-700">{row.company_name}</td>
                    <td className="px-3 py-4 text-slate-700">{row.main_stack}</td>
                    <td className="max-w-[180px] truncate px-3 py-4 text-slate-500" title={row.job_link || row.generated_filename}>
                      {row.job_link ? hostFromLink(row.job_link) : row.generated_filename || "—"}
                    </td>
                    <td className="px-3 py-4">
                      <span className="inline-flex rounded-full bg-sky-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-sky-700">
                        Generated
                      </span>
                    </td>
                    <td className="px-3 py-4">
                      {row.cv_saved ? (
                        <button
                          type="button"
                          disabled={downloadingId === row.id}
                          onClick={() => void handleDownload(row.id)}
                          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-700 hover:text-brand disabled:opacity-50"
                        >
                          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M12 3v12" />
                            <path d="m7 11 5 5 5-5" />
                            <path d="M5 19h14" />
                          </svg>
                          {downloadingId === row.id ? "Saving…" : "PDF"}
                        </button>
                      ) : (
                        <span className="text-xs text-slate-400">Not saved</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-4 text-slate-500">{formatTableDate(row.created_at)}</td>
                    <td className="px-3 py-4">
                      {row.job_link ? (
                        <a
                          href={row.job_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-600"
                        >
                          Apply
                          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M22 2 11 13" />
                            <path d="M22 2 15 22l-4-9-9-4 20-7z" />
                          </svg>
                        </a>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3 text-sm text-slate-500">
            <p>
              {filtered.length} application{filtered.length === 1 ? "" : "s"} — page {currentPage} of {pageCount}
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={currentPage <= 1}
                onClick={() => setPage((value) => Math.max(1, value - 1))}
                className="rounded-lg border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
              >
                ‹
              </button>
              <select
                value={currentPage}
                onChange={(event) => setPage(Number(event.target.value))}
                className="h-9 rounded-lg border border-slate-200 bg-white px-2 text-sm"
              >
                {Array.from({ length: pageCount }, (_, index) => index + 1).map((number) => (
                  <option key={number} value={number}>
                    Page {number}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={currentPage >= pageCount}
                onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
                className="rounded-lg border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
              >
                ›
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
