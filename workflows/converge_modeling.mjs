// Phase-B convergence loop — modeling competency (wave 1).
//
// attempt -> deterministic score (Python) -> visual judge (panel, if eyes available)
// -> distill, repeated until the modeling battery task passes or budget/plateau.
//
// Design invariants:
// * Scoring is Python (scripts/eval_observe.py) — agents ATTEMPT, they never score
//   themselves, so the loop cannot be talked into a passing grade.
// * The judge is a skeptical multi-lens panel that only runs when the eyes produced
//   images (needs a visible Blender / GL context); headless => objective-only pass.
// * The distilled playbook entry is WRITTEN to playbooks/learned/modeling.md but NOT
//   git-committed — it is reviewed at the human checkpoint before merge (governance).
//
// Run:  Workflow({ scriptPath: ".../workflows/converge_modeling.mjs",
//                  args: { port: 8765, subject: "Subject", maxRounds: 6 } })
// Requires a live bridge on `port` (launch a visible Blender + addon first).

export const meta = {
  name: 'converge-modeling',
  description: 'Phase-B convergence loop: grow Layer 2 for the modeling competency by attempting the modeling battery task against a live Blender until its objective gates (and the visual judge, when eyes are available) pass.',
  phases: [
    { title: 'Setup' },
    { title: 'Attempt' },
    { title: 'Judge' },
    { title: 'Distill' },
  ],
}

const PORT = (args && args.port) || 8765
const SUBJECT = (args && args.subject) || 'Subject'
const TASK = 'modeling_prop'
const REPO = (args && args.repo) || '/home/frankyin/Desktop/lab/lab-niua-blender'
const MAX_ROUNDS = (args && args.maxRounds) || 6
const JUDGE_THRESHOLD = 7.0
const CALL = `python ${REPO}/scripts/bridge_call.py ${PORT}`
const OBSERVE = `python ${REPO}/scripts/eval_observe.py ${PORT} ${TASK} ${SUBJECT} /tmp/niua_eval`

const SCORECARD_SCHEMA = {
  type: 'object',
  properties: {
    gates_pass: { type: 'boolean' },
    images_available: { type: 'boolean' },
    images: { type: 'array', items: { type: 'string' } },
    gates: { type: 'array' },
    failing: { type: 'array', items: { type: 'string' } },
  },
  required: ['gates_pass', 'images_available', 'images'],
}
const JUDGE_SCHEMA = {
  type: 'object',
  properties: { score: { type: 'number' }, critique: { type: 'string' } },
  required: ['score', 'critique'],
}

phase('Setup')

// Build a deliberately deficient (triangulated) subject to clean up.
await agent(
  `Set up the modeling subject in the live Blender. Run each as a shell command:\n` +
  `  ${CALL} scene.create_object '{"type":"CUBE","name":"${SUBJECT}"}'   (ignore "already exists")\n` +
  `  ${CALL} mesh.subdivide '{"object":"${SUBJECT}","cuts":2}'\n` +
  `  ${CALL} capabilities.invoke '{"idname":"mesh.quads_convert_to_tris","object":"${SUBJECT}","mode":"EDIT","select":"[\\"${SUBJECT}\\"]","args":"{}"}'\n` +
  `Then report quad_ratio from: ${CALL} feedback.quality '{"object":"${SUBJECT}"}'`,
  { phase: 'Setup', label: 'setup subject' },
)

const playbook = await agent(
  `Run and return the full stdout:\n` +
  `python -c "import sys; sys.path.insert(0,'${REPO}/src'); from niua_blender_mcp.playbooks import load_playbook; print(load_playbook('modeling'))"`,
  { phase: 'Setup', label: 'load playbook' },
)
const rubric = await agent(
  `Run and return the full stdout:\n` +
  `python -c "import sys; sys.path.insert(0,'${REPO}/src'); from niua_blender_mcp.evals.battery import load_task; print(load_task('${TASK}')['rubric'])"`,
  { phase: 'Setup', label: 'load rubric' },
)

let passed = false
let critique = 'First attempt — start from the playbook.'
let bestGates = -1
let plateau = 0
const trajectory = []

