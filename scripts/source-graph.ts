import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import ts from "typescript";

export async function sourceFiles(
  root: string,
  extension = ".ts",
): Promise<string[]> {
  const entries = await readdir(root, { withFileTypes: true });
  const groups = await Promise.all(
    entries.map(async (entry) => {
      const file = path.join(root, entry.name);
      if (entry.isDirectory()) return sourceFiles(file, extension);
      return entry.name.endsWith(extension) ? [path.resolve(file)] : [];
    }),
  );
  return groups.flat().sort();
}

export function importSpecifiers(file: string, code: string): string[] {
  const source = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true);
  const imports = new Set<string>();
  const visit = (node: ts.Node) => {
    if (
      (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) &&
      node.moduleSpecifier &&
      ts.isStringLiteral(node.moduleSpecifier)
    )
      imports.add(node.moduleSpecifier.text);
    if (
      ts.isCallExpression(node) &&
      node.expression.kind === ts.SyntaxKind.ImportKeyword &&
      node.arguments[0] &&
      ts.isStringLiteral(node.arguments[0])
    )
      imports.add(node.arguments[0].text);
    ts.forEachChild(node, visit);
  };
  visit(source);
  return [...imports];
}

/** Includes type-only imports, re-exports and literal dynamic imports. */
export async function dependencyGraph(
  root: string,
): Promise<Map<string, string[]>> {
  const files = await sourceFiles(root);
  const known = new Set(files);
  const graph = new Map<string, string[]>();
  for (const file of files) {
    const imports = importSpecifiers(file, await readFile(file, "utf8"));
    const dependencies = imports
      .filter((item) => item.startsWith("."))
      .map((item) => {
        const candidate = path.resolve(
          path.dirname(file),
          item.replace(/\.js$/, ".ts"),
        );
        if (!known.has(candidate))
          throw new Error(`Unresolved import: ${file} -> ${item}`);
        return candidate;
      });
    graph.set(file, dependencies);
  }
  return graph;
}

export function dependencyCycles(graph: Map<string, string[]>): string[][] {
  const visited = new Set<string>();
  const active: string[] = [];
  const cycles: string[][] = [];
  function visit(file: string) {
    const cycleStart = active.indexOf(file);
    if (cycleStart >= 0) {
      cycles.push([...active.slice(cycleStart), file]);
      return;
    }
    if (visited.has(file)) return;
    active.push(file);
    for (const dependency of graph.get(file) || []) visit(dependency);
    active.pop();
    visited.add(file);
  }
  for (const file of graph.keys()) visit(file);
  return cycles;
}
