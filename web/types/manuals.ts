export type Source = {
  source: string;
  page_number: number;
  content: string;
  section_title?: string;
  pdf_url?: string;
};

export type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  mode?: "answer" | "procedure";
  error?: boolean;
  question?: string;
  feedback?: "up" | "down" | null;
};
