/** Only metrics actually supplied by the answer pipeline are displayed. */
export function buildProcessRuns(items = []) {
  const runs = new Map();
  let stages = [];
  items.forEach((item, index) => {
    if (item.type === 'user') stages = [];
    else if (item.type === 'stage') stages.push(item);
    else if (item.type === 'answer') { runs.set(index, stages); stages = []; }
  });
  return runs;
}

export function statsRows(answer = {}) {
  const rows = [];
  if (answer.usage?.total_tokens != null) rows.push({label:"Token 用量", value:Number(answer.usage.total_tokens).toLocaleString()});
  if (answer.stats?.duration_ms != null) rows.push({label:"耗时", value:`${(answer.stats.duration_ms / 1000).toFixed(1)}s`});
  if (answer.stats?.cost != null) rows.push({label:"成本", value:`$${Number(answer.stats.cost).toFixed(4)}`});
  return rows;
}
