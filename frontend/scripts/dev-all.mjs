import { spawn } from 'node:child_process';
import process from 'node:process';

const dryRun = process.argv.includes('--dry-run');

const commands = [
  {
    name: 'backend',
    command: '.\\.venv\\Scripts\\python.exe',
    args: ['-m', 'uvicorn', 'main:app', '--reload', '--app-dir', 'backend', '--host', '0.0.0.0', '--port', '8000'],
  },
  {
    name: 'frontend',
    command: 'node_modules\\.bin\\vite.cmd',
    args: ['--host', '0.0.0.0', '--port', '3000'],
  },
];

if (dryRun) {
  for (const job of commands) {
    console.log(`[${job.name}] ${job.command} ${job.args.join(' ')}`);
  }
  process.exit(0);
}

const children = [];
let shuttingDown = false;

function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;

  for (const child of children) {
    if (!child.killed) {
      child.kill('SIGINT');
    }
  }

  setTimeout(() => {
    for (const child of children) {
      if (!child.killed) {
        child.kill('SIGTERM');
      }
    }
    process.exit(code);
  }, 500);
}

for (const job of commands) {
  const child = spawn(job.command, job.args, {
    stdio: 'inherit',
    shell: false,
  });

  children.push(child);

  child.on('exit', (code, signal) => {
    const normalized = typeof code === 'number' ? code : signal ? 1 : 0;
    if (!shuttingDown) {
      console.log(`[${job.name}] exited (${signal ?? code ?? 0}), stopping the other process...`);
      shutdown(normalized);
    }
  });

  child.on('error', (error) => {
    console.error(`[${job.name}] failed to start:`, error.message);
    shutdown(1);
  });
}

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));
