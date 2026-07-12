// ============================================================================
// NON-PRIMARY. This judged 5-lens panel is an OPTIONAL perceptual spot-check only.
// The PRIMARY, deterministic grade for this tool is the objective runner:
//   python scripts/run_objective_benchmark.py --port <p>
// (readiness = objective gates passed, order-free; preservation = silhouette IoU vs intake;
//  do-no-harm is a scorecard FLAG, never a revert; no LLM judge). Do NOT treat this workflow's
//  number as the target — SEM ~0.7 — it is retained solely for occasional perceptual review.
// ============================================================================
//
// Layer 2 — The Altimeter.
//
// Runs the held-out senior benchmark through the LIVE pipeline and scores senior
// quality (not just gate-pass). Per item: build the deficient input mesh, drive the
// gated pipeline as a senior finisher, observe with the eyes, judge with a skeptical
// multi-lens panel anchored by the objective gates, then score. Aggregate the reading.
//
// Design invariants:
// * The objective gates are the un-gameable FLOOR: score_item() forces overall=0 when
//   gates fail, so the judge can never lift a gate-failing asset (scorecard.py owns this).
// * The judge panel only runs when the eyes produced images (needs a visible Blender / GL).
// * scorecard.py is the single source of truth for scoring/aggregation — this script never
//   re-implements it; it calls score_item()/aggregate() once at the end.
//
// Run:  Workflow({ scriptPath: ".../workflows/altimeter.mjs", args: { port: 8765, repo: "..." } })
// Requires a live bridge on `port` (launch a VISIBLE Blender + addon first; headless has no GL).

export const meta = {
  name: 'altimeter',
  grade: 'non-primary',
  description: 'NON-PRIMARY perceptual spot-check (judged, 5-lens panel). The PRIMARY grade is scripts/run_objective_benchmark.py (feedback.readiness + feedback.preservation, no LLM judge). Run the Layer-2 held-out benchmark through the live pipeline and score senior quality per item as an optional A/B diagnostic reading, not the target metric.',
  phases: [
    { title: 'Load' },
    { title: 'Finish' },
    { title: 'Judge' },
    { title: 'Score' },
  ],
}

const PORT = (args && args.port) || 8765
const REPO = (args && args.repo) || '/home/frankyin/Desktop/lab/lab-niua-blender'
const OUTDIR = (args && args.outdir) || '/tmp/niua_altimeter'
const CALL = `python ${REPO}/scripts/bridge_call.py ${PORT}`
const LENSES = ['silhouette', 'proportion', 'topology', 'material_read', 'design_intent']

