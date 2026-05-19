/* Shared auth utilities — โหลดหลัง supabase-js + config.js */
window.sb = supabase.createClient(window.SUPABASE_URL, window.SUPABASE_ANON_KEY);

window.tidtamAuth = {
  async session() {
    const { data } = await sb.auth.getSession();
    return data.session;
  },

  async profile() {
    const s = await this.session();
    if (!s) return null;
    const { data } = await sb.from('profiles').select('*').eq('id', s.user.id).single();
    return data;
  },

  async requireLogin() {
    const s = await this.session();
    if (!s) { location.href = 'login.html'; return null; }
    return s;
  },

  async requireAdmin() {
    const s = await this.requireLogin();
    if (!s) return null;
    const p = await this.profile();
    if (p?.role !== 'admin') {
      alert('สิทธิ์ไม่พอ — ต้องเป็น admin');
      location.href = 'index.html';
      return null;
    }
    return { session: s, profile: p };
  },

  async logout() {
    await sb.auth.signOut();
    location.href = 'login.html';
  },
};
