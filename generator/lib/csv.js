// Minimal RFC-4180 CSV writer. Every field is quoted; internal quotes are
// doubled; nested values (arrays/objects) are JSON-stringified into the cell.
// Rows are CRLF-terminated and the output is written as UTF-8 (content contains
// £, curly quotes, footnote brackets, etc.).

export function csvField(value) {
  let v = value;
  if (v === null || v === undefined) v = "";
  else if (typeof v !== "string") v = JSON.stringify(v);
  return '"' + v.replace(/"/g, '""') + '"';
}

/**
 * @param {Array<object>} rows
 * @param {string[]} columns ordered column keys
 * @returns {string} CSV text (with header row)
 */
export function toCsv(rows, columns) {
  const lines = [columns.map(csvField).join(",")];
  for (const row of rows) {
    lines.push(columns.map((c) => csvField(row[c])).join(","));
  }
  return lines.join("\r\n") + "\r\n";
}
