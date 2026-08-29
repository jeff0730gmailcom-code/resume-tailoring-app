/**
 * Client for talking to the Resume Tailor AI backend.
 */
import type {
  AdminUserActivity,
  AdminUserRow,
  ApplicationAnswerItem,
  AuthResponse,
  CoverLetterContent,
  DownloadSaveResult,
  ResumeTemplateInfo,
  TailorResult,
  UploadedCv,
  UserPublic,
} from "../types";

// Empty string = same origin (used in production, where FastAPI serves
// the built frontend). Local Vite still sets VITE_API_BASE_URL in .env.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

const TOKEN_KEY = "resume_tailor_token";
export const AUTH_EXPIRED_EVENT = "auth:expired";

export interface HealthResponse {
  status: string;
  message: string;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

function isPublicAuthPath(path: string): boolean {
  return (
    path === "/api/auth/login" ||
    path === "/api/auth/register" ||
    path === "/api/auth/google" ||
    path === "/api/auth/config"
  );
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: authHeaders(init.headers),
  });
  if (response.status === 401 && !isPublicAuthPath(path)) {
    clearAccessToken();
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }
  return response;
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return String(body.detail[0].msg);
  } catch {
    // response wasn't JSON, fall through to generic message
  }
  return `Request failed with status ${response.status}`;
}

function mapUser(raw: Record<string, unknown>): UserPublic {
  const role = String(raw.role ?? "user");
  return {
    id: Number(raw.id),
    email: String(raw.email ?? ""),
    name: String(raw.name ?? ""),
    role,
    is_approved: Boolean(raw.is_approved) || role === "admin",
    is_active: raw.is_active !== false,
  };
}

function persistAuth(data: Record<string, unknown>): AuthResponse {
  const token = String(data.token ?? "");
  setAccessToken(token);
  return {
    token,
    user: mapUser((data.user as Record<string, unknown>) ?? {}),
  };
}

export async function checkApiHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return response.json();
}

export async function fetchAuthConfig(): Promise<{ googleClientId: string }> {
  const response = await fetch(`${API_BASE_URL}/api/auth/config`);
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  const data = await response.json();
  return { googleClientId: String(data.google_client_id ?? "") };
}

export async function registerAccount(name: string, email: string, password: string): Promise<AuthResponse> {
  const response = await apiFetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return persistAuth(await response.json());
}

export async function loginWithEmail(email: string, password: string): Promise<AuthResponse> {
  const response = await apiFetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return persistAuth(await response.json());
}

export async function loginWithGoogle(credential: string): Promise<AuthResponse> {
  const response = await apiFetch("/api/auth/google", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential }),
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return persistAuth(await response.json());
}

export async function fetchMe(): Promise<UserPublic> {
  const response = await apiFetch("/api/auth/me");
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return mapUser(await response.json());
}

export async function fetchAdminUsers(): Promise<AdminUserRow[]> {
  const response = await apiFetch("/api/admin/users");
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return response.json();
}

export async function fetchAdminUser(userId: number): Promise<AdminUserRow> {
  const response = await apiFetch(`/api/admin/users/${userId}`);
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return response.json();
}