for (let round = 1; round <= MAX_ROUNDS && !passed; round++) {
  if (budget.total && budget.remaining() < 60000) { log(`budget low — stopping before round ${round}`); break }

  phase('Attempt')
  await agent(
    `You are a senior 3D game artist working in a LIVE Blender. Improve the mesh "${SUBJECT}" toward:\n` +
    `  clean all-quad game-ready topology: quad_ratio >= 0.95, zero n-gons, zero non-manifold edges, within tri budget.\n` +
    `Drive Blender ONLY via shell: ${CALL} <tool> '<json-args>'\n` +
    `Available: model.retopo_quads, mesh.* operators, and capabilities.search / capabilities.describe / capabilities.invoke to discover anything else\n` +
    `  (e.g. ${CALL} capabilities.search '{"query":"quad","kind":"operator"}').\n\n` +
    `SENIOR PLAYBOOK:\n${playbook}\n\n` +
    `PREVIOUS-ROUND FEEDBACK: ${critique}\n\n` +
    `Make concrete edits now, then stop. Report exactly which tool calls you made and why.`,
    { phase: 'Attempt', label: `attempt r${round}` },
  )

  const card = await agent(
    `Run this exactly once and return ONLY the JSON it prints, with one addition:\n` +
    `  ${OBSERVE}\n` +
    `Add a top-level "failing" array = the "path" of every gate whose "pass" is false.`,
    { phase: 'Attempt', label: `score r${round}`, schema: SCORECARD_SCHEMA },
  )
  if (!card) { log(`round ${round}: no scorecard returned`); continue }

  const passedGates = (card.gates || []).filter(g => g.pass).length
  trajectory.push({ round, gates_pass: card.gates_pass, passedGates, failing: card.failing || [] })
  log(`round ${round}: gates_pass=${card.gates_pass} (${passedGates} gates ok)`)

  if (!card.gates_pass) {
    critique = `Objective gates still failing: ${(card.failing || []).join(', ')}. Target those specifically.`
    if (passedGates <= bestGates) { plateau++ } else { plateau = 0; bestGates = passedGates }
    if (plateau >= 2) { log(`plateau (${plateau} rounds, no objective gain) — stopping`); break }
    continue
  }

  // Gates pass. Run the taste judge ONLY if the eyes produced images.
  if (card.images_available && (card.images || []).length) {
    phase('Judge')
    const lenses = ['topology flow & quad distribution', 'silhouette & proportion', 'shading & game-readiness']
    const votes = await parallel(lenses.map(lens => () =>
      agent(
        `You are a skeptical senior game artist judging via the "${lens}" lens.\n` +
        `Open and look at each render with your file Read tool: ${card.images.join(', ')}\n` +
        `Score 0-10 against this rubric (default LOW when unsure):\n${rubric}\n` +
        `Return JSON {"score": <0-10 number>, "critique": "<one concrete sentence>"}.`,
        { phase: 'Judge', label: `judge:${lens.split(' ')[0]}`, schema: JUDGE_SCHEMA },
      )
    ))
    const scores = votes.filter(Boolean).map(v => v.score).sort((a, b) => a - b)
    const median = scores.length ? scores[Math.floor(scores.length / 2)] : null
    log(`round ${round}: gates PASS, judge median=${median}`)
    if (median === null || median < JUDGE_THRESHOLD) {
      critique = `Gates pass but judge median ${median} (<${JUDGE_THRESHOLD}). Raise craft: ` +
        votes.filter(Boolean).map(v => v.critique).join(' ')
      continue
    }
  } else {
    log(`round ${round}: gates PASS; eyes unavailable (headless/no-GL) — objective-only pass`)
  }

  passed = true
  phase('Distill')
  await agent(
    `The modeling task passed. Distill what worked into a concise, reusable senior playbook entry:\n` +
    `5-12 bullet lines mixing heuristics and the EXACT tool calls that produced clean quads.\n` +
    `Write it to a NEW file ${REPO}/playbooks/learned/modeling.md (mkdir -p the dir). Do NOT edit the seed playbook. Do NOT git commit.\n` +
    `Return the file content you wrote.`,
    { phase: 'Distill', label: 'distill playbook' },
  )
}

return {
  task: TASK,
  passed,
  rounds: trajectory.length,
  trajectory,
  note: passed
    ? 'Converged. Learned entry at playbooks/learned/modeling.md (UNCOMMITTED — review at checkpoint before merge).'
    : 'Did not converge within bounds (rounds/budget/plateau).',
}
