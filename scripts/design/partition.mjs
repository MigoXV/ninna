/** Split semantic subtrees at frame boundaries to stay within MCP code limits. */
export function partitionTree(tree, limit = 28000) {
  let ticket = 0;
  function split(node) {
    if (JSON.stringify(node).length <= limit) return { tree: node, jobs: [] };
    if (!node.children?.length) throw new Error(`Oversized leaf: ${node.name}`);
    const slot = `region-${++ticket}`;
    const jobs = [];
    let batch = [],
      bytes = 0;
    for (const child of node.children) {
      const part = split(child);
      const length = JSON.stringify(part.tree).length;
      if (batch.length && bytes + length > limit) {
        jobs.push({ slot, nodes: batch });
        batch = [];
        bytes = 0;
      }
      batch.push(part.tree);
      bytes += length;
      if (part.jobs.length) {
        jobs.push({ slot, nodes: batch });
        batch = [];
        bytes = 0;
        jobs.push(...part.jobs);
      }
    }
    if (batch.length) jobs.push({ slot, nodes: batch });
    return { tree: { ...node, children: [], slot }, jobs };
  }
  return split(tree);
}
