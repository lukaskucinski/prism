#!/usr/bin/env node
/**
 * Validate SUPABASE_DB_URL in .env without echoing the password.
 * Local-only utility. Reports OK/FAIL on each check.
 */
import fs from "node:fs";
import path from "node:path";

const ENV_PATH = path.resolve(process.cwd(), ".env");
if (!fs.existsSync(ENV_PATH)) {
  console.error("No .env at", ENV_PATH);
  process.exit(2);
}

const raw = fs.readFileSync(ENV_PATH, "utf8");
const line = raw.split(/\r?\n/).find((l) => l.startsWith("SUPABASE_DB_URL="));
if (!line) {
  console.error("SUPABASE_DB_URL not found in .env");
  process.exit(2);
}
const rhs = line.slice("SUPABASE_DB_URL=".length).trim();
const surroundingQuotes = /^["'].*["']$/.test(rhs);
const url = rhs.replace(/^["']|["']$/g, "");

// Manual parse so we can diagnose malformed URLs
const afterScheme = url.startsWith("postgresql://") ? url.slice("postgresql://".length) : null;
const atIdx = afterScheme ? afterScheme.lastIndexOf("@") : -1;
const userInfo = afterScheme && atIdx >= 0 ? afterScheme.slice(0, atIdx) : "";
const hostAndDb = afterScheme && atIdx >= 0 ? afterScheme.slice(atIdx + 1) : afterScheme ?? "";
const [user, ...pwdParts] = userInfo.split(":");
const rawPwd = pwdParts.join(":"); // tolerate ':' in password
const [hostport, dbpath] = hostAndDb.split("/", 2);
const [host, port] = (hostport ?? "").split(":");

// Character class summary for the raw password segment (does NOT echo content)
const classes = {
  letters: (rawPwd.match(/[A-Za-z]/g) ?? []).length,
  digits: (rawPwd.match(/[0-9]/g) ?? []).length,
  pct_encoded: (rawPwd.match(/%[0-9A-Fa-f]{2}/g) ?? []).length,
  safe_punct: (rawPwd.match(/[.\-_~]/g) ?? []).length,
  unsafe: [...new Set(rawPwd.match(/[^A-Za-z0-9._~%\-]/g) ?? [])],
  whitespace_in_raw: /\s/.test(rawPwd),
  brackets: /[\[\]]/.test(rawPwd),
};

const checks = [
  ["scheme is postgresql://", url.startsWith("postgresql://")],
  ["found '@' separating credentials from host", atIdx >= 0],
  ["no literal placeholder ([password] / <password>)", !classes.brackets && !/\[password\]|<password>/i.test(url)],
  ["username is 'postgres'", user === "postgres"],
  ["host matches project", host === "db.uuqxqqcelabpacljeqgm.supabase.co"],
  ["port is 5432", port === "5432"],
  ["database is 'postgres'", dbpath === "postgres"],
  ["password present", rawPwd.length > 0],
  ["password length >= 8", rawPwd.length >= 8],
  ["password length <= 200", rawPwd.length <= 200],
  ["no surrounding quotes on value", !surroundingQuotes],
  ["no whitespace anywhere in URL", !/\s/.test(url)],
  ["no whitespace inside password segment", !classes.whitespace_in_raw],
  [
    "password chars are URL-safe (no unencoded specials)",
    classes.unsafe.length === 0,
  ],
];

let failed = 0;
for (const [name, ok] of checks) {
  console.log(`${ok ? "OK  " : "FAIL"} ${name}`);
  if (!ok) failed += 1;
}
console.log("---");
console.log(`password raw length: ${rawPwd.length}`);
console.log(
  `password chars (counts): letters=${classes.letters} digits=${classes.digits} ` +
    `pct-encoded triplets=${classes.pct_encoded} safe-punct(.~-_)=${classes.safe_punct}`
);
if (classes.unsafe.length > 0) {
  // List unsafe character TYPES only — not where they appear.
  console.log(
    `unsafe characters present (need %-encoding): [${classes.unsafe
      .map((c) => `${JSON.stringify(c)} (U+${c.charCodeAt(0).toString(16).padStart(4, "0").toUpperCase()})`)
      .join(", ")}]`
  );
  console.log("Fix: replace each in the password with its %-encoding, e.g.:");
  const examples = {
    "#": "%23",
    "@": "%40",
    "?": "%3F",
    "/": "%2F",
    "=": "%3D",
    "&": "%26",
    "+": "%2B",
    " ": "%20",
    "!": "%21",
    "(": "%28",
    ")": "%29",
    "*": "%2A",
    ",": "%2C",
    ";": "%3B",
    "<": "%3C",
    ">": "%3E",
  };
  for (const c of classes.unsafe) if (examples[c]) console.log(`  ${c} → ${examples[c]}`);
}

process.exit(failed > 0 ? 1 : 0);
