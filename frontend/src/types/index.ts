/**
 * Shared frontend types for the resume tailoring flow, mirroring the
 * backend Pydantic schemas in backend/app/models/schemas.py.
 */

export type FlowStep = "idle" | "uploading" | "ready" | "generating" | "preview";

export interface UploadedCv {
  fileId: string;
  fileName: string;
  cvTextPreview: string;
}

export interface ResumeTemplateInfo {
  slug: string;
  name: string;
  description: string;
  /** Path under the backend's /static mount - prefix with the API base URL to load. */
  thumbnailUrl: string;
}

export interface ContactInfo {
  name: string;
  email?: string | null;
  phone?: string | null;
  location?: string | null;
  linkedin?: string | null;
}

export interface ExperienceEntry {
  title: string;
  company: string;
  dates: string;
  bullets: string[];
}

export interface EducationEntry {
  degree: string;
  institution: string;
  dates: string;
}

export interface SkillCategories {
  languages: string[];
  backend: string[];
  frontend: string[];
  cloud: string[];
  devops: string[];
  databases: string[];
  ai: string[];
  tools: string[];
}

export const SKILL_CATEGORY_LABELS: Record<keyof SkillCategories, string> = {
  languages: "Languages",
  backend: "Backend",
  frontend: "Frontend",
  cloud: "Cloud",
  devops: "DevOps",
  databases: "Databases",
  ai: "AI",
  tools: "Tools",
};

export interface TailoredResumeContent {
  contact: ContactInfo;
  summary: string;
  skills: SkillCategories;
  experience: ExperienceEntry[];
  education: EducationEntry[];
  languages: string[];
  certifications: string[];
}

export interface AtsMatchInfo {
  score: number;
  matchedKeywords: string[];
  missingKeywords: string[];
}

export interface CoverLetterContent {
  recipientCompany: string;
  greeting: string;
  paragraphs: string[];
  closing: string;
  senderName: string;
  senderLocation?: string | null;
  senderEmail?: string | null;
  senderPhone?: string | null;
}

export interface ApplicationAnswerItem {
  question: string;
  answer: string;
}

export interface TailorResult {
  resume: TailoredResumeContent;
  atsMatch: AtsMatchInfo;
  /** Zip base name (no extension), e.g. "Mateo Baranji_node_asd". The CV file inside is the candidate's name. */
  generatedFilename: string;
  templateSlug: string;
  /** Present only when the user asked for a cover letter. Preview-only; never a downloadable file. */
  coverLetter: CoverLetterContent | null;
  applicationAnswers: ApplicationAnswerItem[];
}

export interface DownloadSaveResult {
  zipName: string;
}

export interface UserPublic {
  id: number;
  email: string;
  name: string;
  role: string;
  is_approved: boolean;
  is_active: boolean;
}

export interface AuthResponse {
  token: string;
  user: UserPublic;
}

export interface AdminUserActivity {
  id: number;
  candidate_name: string;
  main_stack: string;
  company_name: string;
  generated_filename: string;
  created_at: string;
}

export interface AdminUserRow {
  id: number;
  email: string;
  name: string;
  role: string;
  is_approved: boolean;
  is_active: boolean;
  created_at: string;
  resume_count: number;
  activity: AdminUserActivity[];
}

export function userCanUseApp(user: UserPublic): boolean {
  return user.role === "admin" || user.is_approved;
}
