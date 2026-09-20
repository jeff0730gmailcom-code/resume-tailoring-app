import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  fetchAdminAllJobLinks,
  fetchAdminUserJobLinks,
  fetchJobLinkHistory,
} from "../services/api";
import type { JobLinkHistoryItem } from "../types";
import { formatWhen } from "./ActivityHistory";

const PAGE_SIZE = 20;

const fieldClass =
  "h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20";

export type JobLinkHistoryScope = "mine" | "all" | "member";

interface JobLinkHistoryProps {
  scope?: JobLinkHistoryScope;
  /** Required when scope is "member". */
  memberId?: number | null;
  memberLabel?: string;
  onBack?: () => void;
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function dayStamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** SpreadsheetML (.xls) that Excel opens without extra libraries. */
function downloadJobLinksExcel(rows: JobLinkHistoryItem[], includeUser: boolean, filenamePrefix: string): void {
  const header = includeUser
    ? ["Job link", "Stack", "Created at", "User", "Email"]
    : ["Job link", "Stack", "Created at"];
  const bodyRows = rows.map((row) =>
    includeUser
      ? [row.job_link, row.main_stack || "", formatWhen(row.created_at), row.user_name || "", row.user_email || ""]
      : [row.job_link, row.main_stack || "", formatWhen(row.created_at)]
  );
  const xmlRows = [header, ...bodyRows]
    .map(
      (cells) =>
        `<Row>${cells
          .map((cell) => `<Cell><Data ss:Type="String">${escapeXml(cell)}</Data></Cell>`)
          .join("")}</Row>`
    )
    .join("");
  const xml = `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Job links">
  <Table>${xmlRows}</Table>
 </Worksheet>
</Workbook>`;
  const blob = new Blob([xml], { type: "application/vnd.ms-excel" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10);
  anchor.href = url;
  anchor.download = `${filenamePrefix}-${stamp}.xls`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function JobLinkHistory({
  scope = "mine",
  memberId = null,
  memberLabel,
  onBack,
}: JobLinkHistoryProps) {
  const [rows, setRows] = useState<JobLinkHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");

  const showUserColumn = scope === "all";

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    const loader =
      scope === "all"
        ? fetchAdminAllJobLinks()
        : scope === "member" && memberId != null
          ? fetchAdminUserJobLinks(memberId)
          : fetchJobLinkHistory();

    void loader
      .then((items) => {
        if (cancelled) return;
        setRows(items);
        setError(null);
        setPage(1);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load job link history.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scope, memberId]);

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      const day = dayStamp(row.created_at);
      if (createdFrom && (!day || day < createdFrom)) return false;
      if (createdTo && (!day || day > createdTo)) return false;
      return true;
    });
  }, [rows, createdFrom, createdTo]);

  useEffect(() => {
    setPage(1);
  }, [createdFrom, createdTo]);

  const pageCount = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  const pageRows = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredRows.slice(start, start + PAGE_SIZE);
  }, [filteredRows, page]);

  const title =
    scope === "all"
      ? "All job links"
      : scope === "member"
        ? `${memberLabel || "Member"} · job links`
        : "Job link history";

  const subtitle =
    scope === "all"
      ? "Unique job links across every member. Duplicates are shown once. Filter by date, then export."
      : scope === "member"
        ? "Unique job links for this member. Duplicates are shown once. Filter by date, then export."
        : "Your unique job links from past applications. Duplicate links are shown once.";

  const exportPrefix =
    scope === "all" ? "all-job-links" : scope === "member" ? `job-links-user-${memberId ?? "member"}` : "job-link-history";

  function clearDates() {
    setCreatedFrom("");
    setCreatedTo("");
  }

  return (
    <div className="flex flex-col gap-5">
      {onBack ? (
        <button type="button" onClick={onBack} className="self-start text-sm font-medium text-brand hover:underline">
          Back to members
        </button>
      ) : null}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-slate-900">{title}</h2>
          <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
        </div>
        <button
          type="button"
          disabled={filteredRows.length === 0}
          onClick={() => downloadJobLinksExcel(filteredRows, showUserColumn, exportPrefix)}
          className="rounded-lg bg-brand px-3.5 py-2 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-40"
        >
          Export to Excel (.xls)
        </button>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            From date
            <input
              type="date"
              value={createdFrom}
              onChange={(event) => setCreatedFrom(event.target.value)}
              className={fieldClass}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            To date
            <input
              type="date"
              value={createdTo}
              onChange={(event) => setCreatedTo(event.target.value)}
              className={fieldClass}
            />
          </label>
          <div className="flex items-end">
            <button
              type="button"
              onClick={clearDates}
              disabled={!createdFrom && !createdTo}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-40"
              title="Clear date filters"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {isLoading ? <p className="text-sm text-slate-500">Loading job links…</p> : null}

      {!isLoading && filteredRows.length === 0 && !error ? (
        <div className="rounded-xl border border-slate-200 bg-white px-6 py-16 text-center text-sm text-slate-500">
          {rows.length === 0
            ? "No job links yet."
            : "No job links match the selected date range."}
        </div>
      ) : null}

      {filteredRows.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Job link</th>
                  <th className="px-4 py-3">Stack</th>
                  <th className="px-4 py-3">Created at</th>
                  {showUserColumn ? <th className="px-4 py-3">User</th> : null}
                </tr>
              </thead>
              <tbody>
                {pageRows.map((row) => (
                  <tr key={`${row.job_link}-${row.user_id ?? ""}`} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/70">
                    <td className="max-w-[28rem] px-4 py-3">
                      <a
                        href={row.job_link}
                        target="_blank"
                        rel="noreferrer"
                        className="break-all font-medium text-brand hover:underline"
                      >
                        {row.job_link}
                      </a>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{row.main_stack || "—"}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-500">{formatWhen(row.created_at)}</td>
                    {showUserColumn ? (
                      <td className="px-4 py-3 text-slate-700">
                        <p className="font-medium">{row.user_name || "—"}</p>
                        {row.user_email ? <p className="text-xs text-slate-500">{row.user_email}</p> : null}
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3 text-sm text-slate-500">
            <p>
              {filteredRows.length} unique link{filteredRows.length === 1 ? "" : "s"}
              {rows.length !== filteredRows.length ? ` (of ${rows.length})` : ""}
              {pageCount > 1 ? ` · page ${page} of ${pageCount}` : ""}
            </p>
            {pageCount > 1 ? (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="rounded-lg border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                >
                  Prev
                </button>
                <button
                  type="button"
                  disabled={page >= pageCount}
                  onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                  className="rounded-lg border border-slate-200 px-2 py-1 hover:bg-slate-50 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
