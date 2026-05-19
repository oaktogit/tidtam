// Vercel serverless function — triggers the GitHub Actions scrape workflow.
// Verifies the caller is logged in to Supabase before dispatching.

const REPO = 'oaktogit/tidtam';
const WORKFLOW = 'scrape.yml';
const REF = 'main';
const SUPABASE_URL = 'https://khweesxzhbxroytmvbnl.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_d9_ohgy4KNFnwGWAQAa_gw_nR0-lsT9';

async function verifyUser(req) {
  const auth = req.headers['authorization'] || '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : null;
  if (!token) return null;
  const r = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
    headers: { Authorization: `Bearer ${token}`, apikey: SUPABASE_ANON_KEY },
  });
  if (!r.ok) return null;
  return r.json();
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const user = await verifyUser(req);
  if (!user) return res.status(401).json({ error: 'Not authenticated' });

  const token = process.env.GITHUB_TOKEN;
  if (!token) return res.status(500).json({ error: 'GITHUB_TOKEN not configured' });

  const r = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'tidtam-dashboard',
      },
      body: JSON.stringify({ ref: REF }),
    }
  );

  if (r.status === 204) return res.status(202).json({ ok: true });
  const text = await r.text().catch(() => '');
  return res.status(r.status).json({ error: text || `GitHub returned ${r.status}` });
}
