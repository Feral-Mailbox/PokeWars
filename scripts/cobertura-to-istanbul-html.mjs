#!/usr/bin/env node
/**
 * Convert coverage.py Cobertura XML into an Istanbul HTML report
 * (same style as the Vitest/frontend lcov-report).
 *
 * Usage:
 *   node scripts/cobertura-to-istanbul-html.mjs <coverage.xml> <output-dir>
 */
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const frontendModules = path.join(root, "apps/frontend/node_modules");

function load(name) {
  return require(require.resolve(name, { paths: [frontendModules, root] }));
}

const libCoverage = load("istanbul-lib-coverage");
const libReport = load("istanbul-lib-report");
const reports = load("istanbul-reports");

function decodeXml(value) {
  return value
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&");
}

function attr(tag, name) {
  const match = tag.match(new RegExp(`${name}="([^"]*)"`));
  return match ? decodeXml(match[1]) : null;
}

function parseConditionCoverage(text) {
  // e.g. "100% (2/2)" or "50% (1/2)" or "0% (0/2)"
  const match = String(text || "").match(/\((\d+)\/(\d+)\)/);
  if (!match) return { covered: 0, total: 0 };
  return { covered: Number(match[1]), total: Number(match[2]) };
}

function parseCobertura(xml) {
  const map = libCoverage.createCoverageMap({});
  const classBlocks = xml.match(/<class\b[\s\S]*?<\/class>/g) || [];

  for (const block of classBlocks) {
    const openTag = block.match(/<class\b[^>]*>/)?.[0];
    if (!openTag) continue;
    const filePath = (attr(openTag, "filename") || "").replace(/\\/g, "/");
    if (!filePath) continue;

    const coverage = {
      path: filePath,
      statementMap: {},
      fnMap: {},
      branchMap: {},
      s: {},
      f: {},
      b: {},
    };

    const lineTags = block.match(/<line\b[^>]*\/?>/g) || [];
    for (const lineTag of lineTags) {
      const lineNo = Number(attr(lineTag, "number"));
      const hits = Number(attr(lineTag, "hits") || 0);
      if (!Number.isFinite(lineNo)) continue;

      const stmtId = String(Object.keys(coverage.statementMap).length);
      coverage.statementMap[stmtId] = {
        start: { line: lineNo, column: 0 },
        end: { line: lineNo, column: 0 },
      };
      coverage.s[stmtId] = hits;

      if (attr(lineTag, "branch") === "true") {
        const { covered, total } = parseConditionCoverage(
          attr(lineTag, "condition-coverage"),
        );
        const branchTotal = total > 0 ? total : 2;
        const branchCovered = Math.min(covered, branchTotal);
        const branchId = String(Object.keys(coverage.branchMap).length);
        coverage.branchMap[branchId] = {
          loc: {
            start: { line: lineNo, column: 0 },
            end: { line: lineNo, column: 0 },
          },
          type: "branch",
          locations: Array.from({ length: branchTotal }, () => ({
            start: { line: lineNo, column: 0 },
            end: { line: lineNo, column: 0 },
          })),
          line: lineNo,
        };
        coverage.b[branchId] = Array.from({ length: branchTotal }, (_, i) =>
          i < branchCovered ? Math.max(hits, 1) : 0,
        );
      }
    }

    // coverage.py Cobertura often omits methods; synthesize one fn per file
    // so the Functions column is present and mirrors statement coverage.
    const stmtHits = Object.values(coverage.s);
    // Empty files (e.g. __init__.py) have no statements — treat as covered
    // so they don't drag package Functions % below green.
    const anyHit = stmtHits.length === 0 || stmtHits.some((n) => n > 0) ? 1 : 0;
    coverage.fnMap["0"] = {
      name: path.basename(filePath),
      decl: { start: { line: 1, column: 0 }, end: { line: 1, column: 0 } },
      loc: { start: { line: 1, column: 0 }, end: { line: 1, column: 0 } },
      line: 1,
    };
    coverage.f["0"] = anyHit;

    map.addFileCoverage(coverage);
  }

  return map;
}

const xmlPath = process.argv[2];
const outDir = process.argv[3];

if (!xmlPath || !outDir) {
  console.error(
    "Usage: node scripts/cobertura-to-istanbul-html.mjs <coverage.xml> <output-dir>",
  );
  process.exit(1);
}

const xml = fs.readFileSync(xmlPath, "utf8");
const coverageMap = parseCobertura(xml);
fs.mkdirSync(outDir, { recursive: true });

const sourceFinder = (filePath) => {
  const candidates = [
    path.join(root, filePath),
    path.join(root, "apps/backend", filePath),
    filePath,
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return fs.readFileSync(candidate, "utf8");
    }
  }
  return `// Source not found for ${filePath}\n`;
};

const reportContext = libReport.createContext({
  dir: outDir,
  defaultSummarizer: "nested",
  coverageMap,
  sourceFinder,
});

reports.create("html", { skipEmpty: false, skipFull: false }).execute(reportContext);
console.log(`Wrote Istanbul HTML report to ${outDir}`);
