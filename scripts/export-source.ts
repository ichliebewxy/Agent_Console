import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import AdmZip from "adm-zip";

const root = process.cwd();
const output = path.join(root, "tmp", "delivery");
const files = [
  ...new Set(
    execFileSync(
      "git",
      ["ls-files", "--cached", "--others", "--exclude-standard", "-z"],
      { encoding: "utf8" },
    )
      .split("\0")
      .filter(Boolean),
  ),
]
  .filter((file) => !file.startsWith("tmp/") || file === "tmp/.gitkeep")
  .filter(
    (file) => !/(^|\/)\.env(?:\.|$)/.test(file) || file === ".env.example",
  )
  .sort();
if (!files.includes("docs/file-tree.md")) files.push("docs/file-tree.md");
files.sort();

type Tree = { [key: string]: Tree | null };
const tree: Tree = {};
for (const file of files) {
  const parts = file.split("/");
  let current = tree;
  for (const [index, part] of parts.entries()) {
    if (index === parts.length - 1) current[part] = null;
    else current = current[part] ??= {};
  }
}
function draw(tree: Tree, prefix = ""): string[] {
  const entries = Object.entries(tree).sort(
    ([a, av], [b, bv]) =>
      Number(bv !== null) - Number(av !== null) || a.localeCompare(b),
  );
  return entries.flatMap(([name, children], index) => {
    const last = index === entries.length - 1;
    return [
      prefix + (last ? "└─ " : "├─ ") + name + (children ? "/" : ""),
      ...(children ? draw(children, prefix + (last ? "   " : "│  ")) : []),
    ];
  });
}
await mkdir(output, { recursive: true });
await writeFile(
  "docs/file-tree.md",
  `# 完整交付文件树\n\n共 ${files.length} 个版本管理文件（含新增文件）；不包含第三方安装目录、真实密钥或用户运行数据。由 npm run export:source 生成。\n\n\`\`\`text\nproject/\n${draw(tree).join("\n")}\n\`\`\`\n`,
  "utf8",
);

const zip = new AdmZip();
const code: string[] = [
  "# 完整项目源码\n\n与 refactored-source.zip 对应；文件内容逐字包含在下面的代码块中。\n",
];
const manifest: Array<{ path: string; bytes: number; sha256: string }> = [];
for (const file of files) {
  const content = await readFile(path.join(root, file));
  zip.addFile(file, content);
  const text = content.toString("utf8");
  const longestFence = Math.max(
    2,
    ...Array.from(text.matchAll(/`+/g), (match) => match[0].length),
  );
  const fence = "`".repeat(longestFence + 1);
  code.push(
    `\n## ${file}\n\n${fence}${path.extname(file).slice(1)}\n${text}${text.endsWith("\n") ? "" : "\n"}${fence}\n`,
  );
  manifest.push({
    path: file,
    bytes: content.length,
    sha256: createHash("sha256").update(content).digest("hex"),
  });
}
await zip.writeZipPromise(path.join(output, "refactored-source.zip"));
await writeFile(path.join(output, "source-code.md"), code.join(""), "utf8");
await writeFile(
  path.join(output, "source-manifest.json"),
  JSON.stringify(
    {
      baseRevision: execFileSync("git", ["rev-parse", "HEAD"], {
        encoding: "utf8",
      }).trim(),
      files: manifest,
    },
    null,
    2,
  ),
  "utf8",
);
// Reopen the actual archive and verify every file instead of trusting the write.
const reopened = new AdmZip(path.join(output, "refactored-source.zip"));
for (const file of manifest) {
  const content = reopened.readFile(file.path);
  if (
    !content ||
    createHash("sha256").update(content).digest("hex") !== file.sha256
  )
    throw new Error(`Archive mismatch: ${file.path}`);
}
console.log(`Exported and verified ${manifest.length} files in ${output}`);
