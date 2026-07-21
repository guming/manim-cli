#!/usr/bin/env node

const fs = require("fs");
const os = require("os");
const path = require("path");

const DEFAULT_SKILL_NAME = "manim-video";

function printJson(value) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

function usage() {
  process.stdout.write(`Usage: skill install [options]

Install the bundled Manim agent skill.

Options:
  --target-dir <dir>  Directory that contains installed skills (default: ~/.codex/skills)
  --name <name>       Installed skill directory name (default: manim-video)
  --force             Replace an existing installed skill
  --dry-run           Report what would be installed without writing files
  -h, --help          Show this help
`);
}

function expandHome(input) {
  if (input === "~") {
    return os.homedir();
  }
  if (input.startsWith("~/")) {
    return path.join(os.homedir(), input.slice(2));
  }
  return input;
}

function copyDir(source, destination) {
  fs.mkdirSync(destination, { recursive: true });
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    const sourcePath = path.join(source, entry.name);
    const destinationPath = path.join(destination, entry.name);
    if (entry.isDirectory()) {
      copyDir(sourcePath, destinationPath);
    } else if (entry.isFile()) {
      fs.copyFileSync(sourcePath, destinationPath);
    }
  }
}

function listFiles(root, current = root, files = []) {
  for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
    const entryPath = path.join(current, entry.name);
    if (entry.isDirectory()) {
      listFiles(root, entryPath, files);
    } else if (entry.isFile()) {
      files.push(path.relative(root, entryPath));
    }
  }
  return files.sort();
}

function parseInstallArgs(args) {
  const options = {
    targetDir: "~/.codex/skills",
    name: DEFAULT_SKILL_NAME,
    force: false,
    dryRun: false,
  };

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--target-dir") {
      options.targetDir = args[index + 1];
      index += 1;
    } else if (arg === "--name") {
      options.name = args[index + 1];
      index += 1;
    } else if (arg === "--force") {
      options.force = true;
    } else if (arg === "--dry-run") {
      options.dryRun = true;
    } else if (arg === "-h" || arg === "--help") {
      options.help = true;
    } else {
      throw new Error(`Unknown option: ${arg}`);
    }
  }

  if (!options.targetDir) {
    throw new Error("--target-dir requires a value");
  }
  if (!options.name) {
    throw new Error("--name requires a value");
  }

  return options;
}

function install(args) {
  const options = parseInstallArgs(args);
  if (options.help) {
    usage();
    return 0;
  }

  const source = path.resolve(__dirname, "..", "manim_cli", "agent", "skill");
  const targetDir = path.resolve(expandHome(options.targetDir));
  const destination = path.join(targetDir, options.name);

  if (!fs.existsSync(source)) {
    printJson({
      ok: false,
      phase: "skill_install",
      error_type: "missing_bundled_skill",
      message: `Bundled skill directory was not found: ${source}`,
    });
    return 1;
  }

  if (fs.existsSync(destination) && !options.force) {
    printJson({
      ok: false,
      phase: "skill_install",
      error_type: "destination_exists",
      message: `Skill already exists at ${destination}`,
      suggestions: ["Pass --force to replace the existing installed skill."],
      destination,
    });
    return 1;
  }

  const files = listFiles(source);
  if (!options.dryRun) {
    fs.mkdirSync(targetDir, { recursive: true });
    fs.rmSync(destination, { recursive: true, force: true });
    copyDir(source, destination);
  }

  printJson({
    ok: true,
    phase: "skill_install",
    source,
    destination,
    installed: !options.dryRun,
    files,
  });
  return 0;
}

function main() {
  const [command, ...args] = process.argv.slice(2);
  if (!command || command === "-h" || command === "--help") {
    usage();
    return 0;
  }
  if (command !== "install") {
    process.stderr.write(`Unknown command: ${command}\n`);
    usage();
    return 1;
  }
  return install(args);
}

process.exitCode = main();