export async function updateAdminUser(
  userId: number,
  patch: { is_approved?: boolean; is_active?: boolean }
): Promise<AdminUserRow> {
  const response = await apiFetch(`/api/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return response.json();
}

export async function deleteAdminUser(userId: number): Promise<void> {
  const response = await apiFetch(`/api/admin/users/${userId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
}

export async function fetchMyActivity(): Promise<AdminUserActivity[]> {
  const response = await apiFetch("/api/resume/history");
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  const rows = (await response.json()) as Array<Record<string, unknown>>;
  return rows.map((row) => ({
    id: Number(row.id),
    candidate_name: String(row.candidate_name ?? ""),
    main_stack: String(row.main_stack ?? ""),
    company_name: String(row.company_name ?? ""),
    generated_filename: String(row.generated_filename ?? ""),
    created_at: String(row.created_at ?? ""),
  }));
}

export async function uploadCv(file: File): Promise<UploadedCv> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiFetch("/api/resume/upload", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }

  const data = await response.json();
  return {
    fileId: data.file_id,
    fileName: data.file_name,
    cvTextPreview: data.cv_text_preview,
  };
}

export async function fetchTemplates(): Promise<ResumeTemplateInfo[]> {
  const response = await fetch(`${API_BASE_URL}/api/resume/templates`);
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  const data = await response.json();
  return (data as Array<Record<string, unknown>>).map((t) => ({
    slug: t.slug as string,
    name: t.name as string,
    description: (t.description as string) ?? "",
    thumbnailUrl: `${API_BASE_URL}${t.thumbnail_url as string}`,
  }));
}

function mapCoverLetter(raw: Record<string, unknown> | null | undefined): CoverLetterContent | null {
  if (!raw) return null;
  return {
    recipientCompany: String(raw.recipient_company ?? ""),
    greeting: String(raw.greeting ?? ""),
    paragraphs: Array.isArray(raw.paragraphs) ? raw.paragraphs.map(String) : [],
    closing: String(raw.closing ?? ""),
    senderName: String(raw.sender_name ?? ""),
    senderLocation: (raw.sender_location as string | null) ?? null,
    senderEmail: (raw.sender_email as string | null) ?? null,
    senderPhone: (raw.sender_phone as string | null) ?? null,
  };
}

function mapApplicationAnswers(raw: unknown): ApplicationAnswerItem[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const row = item as Record<string, unknown>;
      const question = String(row.question ?? "").trim();
      const answer = String(row.answer ?? "").trim();
      if (!question || !answer) return null;
      return { question, answer };
    })
    .filter((item): item is ApplicationAnswerItem => item !== null);
}

export async function tailorResume(
  fileId: string,
  jobDescription: string,
  mainStack: string,
  companyName: string,
  templateSlug: string,
  includeCoverLetter = false,
  applicationQuestions: string[] = []
): Promise<TailorResult> {
  const response = await apiFetch("/api/resume/tailor", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_id: fileId,
      job_description: jobDescription,
      main_stack: mainStack,
      company_name: companyName,
      template_slug: templateSlug,
      include_cover_letter: includeCoverLetter,
      application_questions: applicationQuestions,
    }),
  });

  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }

  const data = await response.json();
  return {
    resume: data.resume,
    atsMatch: {
      score: data.ats_match.score,
      matchedKeywords: data.ats_match.matched_keywords,
      missingKeywords: data.ats_match.missing_keywords,
    },
    generatedFilename: data.generated_filename,
    templateSlug: data.template_slug,
    coverLetter: mapCoverLetter(data.cover_letter),
    applicationAnswers: mapApplicationAnswers(data.application_answers),
  };
}

export async function downloadResume(
  fileId: string,
  format: "pdf" | "docx" = "pdf",
): Promise<DownloadSaveResult> {
  const response = await apiFetch(`/api/resume/download/${fileId}?format=${format}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }

  const blob = await response.blob();
  const zipName = zipNameFromDisposition(response.headers.get("Content-Disposition")) || "resume.zip";
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = zipName;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
  return { zipName };
}

function zipNameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const utf = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(header);
  if (utf) return decodeURIComponent(utf[1].trim().replace(/^"(.*)"$/, "$1"));
  const ascii = /filename="?([^";]+)"?/i.exec(header);
  if (ascii) return ascii[1].trim();
  return null;
}

/**
 * Fetches the tailored resume rendered through the exact same Jinja2 +
 * Playwright pipeline used by /download (see backend's /preview/{file_id}
 * route), as a PDF blob. This is what guarantees the in-app preview is
 * pixel-identical to the saved file - it's the same bytes, not a
 * separate re-implementation.
 */
export async function fetchResumePreviewPdf(fileId: string): Promise<Blob> {
  const response = await apiFetch(`/api/resume/preview/${fileId}`);
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return response.blob();
}
