import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import mermaid from "mermaid";

const scriptPath = fileURLToPath(import.meta.url);
const root = path.resolve(path.dirname(scriptPath), "..");
const docsRoot = path.join(root, "docs");
const fencePattern = /```mermaid\s*\n([\s\S]*?)```/g;

async function markdownFiles(directory) {
  const entries = await fs.readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await markdownFiles(target)));
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      files.push(target);
    }
  }
  return files.sort();
}

const failures = [];
let blocksChecked = 0;

for (const markdownPath of await markdownFiles(docsRoot)) {
  const content = await fs.readFile(markdownPath, "utf8");
  const relative = path.relative(root, markdownPath);
  let match;
  let blockIndex = 0;

  while ((match = fencePattern.exec(content)) !== null) {
    blockIndex += 1;
    blocksChecked += 1;
    try {
      await mermaid.parse(match[1]);
    } catch (error) {
      failures.push(
        `${relative} Mermaid block ${blockIndex}\n${error?.message ?? String(error)}`,
      );
    }
  }
}

if (failures.length > 0) {
  console.error(
    `Mermaid validation failed for ${failures.length} block(s):\n\n${failures.join("\n\n")}`,
  );
  process.exit(1);
}

console.log(`Validated ${blocksChecked} Mermaid diagram(s) under docs/.`);
