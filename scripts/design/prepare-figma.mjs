/** Prepare retryable native Figma updates from browser evidence.
 * node scripts/design/prepare-figma.mjs <browser-evidence-directory>
 * Output is input for sequential use_figma calls, never a flattened UI image.
 */
import fs from "node:fs/promises";
import path from "node:path";
import { prepareScene, squash, nativeRuntime } from "./figma-native.mjs";
import { partitionTree } from "./partition.mjs";
const directory = process.argv[2];
if (!directory) throw new Error("Pass the browser evidence directory");
const manifest = JSON.parse(await fs.readFile(process.argv[3] || "docs/figma-work-v2.json", "utf8"));
const scenes = [],
  definitions = new Map();
for (const screen of manifest.screens) {
  const scene = JSON.parse(
    await fs.readFile(
      path.join(directory, "vallum", `${screen.source}.scene.json`),
      "utf8",
    ),
  );
  const prepared = prepareScene(scene);
  scenes.push(prepared.scene);
  for (const definition of prepared.definitions)
    definitions.set(definition.key, definition);
}
const batches = [];
let batch = [],
  bytes = 0;
for (const definition of definitions.values()) {
  const node = { ...squash(definition, true), component: definition.component };
  const length = JSON.stringify(node).length;
  if (bytes + length > 29000 && batch.length) {
    batches.push(batch);
    batch = [];
    bytes = 0;
  }
  batch.push(node);
  bytes += length;
}
if (batch.length) batches.push(batch);
const plans = scenes.map((scene) => ({
  ...scene,
  tree: undefined,
  ...partitionTree(squash(scene.tree, true)),
}));
await fs.writeFile(
  path.join(directory, "component-batches.json"),
  JSON.stringify(batches),
);
await fs.writeFile(
  path.join(directory, "page-plans.json"),
  JSON.stringify(plans),
);
await fs.writeFile(path.join(directory, "native-runtime.txt"), nativeRuntime);
console.log(
  JSON.stringify({
    screens: scenes.length,
    components: definitions.size,
    batches: batches.length,
  }),
);
