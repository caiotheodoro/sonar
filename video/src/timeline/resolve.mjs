/**
 * The one timing implementation. Remotion (src/timeline/index.ts) and the
 * gate (capture/check-shot-reality.mjs) both import this file, so the cut the
 * renderer draws is the cut the gate checked.
 *
 * Everything is authored in absolute milliseconds on the video timeline and
 * converted to frames in exactly one place, `msToFrame`. Nothing accumulates
 * durations: every frame position comes from an absolute ms, so a 100 BPM
 * grid (600 ms, 18 frames) cannot drift.
 */

export const msToFrame = (ms, fps) => Math.round((ms * fps) / 1000);

const nearest = (values, ms) => {
  let best = null;
  for (const v of values) {
    if (best === null || Math.abs(v - ms) < Math.abs(best - ms)) best = v;
  }
  return best;
};

const resolveAnchor = (anchor, ctx, where) => {
  if (anchor == null || typeof anchor !== "object") throw new Error(`${where}: anchor missing`);
  if ("ms" in anchor) return anchor.ms;
  if ("beat" in anchor) {
    const v = ctx.grid.beatsMs[anchor.beat];
    if (v === undefined) throw new Error(`${where}: beat ${anchor.beat} is off the grid (${ctx.grid.beatsMs.length} beats)`);
    return v + (anchor.offsetMs ?? 0);
  }
  if ("hit" in anchor) {
    const v = ctx.grid.hitsMs[anchor.hit];
    if (v === undefined) throw new Error(`${where}: hit ${anchor.hit} is off the grid (${ctx.grid.hitsMs.length} hits)`);
    return v + (anchor.offsetMs ?? 0);
  }
  if ("cue" in anchor) {
    const cue = ctx.cues.find((c) => c.id === anchor.cue);
    if (!cue) throw new Error(`${where}: no cue "${anchor.cue}" in narration.json`);
    if (!ctx.narrationMeasured) throw new Error(`${where}: anchored to cue "${anchor.cue}" but the narration is not measured; run capture/measure-cues.mjs`);
    const base = anchor.edge === "end" ? cue.endMs : cue.startMs;
    return base + ctx.narrationOffsetMs + (anchor.offsetMs ?? 0);
  }
  throw new Error(`${where}: unknown anchor ${JSON.stringify(anchor)}`);
};

/**
 * @param {{storyboard: object, cues: object[], grid: object, fps: number, narrationMeasured?: boolean}} input
 */
