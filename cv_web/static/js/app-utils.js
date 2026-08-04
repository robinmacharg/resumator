export function shellQuote(arg) {
  if (arg === "") {
    return "''";
  }
  if (/^[A-Za-z0-9_./:@%+=,-]+$/.test(arg)) {
    return arg;
  }
  return `'${String(arg).replace(/'/g, `'\\''`)}'`;
}

export function formatCommandForDisplay(command) {
  if (!Array.isArray(command) || command.length === 0) {
    return "No command yet. Run Research first.";
  }
  return command.map((part) => shellQuote(String(part))).join(" ");
}

export function formatTimestampToSecond(value) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) {
    return new Date().toLocaleString();
  }
  const pad2 = (n) => String(n).padStart(2, "0");
  const year = date.getFullYear();
  const month = pad2(date.getMonth() + 1);
  const day = pad2(date.getDate());
  const hours = pad2(date.getHours());
  const mins = pad2(date.getMinutes());
  const secs = pad2(date.getSeconds());
  return `${year}-${month}-${day} ${hours}:${mins}:${secs}`;
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function parseResearchUrlsInput(rawText) {
  const seen = new Set();
  const urls = [];
  (rawText || "").split(/\r?\n/).forEach((line) => {
    const cleaned = line.trim();
    if (!cleaned || cleaned.startsWith("#") || seen.has(cleaned)) {
      return;
    }
    seen.add(cleaned);
    urls.push(cleaned);
  });
  return urls;
}