const FINISH_SCHEMA = {
  type: 'object',
  properties: {
    id: { type: 'string' },
    subject: { type: 'string' },
    gates_pass: { type: 'boolean' },
    reached_stage: { type: 'string' },
    images: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['id', 'gates_pass', 'images'],
}
const JUDGE_SCHEMA = {
  type: 'object',
  properties: { score: { type: 'number' }, critique: { type: 'string' } },
  required: ['score', 'critique'],
}
const READING_SCHEMA = {
  type: 'object',
  properties: { reading: { type: 'object' }, cards: { type: 'array' } },
  required: ['reading'],
}

phase('Load')

// Load the whole benchmark as one JSON blob {id: item_dict_with_rubric_text} — one python
// call, so Finish/Judge prompts can be built without further python round-trips.
const benchRaw = await agent(
  `Run this and return ONLY the stdout it prints (a single JSON object):\n` +
  `python3 -c "import json,sys; sys.path.insert(0,'${REPO}/src'); ` +
  `from niua_blender_mcp.evals.benchmark import list_items, load_item; ` +
  `print(json.dumps({i: load_item(i) for i in list_items()}))"`,
  { phase: 'Load', label: 'load benchmark' },
)
const bench = JSON.parse(benchRaw)
const items = Object.values(bench)
log(`altimeter: ${items.length} benchmark items across ${new Set(items.map(i => i.asset_class)).size} classes`)

// Per item: Finish (drive the pipeline) -> Judge+assemble (panel -> raw card). Pipelined:
// item B can be judged while item C is still being finished.
const rawCards = await pipeline(
  items,

  // Stage 1 — Finish: build the deficient input, then drive the gated pipeline as a senior.
  (item) => agent(
    `You are a SENIOR game-asset artist working against a LIVE Blender bridge on port ${PORT}.\n` +
    `Drive Blender ONLY via shell: ${CALL} <tool> '<json-args>'\n\n` +
    `TASK: take benchmark item "${item.id}" from its deficient starting mesh to a game-ready asset for this brief:\n` +
    `  ${item.brief}\n` +
    `Asset class: ${item.asset_class}. Target stages in order: ${JSON.stringify(item.stages)}.\n\n` +
    `STEP 1 — build the deficient starting mesh named "bench_${item.id}" from this recipe (run each step in order):\n` +
    `  ${JSON.stringify(item.input.recipe)}\n` +
    `  For a "scene.create_object" step, add "name":"bench_${item.id}". For a "capabilities.invoke" primitive_add\n` +
    `  step, the new object becomes active — then rename it to "bench_${item.id}" (e.g. capabilities.invoke object.select_all off + set the object's name). Ensure exactly one object named "bench_${item.id}" results.\n\n` +
    `STEP 2 — pipeline.start '{"object":"bench_${item.id}","asset_class":"${item.asset_class}"}'.\n` +
    `STEP 3 — advance through the stages: at each stage, use craft_workflow.recommend to find the senior workflow,\n` +
    `  run the recommended curated verbs / Layer-1 tools, then pipeline.gate_check; if it passes, pipeline.advance.\n` +
    `  Use feedback.critique '{"object":"bench_${item.id}"}' as your eyes between edits. If a stage gate cannot pass\n` +
    `  after a couple of honest attempts, STOP advancing and report gates_pass=false with the stage you reached.\n\n` +
    `STEP 4 — save eye renders for the judges: call feedback.topology and feedback.capture_views (preset ortho4) on\n` +
    `  bench_${item.id}; the bridge returns base64 — decode and write each PNG under ${OUTDIR}/${item.id}/ and collect the file paths.\n\n` +
    `Return JSON: {id:"${item.id}", subject:"bench_${item.id}", gates_pass:<true only if EVERY targeted stage gate passed>, reached_stage:"<last stage that passed>", images:[<png paths>], notes:"<one line>"}.`,
    { phase: 'Finish', label: `finish:${item.id}`, schema: FINISH_SCHEMA },
  ),

  // Stage 2 — Judge panel + assemble the raw card. Panel only runs if the eyes produced images.
  async (fin, item) => {
    let lens_scores = {}
    if (fin && fin.images && fin.images.length) {
      const votes = await parallel(LENSES.map(lens => () =>
        agent(
          `You are a SKEPTICAL senior game artist judging benchmark item "${item.id}" through the "${lens}" lens.\n` +
          `Open and LOOK at each render with your Read tool: ${fin.images.join(', ')}\n` +
          `Brief: ${item.brief}\n` +
          `Score 0-10 against this senior rubric — default LOW when unsure, judge only what the renders show:\n` +
          `${item.rubric_text}\n\n` +
          `Return JSON {"score": <0-10 number>, "critique": "<one concrete sentence>"}.`,
          { phase: 'Judge', label: `judge:${item.id}:${lens}`, schema: JUDGE_SCHEMA },
        )
      ))
      LENSES.forEach((lens, k) => { const v = votes[k]; if (v && typeof v.score === 'number') lens_scores[lens] = v.score })
    } else {
      log(`item ${item.id}: no eye images (headless/no-GL or finish failed) — objective-only, judge skipped`)
    }
    return {
      id: item.id,
      asset_class: item.asset_class,
      senior_threshold: item.senior_threshold,
      gates_pass: !!(fin && fin.gates_pass),
      reached_stage: (fin && fin.reached_stage) || null,
      lens_scores,
    }
  },
)

phase('Score')

// Single scoring pass through scorecard.py (the one source of truth): score_item() enforces the
// gate-floor, aggregate() rolls up the reading. Pass raw cards via a temp file to avoid shell-quoting.
const cards = rawCards.filter(Boolean)
const reading = await agent(
  `Score and aggregate the altimeter run. Here are the raw per-item results as JSON:\n` +
  `${JSON.stringify(cards)}\n\n` +
  `Do exactly this and return ONLY the final printed JSON:\n` +
  `1. Write that JSON array verbatim to ${OUTDIR}/raw_cards.json (mkdir -p ${OUTDIR} first).\n` +
  `2. Run:\n` +
  `   python3 -c "import json,sys; sys.path.insert(0,'${REPO}/src'); ` +
  `from niua_blender_mcp.evals.scorecard import score_item, aggregate; ` +
  `raw=json.load(open('${OUTDIR}/raw_cards.json')); ` +
  `cards=[score_item({'id':r['id'],'asset_class':r['asset_class'],'senior_threshold':r['senior_threshold']}, r['gates_pass'], r['lens_scores']) for r in raw]; ` +
  `print(json.dumps({'reading':aggregate(cards),'cards':cards}))"`,
  { phase: 'Score', label: 'score+aggregate', schema: READING_SCHEMA },
)

const out = reading || { reading: null, cards }
log(`altimeter reading: pass_rate=${out.reading && out.reading.pass_rate} mean_overall=${out.reading && out.reading.mean_overall} weakest_lens=${out.reading && out.reading.weakest_lens}`)
return out
