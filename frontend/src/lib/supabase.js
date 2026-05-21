import { createClient } from '@supabase/supabase-js'

const supabaseUrl  = import.meta.env.VITE_SUPABASE_URL
const supabaseKey  = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabase = createClient(supabaseUrl, supabaseKey)

// ── Fetch latest scan date ────────────────────────────────────────────────────
export async function getLatestScanDate() {
  const { data } = await supabase
    .from('sector_scores')
    .select('scan_date')
    .order('scan_date', { ascending: false })
    .limit(1)
  return data?.[0]?.scan_date ?? null
}

// ── Fetch sector scores ───────────────────────────────────────────────────────
export async function getSectorScores(scanDate) {
  const { data } = await supabase
    .from('sector_scores')
    .select('*')
    .eq('scan_date', scanDate)
    .order('prc', { ascending: false })
  return data ?? []
}

// ── Fetch macro summary ───────────────────────────────────────────────────────
export async function getMacroSummary(scanDate) {
  const { data } = await supabase
    .from('macro_summaries')
    .select('*')
    .eq('scan_date', scanDate)
    .limit(1)
  return data?.[0] ?? null
}

// ── Fetch macro findings ──────────────────────────────────────────────────────
export async function getMacroFindings(scanDate) {
  const { data } = await supabase
    .from('macro_findings')
    .select('*')
    .eq('scan_date', scanDate)
    .order('score', { ascending: false })
  return data ?? []
}