export const resolveTimeline = ({ storyboard, cues, grid, fps, narrationMeasured }) => {
  const sb = storyboard;
  const measured = narrationMeasured ?? cues.some((c) => c.endMs > 0);
  const ctx = { grid, cues, narrationMeasured: measured, narrationOffsetMs: sb.narration.offsetMs };

  if (!Array.isArray(sb.shots) || sb.shots.length === 0) throw new Error("storyboard.json: no shots");
  const ids = new Set();
  for (const s of sb.shots) {
    if (ids.has(s.id)) throw new Error(`storyboard.json: duplicate shot id "${s.id}"`);
    ids.add(s.id);
    if (!sb.acts.includes(s.act)) throw new Error(`shot "${s.id}": act "${s.act}" is not declared in acts[]`);
  }

  // starts
  const starts = sb.shots.map((s) => {
    const where = `shot "${s.id}"`;
    let ms = resolveAnchor(s.start, ctx, where);
    let snappedMs;
    if (s.snap) {
      const pool = s.snap === "hit" ? grid.hitsMs : grid.beatsMs;
      const n = nearest(pool, ms);
      if (n !== null && Math.abs(n - ms) <= sb.snapToleranceMs && n !== ms) {
        snappedMs = n - ms;
        ms = n;
      }
    }
    return { ms, snappedMs };
  });

  const last = sb.shots[sb.shots.length - 1];
  if (!last.end) throw new Error(`shot "${last.id}": the last shot must carry an end anchor`);
  for (const s of sb.shots.slice(0, -1)) {
    if (s.end) throw new Error(`shot "${s.id}": only the last shot may carry an end; every other shot ends where the next starts`);
  }
  const totalMs = resolveAnchor(last.end, ctx, `shot "${last.id}" end`);
  if (totalMs > sb.capMs) throw new Error(`the cut runs ${totalMs} ms, over the ${sb.capMs} ms cap`);

  const shots = sb.shots.map((shot, i) => {
    const startMs = starts[i].ms;
    const endMs = i + 1 < sb.shots.length ? starts[i + 1].ms : totalMs;
    if (i > 0 && startMs <= starts[i - 1].ms) {
      throw new Error(`shot "${shot.id}" starts at ${startMs} ms, not after "${sb.shots[i - 1].id}" (${starts[i - 1].ms} ms)`);
    }
    if (endMs - startMs < sb.minShotMs) {
      throw new Error(`shot "${shot.id}" lasts ${endMs - startMs} ms, under the ${sb.minShotMs} ms floor`);
    }
    const from = msToFrame(startMs, fps);
    const to = msToFrame(endMs, fps);
    return { shot, index: i, startMs, endMs, from, durationInFrames: to - from, snappedMs: starts[i].snappedMs };
  });
  if (shots[0].startMs !== 0) throw new Error(`shot "${shots[0].shot.id}" must start at 0 ms, starts at ${shots[0].startMs}`);

  // acts: contiguous, declared order
  const acts = {};
  let lastActIndex = -1;
  for (const r of shots) {
    const ai = sb.acts.indexOf(r.shot.act);
    if (ai < lastActIndex) throw new Error(`shot "${r.shot.id}": act "${r.shot.act}" appears after a later act; acts must run in declared order`);
    lastActIndex = ai;
    const a = acts[r.shot.act] ?? { from: r.from, to: r.from, startMs: r.startMs, endMs: r.startMs };
    a.to = r.from + r.durationInFrames;
    a.endMs = r.endMs;
    acts[r.shot.act] = a;
  }
  for (const act of sb.acts) {
    if (!acts[act]) throw new Error(`act "${act}" has no shots`);
  }

  // cues on the video timeline
  const narrationFrom = msToFrame(sb.narration.offsetMs, fps);
  const resolvedCues = cues.map((c) => {
    const videoStartMs = c.startMs + sb.narration.offsetMs;
    const videoEndMs = c.endMs + sb.narration.offsetMs;
    return {
      ...c,
      videoStartMs,
      videoEndMs,
      from: msToFrame(videoStartMs, fps),
      to: msToFrame(videoEndMs, fps),
      shots: measured ? shots.filter((s) => s.startMs < videoEndMs && s.endMs > videoStartMs).map((s) => s.shot.id) : [],
    };
  });
  if (measured) {
    const lastCue = resolvedCues[resolvedCues.length - 1];
    if (lastCue && lastCue.videoEndMs > totalMs - 500) {
      throw new Error(`narration ends at ${lastCue.videoEndMs} ms, inside the last 500 ms of a ${totalMs} ms cut`);
    }
  }

  const totalFrames = msToFrame(totalMs, fps);
  return {
    shots,
    cues: resolvedCues,
    totalMs,
    totalFrames,
    acts,
    narrationFrom,
    narrationMeasured: measured,
    beatFrames: grid.beatsMs.filter((m) => m < totalMs).map((m) => msToFrame(m, fps)),
    hitFrames: grid.hitsMs.filter((m) => m < totalMs).map((m) => msToFrame(m, fps)),
  };
};

const pad = (s, n) => String(s).padEnd(n);
const rpad = (s, n) => String(s).padStart(n);

export const timelineReport = (t) => {
  const lines = [];
  lines.push(`${pad("#", 3)}${pad("id", 8)}${pad("act", 9)}${pad("kind", 9)}${rpad("start", 7)}${rpad("end", 7)}${rpad("frames", 7)}${rpad("snap", 6)}  content`);
  for (const r of t.shots) {
    const s = r.shot;
    const content = s.kind === "shot" ? s.src : s.kind === "stamp" ? s.text : s.kind === "card" ? s.card : s.kind === "cast" ? `${s.src} ×${s.speed ?? 1}` : s.rows.join("/");
    lines.push(
      `${pad(r.index + 1, 3)}${pad(s.id, 8)}${pad(s.act, 9)}${pad(s.kind, 9)}${rpad(r.startMs, 7)}${rpad(r.endMs, 7)}${rpad(r.durationInFrames, 7)}${rpad(r.snappedMs === undefined ? "" : (r.snappedMs > 0 ? "+" : "") + r.snappedMs, 6)}  ${content}`,
    );
  }
  lines.push(`total ${t.totalMs} ms · ${t.totalFrames} frames · narration from ${t.narrationFrom}f (${t.narrationMeasured ? "measured" : "UNMEASURED"})`);
  if (t.narrationMeasured) {
    lines.push("");
    lines.push(`${pad("cue", 5)}${rpad("start", 7)}${rpad("end", 7)}  shots`);
    for (const c of t.cues) lines.push(`${pad(c.id, 5)}${rpad(c.videoStartMs, 7)}${rpad(c.videoEndMs, 7)}  ${c.shots.join(", ")}`);
  }
  return lines.join("\n");
};

/** SRT of the cues on the video timeline. */
export const timelineSrt = (t) => {
  const stamp = (ms) => {
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    const s = Math.floor((ms % 60000) / 1000);
    const x = ms % 1000;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")},${String(x).padStart(3, "0")}`;
  };
  return t.cues.map((c, i) => `${i + 1}\n${stamp(c.videoStartMs)} --> ${stamp(c.videoEndMs)}\n${c.text}\n`).join("\n");
};
