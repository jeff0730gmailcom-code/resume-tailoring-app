/**
 * Client for talking to the Resume Tailor AI backend.
 */
import type { ApplicationAnswerItem, CoverLetterContent, ResumeTemplateInfo, TailorResult, UploadedCv } from "../types";

// Empty string = same origin (used in production, where FastAPI serves
// the built frontend). Local Vite still sets VITE_API_BASE_URL in .env.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

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

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // response wasn't JSON, fall through to generic message
  }
  return `Request failed with status ${response.status}`;
}

export async function checkApiHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return response.json();
}

export async function uploadCv(file: File): Promise<UploadedCv> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/resume/upload`, {
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
  const response = await fetch(`${API_BASE_URL}/api/resume/tailor`, {
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

export async function fetchResumeDownload(
  fileId: string,
  format: "pdf" | "docx" = "pdf",
): Promise<{ blob: Blob; folderName: string; fileName: string }> {
  const response = await fetch(`${API_BASE_URL}/api/resume/download/${fileId}?format=${format}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  const folderName = decodeURIComponent(response.headers.get("X-Resume-Folder-Name") ?? "");
  const fileName = decodeURIComponent(response.headers.get("X-Resume-File-Name") ?? "");
  return {
    blob: await response.blob(),
    folderName,
    fileName,
  };
}

/**
 * Fetches the tailored resume rendered through the exact same Jinja2 +
 * Playwright pipeline used by /download (see backend's /preview/{file_id}
 * route), as a PDF blob. This is what guarantees the in-app preview is
 * pixel-identical to the saved file - it's the same bytes, not a
 * separate re-implementation.
 */
export async function fetchResumePreviewPdf(fileId: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/resume/preview/${fileId}`);
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return response.blob();
}
