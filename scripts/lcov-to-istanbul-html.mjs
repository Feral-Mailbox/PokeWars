#!/usr/bin/env node
/**
 * Convert an LCOV file into an Istanbul HTML report (same style as Vitest/frontend).
 *
 * Usage:
 *   node scripts/lcov-to-istanbul-html.mjs <lcov.info> <output-dir> [path-prefix-to-strip]
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

function parseLcov(text, stripPrefix) {
  const map = libCoverage.createCoverageMap({});
  let current = null;

  const flush = () => {
    if (!current) return;
    map.addFileCoverage(current);
    current = null;
  };

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;

    if (line.startsWith("TN:")) continue;
    if (line.startsWith("SF:")) {
      flush();
      let filePath = line.slice(3);
      if (stripPrefix && filePath.startsWith(stripPrefix)) {
        filePath = filePath.slice(stripPrefix.length).replace(/^[/\\]/, "");
      }
      filePath = filePath.replace(/\\/g, "/");
      current = {
        path: filePath,
        statementMap: {},
        fnMap: {},
        branchMap: {},
        s: {},
        f: {},
        b: {},
      };
      continue;
    }
    if (!current) continue;

    if (line.startsWith("FN:")) {
      // FN:<line>,<name>
      const rest = line.slice(3);
      const comma = rest.indexOf(",");
      const startLine = Number(rest.slice(0, comma));
      const name = rest.slice(comma + 1) || `(anonymous_${Object.keys(current.fnMap).length})`;
      const id = String(Object.keys(current.fnMap).length);
      current.fnMap[id] = {
        name,
        decl: {
          start: { line: startLine, column: 0 },
          end: { line: startLine, column: 0 },
        },
        loc: {
          start: { line: startLine, column: 0 },
          end: { line: startLine, column: 0 },
        },
        line: startLine,
      };
      current.f[id] = 0;
      continue;
    }

    if (line.startsWith("FNDA:")) {
      // FNDA:<hits>,<name>
      const rest = line.slice(5);
      const comma = rest.indexOf(",");
      const hits = Number(rest.slice(0, comma));
      const name = rest.slice(comma + 1);
      const entry = Object.entries(current.fnMap).find(([, fn]) => fn.name === name);
      if (entry) current.f[entry[0]] = hits;
      continue;
    }

    if (line.startsWith("DA:")) {
      // DA:<line>,<hits>
      const [lineNo, hits] = line.slice(3).split(",").map(Number);
      const id = String(Object.keys(current.statementMap).length);
      current.statementMap[id] = {
        start: { line: lineNo, column: 0 },
        end: { line: lineNo, column: 0 },
      };
      current.s[id] = hits;
      continue;
    }

    if (line.startsWith("BRDA:")) {
      // BRDA:<line>,<block>,<branch>,<taken>
      const [lineNo, block, branch, takenRaw] = line.slice(5).split(",");
      const taken = takenRaw === "-" ? 0 : Number(takenRaw);
      const key = `${block}`;
      if (!current.branchMap[key]) {
        current.branchMap[key] = {
          loc: {
            start: { line: Number(lineNo), column: 0 },
            end: { line: Number(lineNo), column: 0 },
          },
          type: "branch",
          locations: [],
          line: Number(lineNo),
        };
        current.b[key] = [];
      }
      current.branchMap[key].locations.push({
        start: { line: Number(lineNo), column: 0 },
        end: { line: Number(lineNo), column: 0 },
      });
      current.b[key].push(taken);
      continue;
    }

    if (line === "end_of_record") {
      flush();
    }
  }

  flush();
  return map;
}

const lcovPath = process.argv[2];
const outDir = process.argv[3];
const stripPrefix = process.argv[4] || "";

if (!lcovPath || !outDir) {
  console.error(
    "Usage: node scripts/lcov-to-istanbul-html.mjs <lcov.info> <output-dir> [path-prefix-to-strip]",
  );
  process.exit(1);
}

const text = fs.readFileSync(lcovPath, "utf8");
const coverageMap = parseLcov(text, stripPrefix);

fs.mkdirSync(outDir, { recursive: true });
const context = libReport.createContext({
  dir: outDir,
  defaultSummarizer: "nested",
  coverageMap,
});
reports.create("html", { skipEmpty: false, skipFull: false }).execute(context);
console.log(`Wrote Istanbul HTML report to ${outDir}`);
