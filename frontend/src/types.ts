export type Subject = '408' | 'math' | 'english'
export type Rating = 'again' | 'hard' | 'good' | 'easy'
export interface Preferences { daily_goal: number; daily_new_limit: number; retention: Record<Subject, number>; exam_date: string | null; timezone: string; display_name: string }
export interface User { id: string; username: string; display_name: string; preferences: Preferences }
export interface Chapter { id: string; subject: Subject; name: string; position: number }
export interface Media { id: string; url: string; filename: string; width: number; height: number; size: number; mime_type: string }
export interface Schedule { due: string; last_review: string | null; stability: number | null; difficulty: number | null; state: 'new' | 'learning' | 'review' | 'relearning'; version: number; retrievability: number | null }
export interface Item { id: string; title: string; subject: Subject; chapter_id: string | null; kind: string; question: string; answer?: string; difficulty: string; tags: string[]; source: string; is_mistake: boolean; mistake_reason?: string; takeaway?: string; status: 'active' | 'draft' | 'suspended' | 'deleted'; external_id: string | null; version: number; created_at: string; updated_at: string; question_media: Media[]; answer_media?: Media[]; schedule: Schedule }
export interface ItemPage { items: Item[]; total: number; page: number; page_size: number }
export interface Review { id: string; item_id: string; rating: number; reviewed_at: string; duration_ms: number; answer_text: string; answer_media: string[]; undone: boolean; due: string; was_new: boolean }
export interface Stats {
  today: { reviews: number; minutes: number; due: number; overdue: number; new: number; later_today: number; new_available: number; estimated_minutes: number; estimate_from_history: boolean }
  totals: { items: number; mistakes: number; reviews: number; minutes: number; streak: number; active_days: number; retention: number | null }
  subjects: { subject: Subject; total: number; due: number; overdue: number; new: number; reviewed: number; retention: number | null; reviews_30d: number }[]
  heatmap: { date: string; count: number }[]
  forecast: { date: string; '408': number; math: number; english: number; total: number }[]
  ratings: Record<string, number>
  week: { date: string; count: number; minutes: number }[]
  recent_items: Item[]
  weak_items: (Item & { lapses: number })[]
  server_time: string
}
export interface Queue { items: Item[]; due_count: number; new_count: number; new_available: number; next_due: string | null; server_time: string }
export interface Preview { ratings: Record<Rating, { due: string; interval_seconds: number }>; version: number }
export interface APIKey { id: string; name: string; prefix: string; scopes: string[]; created_at: string; expires_at: string | null }
