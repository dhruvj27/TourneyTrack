/* ---------- storage helpers ---------- */
function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}
function save(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

/* ---------- small utils ---------- */
function teamExists(id) {
  return load('teams', []).some(t => t.id === id);
}

/* ---------- auth ---------- */
function loginTeam(name, pass) {
  const teams = load('teams', []);
  const team = teams.find(t => t.name.trim().toLowerCase() === name.trim().toLowerCase());
  if (!team || pass !== '123') return null;  // compare to stored password
  const user = { role: 'team', teamId: team.id };
  save('currentUser', user);
  return user;
}

function loginSMSC(pass) {
  if (pass !== 'admin123') return null; // change for real use
  const user = { role: 'smsc' };
  save('currentUser', user);
  return user;
}

function getCurrentUser() { return load('currentUser', null); }
function logout() { localStorage.removeItem('currentUser'); }

/* ---------- cascading cleanup (when teams get deleted) ---------- */
function cleanupOrphans() {
  // wipe fixtures that reference non-existent teams
  let fixtures = load('fixtures', []);
  fixtures = fixtures.filter(f => teamExists(f.homeId) && teamExists(f.awayId));
  save('fixtures', fixtures);

  // fix registrations map
  const regs = load('registrations', {});
  for (const tourn in regs) {
    regs[tourn] = (regs[tourn] || []).filter(teamId => teamExists(teamId));
  }
  save('registrations', regs);
}

function deleteTeamById(teamId) {
  const teams = load('teams', []).filter(t => t.id !== teamId);
  save('teams', teams);
  cleanupOrphans();
}

/* ---------- queries ---------- */
function getTeamById(id) { return load('teams', []).find(t => t.id === id) || null; }
function getTeamName(id) { const t = getTeamById(id); return t ? t.name : 'Unknown'; }

function getUpcoming(n = 5) {
  const now = Date.now();
  return load('fixtures', [])
    .filter(f => !f.played && new Date(f.dateISO).getTime() >= now)
    .filter(f => teamExists(f.homeId) && teamExists(f.awayId))
    .sort((a, b) => new Date(a.dateISO) - new Date(b.dateISO))
    .slice(0, n);
}

function getResults(n = 10) {
  return load('fixtures', [])
    .filter(f => f.played)
    .filter(f => teamExists(f.homeId) && teamExists(f.awayId))
    .sort((a, b) => new Date(b.dateISO) - new Date(a.dateISO))
    .slice(0, n);
}

/* ---------- mutations ---------- */
function saveTeam(updatedTeam) {
  const teams = load('teams', []);
  const i = teams.findIndex(t => t.id === updatedTeam.id);
  if (i >= 0) teams[i] = updatedTeam; else teams.push(updatedTeam);
  save('teams', teams);
}

function addFixture({ tournament, homeId, awayId, dateISO }) {
  if (!tournament || !homeId || !awayId || !dateISO) return;
  const fixtures = load('fixtures', []);
  fixtures.push({ id: 'F' + Date.now(), tournament, homeId, awayId, dateISO, played: false });
  save('fixtures', fixtures);
}

function recordResult(fixtureId, home, away) {
  const fixtures = load('fixtures', []);
  const f = fixtures.find(x => x.id === fixtureId);
  if (f) { f.played = true; f.home = Number(home); f.away = Number(away); }
  save('fixtures', fixtures);
}

/* ---------- no seeding, just keep storage tidy ---------- */
cleanupOrphans();
